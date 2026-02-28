from __future__ import annotations

import asyncio
import json
import logging
import resource
import time
import urllib.request
from typing import Any

from sage.studio.config.vida import VidaRuntimeConfig, load_vida_runtime_config

logger = logging.getLogger(__name__)


class _SkippedVidaResult:
    def __init__(self, event_id: str) -> None:
        self.message_id = event_id
        self.answer = ""
        self.error = "trigger is disabled"

    @property
    def ok(self) -> bool:
        return False


def _build_studio_trigger_manager_class(base_trigger_manager: type[Any]) -> type[Any]:
    class _StudioTriggerManager(base_trigger_manager):
        def __init__(self, vida_agent: Any, disabled_sources: set[str]) -> None:
            super().__init__(vida_agent)
            self._disabled_sources = disabled_sources

        async def _dispatch_event(self, event: Any) -> Any:
            if getattr(event, "source", "") in self._disabled_sources:
                return _SkippedVidaResult(getattr(event, "event_id", ""))
            return await super()._dispatch_event(event)

    return _StudioTriggerManager


class _GatewayJSONModelClient:
    def __init__(self, *, model: str, gateway_url: str, timeout_seconds: float = 15.0) -> None:
        self._model = model
        self._gateway_url = gateway_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def generate(self, messages: list[dict[str, Any]]) -> str:
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.2,
            "stream": False,
        }
        request = urllib.request.Request(
            f"{self._gateway_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("Gateway returned empty choices")
        message = choices[0].get("message") or {}
        content = str(message.get("content") or "")
        if not content:
            raise RuntimeError("Gateway returned empty content")
        return content


class VidaRuntimeManager:
    def __init__(self, config: VidaRuntimeConfig | None = None) -> None:
        self._config = config or load_vida_runtime_config()
        self._agent: Any | None = None
        self._trigger_manager: Any | None = None
        self._trigger_names: set[str] = set()
        self._disabled_trigger_names: set[str] = set()
        self._reflection_history: list[dict[str, Any]] = []
        self._started_at_monotonic: float | None = None
        self._lock = asyncio.Lock()

    @property
    def config(self) -> VidaRuntimeConfig:
        return self._config

    def reload_config(self) -> VidaRuntimeConfig:
        self._config = load_vida_runtime_config()
        return self._config

    async def start(self) -> dict[str, Any]:
        async with self._lock:
            if self.is_running:
                return self.status(started=False)

            from sage.middleware.operators.vida import (
                TriggerManager,
                VidaAgent,
                VidaMemoryBridge,
                VidaReflectionEngine,
            )
            from sage_libs.sage_agentic.vida.async_react_loop import AsyncReActLoop

            from sage.studio.api.chat import _auto_resolve_chat_model
            from sage.studio.api.llm import _get_gateway_url

            model_name = self._config.model.strip() or _auto_resolve_chat_model()
            if not model_name:
                raise RuntimeError("Vida runtime start failed: no chat model available")

            gateway_url = self._config.gateway_url.strip() or _get_gateway_url()
            if not gateway_url:
                raise RuntimeError("Vida runtime start failed: gateway url is empty")

            llm_client = _GatewayJSONModelClient(model=model_name, gateway_url=gateway_url)
            react_loop = AsyncReActLoop(config=dict(self._config.react_loop), model=llm_client)

            memory_bridge = VidaMemoryBridge(
                config=self._config.memory.model_dump(exclude_none=True)
            )

            reflection_engine = None
            if self._config.reflection.enabled:
                reflection_engine = VidaReflectionEngine(
                    memory_bridge=memory_bridge,
                    llm=llm_client,
                    config={
                        "interval_seconds": self._config.reflection.interval_seconds,
                        "top_k_episodes": self._config.reflection.top_k_episodes,
                        "reflection_query": self._config.reflection.reflection_query,
                    },
                )

            self._agent = VidaAgent(
                react_loop=react_loop,
                memory_bridge=memory_bridge,
                reflection_engine=reflection_engine,
                config=self._config.agent.model_dump(),
            )
            await self._agent.start()

            self._trigger_manager = None
            self._trigger_names = set()
            self._disabled_trigger_names = set()
            self._reflection_history = []
            if self._config.trigger.enabled:
                studio_trigger_manager = _build_studio_trigger_manager_class(TriggerManager)
                trigger_manager = studio_trigger_manager(
                    self._agent,
                    disabled_sources=self._disabled_trigger_names,
                )
                await trigger_manager.start()
                for name, seconds in self._config.trigger.interval_triggers.items():
                    await trigger_manager.register_interval_trigger(
                        name=name, interval_seconds=float(seconds)
                    )
                    self._trigger_names.add(name)
                self._trigger_manager = trigger_manager

            if (
                self._agent is not None
                and getattr(self._agent, "_reflection_engine", None) is not None
            ):
                reflection_engine = self._agent._reflection_engine
                original_reflect = reflection_engine.reflect

                async def _recording_reflect() -> list[str]:
                    insights = await original_reflect()
                    if insights:
                        ts = float(reflection_engine.last_reflect_timestamp or time.time())
                        self._reflection_history.append(
                            {
                                "timestamp": ts,
                                "summary": insights[0][:200],
                                "insights": insights,
                            }
                        )
                        if len(self._reflection_history) > 200:
                            self._reflection_history = self._reflection_history[-200:]
                    return insights

                reflection_engine.reflect = _recording_reflect

            self._started_at_monotonic = time.monotonic()
            logger.info("Vida runtime started: model=%s", model_name)
            return self.status(started=True)

    async def stop(self, *, drain: bool = True) -> dict[str, Any]:
        async with self._lock:
            if not self.is_running:
                return self.status(stopped=False)

            trigger_manager = self._trigger_manager
            self._trigger_manager = None
            self._trigger_names = set()
            self._disabled_trigger_names = set()
            if trigger_manager is not None and trigger_manager.is_running:
                await trigger_manager.stop()

            if self._agent is not None:
                await self._agent.shutdown(drain=drain)

            self._agent = None
            self._started_at_monotonic = None
            logger.info("Vida runtime stopped")
            return self.status(stopped=True)

    async def trigger(
        self, trigger_name: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not self.is_running or self._agent is None:
            raise RuntimeError("Vida runtime is not running")

        from sage.middleware.operators.vida import VidaEvent

        event = VidaEvent(
            event_type="manual",
            source=trigger_name,
            payload=payload or {},
        )

        if self._trigger_manager is not None:
            result = await self._trigger_manager.emit_event(event)
        else:
            result = await self._agent.handle_event(event)

        return {
            "trigger_name": trigger_name,
            "result_ok": bool(getattr(result, "ok", True)),
            "message_id": getattr(result, "message_id", ""),
            "answer": getattr(result, "answer", ""),
            "error": getattr(result, "error", ""),
        }

    @property
    def is_running(self) -> bool:
        return bool(self._agent is not None and self._agent.is_running)

    def status(self, *, started: bool | None = None, stopped: bool | None = None) -> dict[str, Any]:
        uptime_seconds = 0.0
        if self._started_at_monotonic is not None:
            uptime_seconds = max(0.0, time.monotonic() - self._started_at_monotonic)

        queue_depth = 0
        processed_count = 0
        failed_count = 0
        accepting = False
        if self._agent is not None:
            queue_depth = int(self._agent.pending_count)
            processed_count = int(self._agent.processed_count)
            failed_count = int(self._agent.failed_count)
            accepting = bool(self._agent.is_accepting)

        mem = resource.getrusage(resource.RUSAGE_SELF)
        memory_stats = {
            "ru_maxrss_kb": int(mem.ru_maxrss),
        }

        result: dict[str, Any] = {
            "state": "running" if self.is_running else "stopped",
            "accepting": accepting,
            "queue_depth": queue_depth,
            "processed_count": processed_count,
            "failed_count": failed_count,
            "uptime_seconds": round(uptime_seconds, 3),
            "memory_stats": memory_stats,
            "trigger_names": sorted(self._trigger_names),
            "disabled_trigger_names": sorted(self._disabled_trigger_names),
            "last_reflect_timestamp": self.last_reflect_timestamp,
        }
        if started is not None:
            result["started"] = started
        if stopped is not None:
            result["stopped"] = stopped
        return result

    @property
    def last_reflect_timestamp(self) -> float:
        if self._agent is None:
            return 0.0
        reflection_engine = getattr(self._agent, "_reflection_engine", None)
        if reflection_engine is None:
            return 0.0
        return float(getattr(reflection_engine, "last_reflect_timestamp", 0.0) or 0.0)

    def list_triggers(self) -> list[dict[str, Any]]:
        triggers: list[dict[str, Any]] = []
        for name in sorted(self._trigger_names):
            triggers.append(
                {
                    "name": name,
                    "type": "interval",
                    "enabled": name not in self._disabled_trigger_names,
                }
            )
        return triggers

    def set_trigger_enabled(self, trigger_name: str, enabled: bool) -> dict[str, Any]:
        if trigger_name not in self._trigger_names:
            raise RuntimeError(f"Unknown trigger: {trigger_name}")

        if enabled:
            self._disabled_trigger_names.discard(trigger_name)
        else:
            self._disabled_trigger_names.add(trigger_name)

        return {
            "name": trigger_name,
            "enabled": trigger_name not in self._disabled_trigger_names,
        }

    def list_reflections(self, *, limit: int = 20) -> list[dict[str, Any]]:
        size = max(1, min(int(limit), 200))
        return list(reversed(self._reflection_history[-size:]))

    def _get_memory_bridge(self) -> Any:
        if not self.is_running or self._agent is None:
            raise RuntimeError("Vida runtime is not running")
        return self._agent._memory_bridge

    async def recall_memory(
        self,
        *,
        query: str,
        top_k: int,
        layer: str | None = None,
    ) -> dict[str, Any]:
        bridge = self._get_memory_bridge()
        normalized_layer = (layer or "all").strip().lower()
        top_k = max(1, min(int(top_k), 100))

        layers = (
            ["working", "episodic", "semantic"] if normalized_layer == "all" else [normalized_layer]
        )
        for candidate in layers:
            if candidate not in {"working", "episodic", "semantic"}:
                raise RuntimeError(f"Unsupported memory layer: {candidate}")

        results: dict[str, list[dict[str, Any]]] = {}
        if "working" in layers:
            results["working"] = await bridge.recall_working(query=query, top_k=top_k)
        if "episodic" in layers:
            results["episodic"] = await bridge.recall_episodic(query=query, top_k=top_k)
        if "semantic" in layers:
            results["semantic"] = await bridge.recall_semantic(query=query, top_k=top_k)

        return {
            "query": query,
            "top_k": top_k,
            "layer": normalized_layer,
            "results": results,
        }

    async def list_memory(
        self,
        *,
        layer: str,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        bridge = self._get_memory_bridge()
        normalized_layer = layer.strip().lower()
        if normalized_layer not in {"working", "episodic", "semantic"}:
            raise RuntimeError(f"Unsupported memory layer: {normalized_layer}")

        page = max(1, int(page))
        page_size = max(1, min(int(page_size), 100))
        end_index = page * page_size
        start_index = end_index - page_size

        if normalized_layer == "working":
            all_items = await bridge.recall_working(query="", top_k=end_index)
        elif normalized_layer == "episodic":
            all_items = await bridge.recall_episodic(query="", top_k=end_index)
        else:
            all_items = await bridge.recall_semantic(query="", top_k=end_index)

        page_items = all_items[start_index:end_index]
        total = len(all_items)
        return {
            "layer": normalized_layer,
            "page": page,
            "page_size": page_size,
            "total": total,
            "items": page_items,
        }

    async def memory_usage(self) -> dict[str, Any]:
        bridge = self._get_memory_bridge()
        top_k = 200
        working = await bridge.recall_working(query="", top_k=top_k)
        episodic = await bridge.recall_episodic(query="", top_k=top_k)
        semantic = await bridge.recall_semantic(query="", top_k=top_k)
        return {
            "working_count": len(working),
            "episodic_count": len(episodic),
            "semantic_count": len(semantic),
        }


_VIDA_RUNTIME: VidaRuntimeManager | None = None


def get_vida_runtime_manager() -> VidaRuntimeManager:
    global _VIDA_RUNTIME
    if _VIDA_RUNTIME is None:
        _VIDA_RUNTIME = VidaRuntimeManager()
    return _VIDA_RUNTIME


__all__ = ["VidaRuntimeManager", "get_vida_runtime_manager"]
