"""
Agent Orchestrator for SAGE Studio

Layer: L6 (sage-studio)
Dependencies: IntentClassifier, KnowledgeManager, WorkflowGenerator
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import AsyncGenerator

import httpx

from sage.studio.config.ports import StudioPorts
from sage_libs.sage_agentic.intent import IntentClassifier, UserIntent, IntentResult
from sage_libs.sage_agentic.workflows.router import (
    WorkflowDecision,
    WorkflowRequest,
    WorkflowRoute,
    WorkflowRouter,
)
from sage.studio.models.agent_step import (
    AgentStep,
)
from sage.studio.services.agents.coding import CodingAgent
from sage.studio.services.agents.researcher import ResearcherAgent
from sage.studio.services.knowledge_manager import KnowledgeManager
from sage.studio.services.memory_integration import get_memory_service

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Agent 编排器

    协调意图分类、知识检索、工具调用等，处理用户请求。
    """

    def __init__(self):
        # 优先使用 LLM 模式以获得 Agentic 体验，内部会自动降级到 keyword
        self.intent_classifier = IntentClassifier(mode="llm")
        self.workflow_router = WorkflowRouter(self.intent_classifier)
        self.knowledge_manager = KnowledgeManager()

        # 尝试获取工具注册表
        try:
            from sage.studio.tools.base import get_tool_registry

            self.tools = get_tool_registry()
        except ImportError:
            logger.warning("ToolRegistry not found, tools will be unavailable.")

            class MockRegistry:
                def get(self, name):
                    return None

                def register(self, tool):
                    pass

                def list_tools(self):
                    return []

            self.tools = MockRegistry()

        # 注册内置工具
        self._register_builtin_tools()

        # Initialize Agents (Swarm Architecture)
        # Pass all available tools to the researcher agent
        self.researcher_agent = ResearcherAgent(self.tools.list_tools())

        # Coding tools (L6 FS infra) — stored for per-request CodingAgent construction
        self._code_tools = self._build_code_tools()

    def _register_builtin_tools(self):
        """注册内置工具"""
        try:
            from sage.studio.tools.arxiv_search import ArxivSearchTool
            from sage.studio.tools.knowledge_search import KnowledgeSearchTool
            from sage.studio.tools.middleware_adapter import NatureNewsTool

            self.tools.register(KnowledgeSearchTool(self.knowledge_manager))
            self.tools.register(ArxivSearchTool())

            # 注册新的 Middleware 适配工具
            self.tools.register(NatureNewsTool())
        except ImportError as e:
            logger.warning(f"Builtin tools not found or failed to load: {e}")

    def _build_code_tools(self) -> list:
        """Build the FS tools passed to CodingAgent/CoderBot at request time."""
        try:
            from sage.studio.tools.code_writing import FileWriteTool, FileReadTool, ListDirectoryTool

            return [FileWriteTool(), FileReadTool(), ListDirectoryTool()]
        except ImportError as exc:
            logger.warning("code_writing tools unavailable: %s", exc)
            return []

    def _make_step(
        self, type: str, content: str, status: str = "completed", **metadata
    ) -> AgentStep:
        """创建执行步骤"""
        return AgentStep.create(
            type=type,
            content=content,
            status=status,
            **metadata,
        )

    async def process_message(
        self,
        message: str,
        session_id: str,
        history: list[dict[str, str]] | None = None,
        *,
        should_index: bool = False,
        metadata: dict[str, str] | None = None,
        evidence: list[dict[str, str]] | None = None,
    ) -> AsyncGenerator[AgentStep | str, None]:
        """Route a message through the shared workflow router and stream steps/results."""

        history = history or []
        metadata = metadata or {}
        evidence = evidence or []

        memory_service = get_memory_service(session_id)

        yield self._make_step("routing", "正在检索上下文并分析意图...", status="running")
        context_items = await memory_service.retrieve_context(message)

        decision = await self.workflow_router.decide(
            WorkflowRequest(
                query=message,
                session_id=session_id,
                history=history,
                metadata=metadata,
                should_index=should_index,
                evidence=evidence,
                context=[item.content for item in context_items[:3]],
            )
        )

        yield self._make_step(
            "routing",
            (
                f"路由: {decision.route.value} | 意图: {decision.intent.value} "
                f"(置信度 {decision.confidence:.2f})"
            ),
            matched_keywords=decision.matched_keywords,
            status="completed",
        )

        route_started_at = time.perf_counter()

        if decision.route == WorkflowRoute.SIMPLE_RAG:
            async for chunk in self._run_simple_rag(message, session_id, context_items, decision):
                yield chunk
            route_duration = time.perf_counter() - route_started_at
            logger.info(
                "route completed",
                extra={
                    "route": decision.route.value,
                    "intent": decision.intent.value,
                    "duration_ms": int(route_duration * 1000),
                    "should_index": decision.should_index,
                },
            )
            return

        if decision.route == WorkflowRoute.AGENTIC:
            async for chunk in self._run_agentic(message, session_id, history, decision):
                yield chunk
            route_duration = time.perf_counter() - route_started_at
            logger.info(
                "route completed",
                extra={
                    "route": decision.route.value,
                    "intent": decision.intent.value,
                    "duration_ms": int(route_duration * 1000),
                    "should_index": decision.should_index,
                },
            )
            return

        if decision.route == WorkflowRoute.CODE:
            async for chunk in self._run_coding(message, session_id, decision):
                yield chunk
            route_duration = time.perf_counter() - route_started_at
            logger.info(
                "route completed",
                extra={
                    "route": decision.route.value,
                    "intent": decision.intent.value,
                    "duration_ms": int(route_duration * 1000),
                },
            )
            return

        async for chunk in self._run_general_chat(message, session_id, context_items, decision):
            yield chunk
        route_duration = time.perf_counter() - route_started_at
        logger.info(
            "route completed",
            extra={
                "route": decision.route.value,
                "intent": decision.intent.value,
                "duration_ms": int(route_duration * 1000),
                "should_index": decision.should_index,
            },
        )

    async def _run_general_chat(
        self,
        message: str,
        session_id: str,
        context_items: list,
        decision: WorkflowDecision,
    ) -> AsyncGenerator[AgentStep | str, None]:
        memory_service = get_memory_service(session_id)
        yield self._make_step("response", "正在生成回复...", status="running")
        full_text = ""
        try:
            async for chunk in self._stream_gateway_chat(
                message=message,
                session_id=session_id,
                context_items=context_items,
                evidence=[],
            ):
                full_text += chunk
                yield chunk
        except RuntimeError as exc:
            logger.error("General chat gateway streaming failed: %s", exc)
            yield self._make_step("response", str(exc), status="failed")
            yield f"[Error] {exc}"
            return

        if full_text:
            await memory_service.add_interaction(message, full_text)
            yield self._make_step("response", "回复完成", status="completed")
        else:
            yield "(LLM returned empty response. The model may not be loaded yet.)"

    async def _run_simple_rag(
        self,
        message: str,
        session_id: str,
        context_items: list,
        decision: WorkflowDecision,
    ) -> AsyncGenerator[AgentStep | str, None]:
        memory_service = get_memory_service(session_id)
        yield self._make_step("retrieval", "正在检索知识库...", status="running")

        try:
            km_results = await self.knowledge_manager.search(message, limit=4, score_threshold=0.4)
        except Exception as exc:
            logger.warning(f"Knowledge search failed: {exc}")
            km_results = []

        evidence_payload = [
            {
                "content": res.content,
                "score": res.score,
                "source": res.source,
                "metadata": res.metadata,
            }
            for res in km_results
        ]

        if evidence_payload:
            yield self._make_step(
                "retrieval",
                f"检索到 {len(evidence_payload)} 条知识库证据",
                status="completed",
                evidence=evidence_payload,
            )
        else:
            yield self._make_step("retrieval", "未找到知识库证据，继续对话", status="completed")

        if evidence_payload:
            await memory_service.add_evidence_batch(
                evidence_payload, {"route": decision.route.value}
            )

            if decision.should_index:
                try:
                    await self.knowledge_manager.ingest_texts(
                        [ev.get("content", "") for ev in evidence_payload],
                        source_name="agentic_evidence",
                        metadata={"session_id": session_id, "route": decision.route.value},
                    )
                except Exception as exc:
                    logger.warning("Failed to ingest evidence into vector store: %s", exc)

        yield self._make_step("response", "正在生成回复...", status="running")
        full_text = ""
        try:
            async for chunk in self._stream_gateway_chat(
                message=message,
                session_id=session_id,
                context_items=context_items,
                evidence=evidence_payload,
            ):
                full_text += chunk
                yield chunk
        except RuntimeError as exc:
            logger.error("RAG gateway streaming failed: %s", exc)
            yield self._make_step("response", str(exc), status="failed")
            yield f"[Error] {exc}"
            return

        if full_text:
            await memory_service.add_interaction(message, full_text)
            yield self._make_step("response", "回复完成", status="completed")
        else:
            yield "(LLM returned empty response. The model may not be loaded yet.)"

    async def _raw_gateway_call(self, messages: list[dict], session_id: str = "") -> str:
        """Low-level gateway call: takes a full messages list, returns completion text.

        Used as the injected ``llm_callable`` for CoderBot so the bot stays L3-neutral.
        """
        base_url = self._resolve_gateway_base_url()
        try:
            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                resp = await client.post(
                    f"{base_url}/v1/chat/completions",
                    json={"model": "sage-default", "messages": messages, "stream": False,
                          "session_id": session_id},
                )
        except httpx.ConnectError:
            raise RuntimeError(
                f"Cannot connect to LLM Gateway at {base_url}. "
                "Please ensure the gateway is running (sage gateway start)."
            )
        except httpx.TimeoutException:
            raise RuntimeError("LLM Gateway timed out (120s).")
        if resp.status_code != 200:
            raise RuntimeError(f"LLM Gateway error ({resp.status_code}): {resp.text[:200]}")
        data = resp.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")

    async def _run_coding(
        self,
        message: str,
        session_id: str,
        decision: WorkflowDecision,
    ) -> AsyncGenerator[AgentStep | str, None]:
        """Route CODE intent to CodingAgent backed by CoderBot (L3)."""
        import functools

        # Build per-request llm_callable with session_id baked in
        llm_callable = functools.partial(self._raw_gateway_call, session_id=session_id)

        agent = CodingAgent(tools=self._code_tools, llm_callable=llm_callable)
        memory_service = get_memory_service(session_id)
        full_response = ""

        async for item in agent.run(message):
            if isinstance(item, str):
                full_response += item
            yield item

        if full_response:
            await memory_service.add_interaction(message, full_response)

    async def _run_agentic(
        self,
        message: str,
        session_id: str,
        history: list[dict],
        decision: WorkflowDecision,
    ) -> AsyncGenerator[AgentStep | str, None]:
        memory_service = get_memory_service(session_id)
        full_response = ""
        evidence_payload: list[dict[str, object]] = []
        async for item in self.researcher_agent.run(message, history):
            if hasattr(item, "metadata"):
                raw_results = (
                    item.metadata.get("raw_results") if hasattr(item, "metadata") else None
                )
                if raw_results:
                    for res in raw_results:
                        if not isinstance(res, dict):
                            continue
                        content = res.get("content")
                        if not content:
                            continue
                        try:
                            score_val = float(res.get("score", 1.0))
                        except Exception:
                            score_val = 1.0
                        evidence_payload.append(
                            {
                                "content": content,
                                "score": score_val,
                                "source": res.get("source") or "agentic_tool",
                                "metadata": res.get("metadata") or {},
                            }
                        )
            if isinstance(item, str):
                full_response += item
            yield item

        if evidence_payload:
            await memory_service.add_evidence_batch(
                evidence_payload,
                {"route": decision.route.value},
            )

            if decision.should_index:
                try:
                    await self.knowledge_manager.ingest_texts(
                        [ev.get("content", "") for ev in evidence_payload],
                        source_name="agentic_evidence",
                        metadata={"session_id": session_id, "route": decision.route.value},
                    )
                except Exception as exc:
                    logger.warning("Failed to ingest agentic evidence into vector store: %s", exc)

        if full_response:
            await memory_service.add_interaction(message, full_response)

    async def _call_gateway_chat(
        self,
        *,
        message: str,
        session_id: str,
        context_items: list,
        evidence: list[dict],
    ) -> str:
        """Call the LLM Gateway non-streaming (delegates to _call_gateway_chat_non_streaming)."""
        return await self._call_gateway_chat_non_streaming(
            message=message,
            session_id=session_id,
            context_items=context_items,
            evidence=evidence,
        )

    async def _stream_gateway_chat(
        self,
        *,
        message: str,
        session_id: str,
        context_items: list,
        evidence: list[dict],
    ) -> AsyncGenerator[str, None]:
        """Stream token chunks from the LLM Gateway via SSE.

        Yields each ``content`` delta as a plain string as soon as it arrives,
        enabling the caller to forward chunks to the frontend progressively.

        Raises:
            RuntimeError: When the gateway is unreachable, times out, or errors.
        """
        context_text = self._format_context(context_items, evidence)
        messages: list[dict] = []
        if context_text:
            messages.append({"role": "system", "content": context_text})
        messages.append({"role": "user", "content": message})

        base_url = self._resolve_gateway_base_url()
        try:
            async with httpx.AsyncClient(timeout=90.0, trust_env=False) as client:
                async with client.stream(
                    "POST",
                    f"{base_url}/v1/chat/completions",
                    json={
                        "model": "sage-default",
                        "messages": messages,
                        "stream": True,
                        "session_id": session_id,
                    },
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        detail = body.decode(errors="replace")[:200]
                        raise RuntimeError(
                            f"LLM Gateway error ({resp.status_code}): {detail}"
                        )
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            token = chunk["choices"][0]["delta"].get("content", "")
                            if token:
                                yield token
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        except httpx.ConnectError:
            raise RuntimeError(
                f"Cannot connect to LLM Gateway at {base_url}. "
                "Please ensure the gateway is running (sage gateway start)."
            )
        except httpx.TimeoutException:
            raise RuntimeError(
                "LLM Gateway streaming request timed out (90s). "
                "The LLM engine may be overloaded or unresponsive."
            )
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"LLM Gateway streaming call failed: {exc}")

    async def _call_gateway_chat_non_streaming(
        self,
        *,
        message: str,
        session_id: str,
        context_items: list,
        evidence: list[dict],
    ) -> str:
        """Call the LLM Gateway /v1/chat/completions with optional context/evidence.

        Raises:
            RuntimeError: When the gateway is unreachable or returns an error.
        """

        context_text = self._format_context(context_items, evidence)
        messages = []
        if context_text:
            messages.append({"role": "system", "content": context_text})
        messages.append({"role": "user", "content": message})

        base_url = self._resolve_gateway_base_url()
        try:
            async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
                resp = await client.post(
                    f"{base_url}/v1/chat/completions",
                    json={
                        "model": "sage-default",
                        "messages": messages,
                        "stream": False,
                        "session_id": session_id,
                    },
                )
        except httpx.ConnectError:
            raise RuntimeError(
                f"Cannot connect to LLM Gateway at {base_url}. "
                "Please ensure the gateway is running (sage gateway start)."
            )
        except httpx.TimeoutException:
            raise RuntimeError(
                "LLM Gateway request timed out (60s). "
                "The LLM engine may be overloaded or unresponsive."
            )
        except Exception as exc:
            raise RuntimeError(f"LLM Gateway call failed: {exc}")

        if resp.status_code != 200:
            detail = resp.text[:200] if resp.text else f"HTTP {resp.status_code}"
            raise RuntimeError(f"LLM Gateway error ({resp.status_code}): {detail}")

        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            logger.warning("Gateway returned empty content: %s", data)
        return content

    def _resolve_gateway_base_url(self) -> str:
        """Resolve gateway base URL with local-first preference."""

        env_url = os.environ.get("SAGE_GATEWAY_BASE_URL") or os.environ.get("GATEWAY_BASE_URL")
        if env_url:
            return env_url.rstrip("/")

        host = os.environ.get("SAGE_GATEWAY_HOST")
        if host:
            return f"http://{host}:{StudioPorts.GATEWAY}"

        # Local-first: try gateway default port
        return f"http://127.0.0.1:{StudioPorts.GATEWAY}"

    def _format_context(self, context_items: list, evidence: list[dict]) -> str:
        """Build a compact context string for the system prompt."""

        context_snippets = []
        for item in context_items[:3]:
            try:
                snippet = item.content if len(item.content) <= 400 else f"{item.content[:400]}..."
                context_snippets.append(f"Memory: {snippet}")
            except Exception:
                continue

        for ev in evidence[:3]:
            content = ev.get("content")
            if content:
                snippet = content if len(content) <= 400 else f"{content[:400]}..."
                source = ev.get("source") or "knowledge"
                context_snippets.append(f"Evidence ({source}): {snippet}")

        if not context_snippets:
            return ""

        return "\n".join(context_snippets)


# 单例
_orchestrator: AgentOrchestrator | None = None


def get_orchestrator() -> AgentOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator
