"""Chat Pipeline-as-Service for SAGE Studio.

Wraps a SAGE DataStream pipeline using PipelineBridge so that the Studio
backend can call it synchronously per chat request.  LLM calls happen
exclusively inside the Generator operator — the backend never contacts
the gateway directly.

Pipeline dataflow::

    Source → Intent → ContextRetrieval → Prompt → Generate → Package → Sink

Stages:
    - **IntentStage**: Classifies user intent via ``IntentClassifier`` +
      ``WorkflowRouter`` and attaches route metadata to the payload.
    - **ContextRetrievalStage**: Retrieves context from NeuroMem (memory)
      and SageVDB (knowledge base).  KB search is conditional on the route
      decided by IntentStage.
    - **PromptStage**: Wraps ``QAPromptor`` to build LLM messages with
      context.
    - **GeneratorStage**: Wraps ``OpenAIGenerator`` targeting
      sagellm-gateway (resolved via ``StudioPorts``).
    - **PackageResultStage**: Normalises output into
      ``{"text": str, "meta": {...}}`` including intent metadata.

Layer: L6 (sage-studio)
Dependencies:
    - sage-kernel  (LocalEnvironment, PipelineBridge, PipelineServiceSource/Sink)
    - sage-agentic  (IntentClassifier, WorkflowRouter)
    - sage-middleware  (QAPromptor, OpenAIGenerator)
    - sage-studio services  (MemoryIntegrationService, KnowledgeManager)
"""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
from typing import Any

from sage.common.core.functions import MapFunction, SinkFunction
from sage.kernel.api.local_environment import LocalEnvironment
from sage.kernel.api.service.pipeline_service import (
    PipelineBridge,
    PipelineService,
    PipelineServiceSink,
    PipelineServiceSource,
)
from sage.kernel.runtime.communication.packet import StopSignal
from sage.middleware.operators.rag.generator import OpenAIGenerator
from sage.middleware.operators.rag.promptor import QAPromptor

from sage.studio.config.ports import StudioPorts
from sage_libs.sage_agentic.intent import IntentClassifier, UserIntent
from sage_libs.sage_agentic.workflows.router import (
    WorkflowDecision,
    WorkflowRequest,
    WorkflowRoute,
    WorkflowRouter,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pipeline operators (thin wrappers keeping response_queue propagation)
# ---------------------------------------------------------------------------


class IntentStage(MapFunction):
    """Classify user intent and decide the workflow route.

    Wraps ``IntentClassifier`` + ``WorkflowRouter.decide()`` as a pipeline
    operator.  Attaches ``intent``, ``route``, ``confidence``, and
    ``matched_keywords`` to the payload so that downstream stages can
    adapt their behaviour (e.g. skip retrieval for general chat).
    """

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self._classifier = IntentClassifier(mode="llm")
        self._router = WorkflowRouter(self._classifier)

        # Log IntentClassifier initialization details
        self.logger.info(f"IntentStage initialized with mode='llm', classifier={self._classifier}")

    def execute(self, payload: dict[str, Any] | StopSignal | None) -> dict[str, Any] | StopSignal | None:
        if payload is None or isinstance(payload, StopSignal):
            return payload

        self.logger.info("IntentStage: Received payload")

        try:
            query: str = payload.get("query", payload.get("prompt", ""))
            history: list[dict[str, str]] = payload.get("history", [])
            session_id: str = payload.get("session_id", "")

            import asyncio

            loop = asyncio.new_event_loop()
            decision: WorkflowDecision = loop.run_until_complete(
                self._router.decide(
                    WorkflowRequest(
                        query=query,
                        session_id=session_id,
                        history=history,
                    )
                )
            )
            loop.close()

            payload["intent"] = decision.intent.value
            payload["route"] = decision.route.value
            payload["confidence"] = decision.confidence
            payload["matched_keywords"] = decision.matched_keywords

            self.logger.info(
                "Intent: %s  Route: %s  Confidence: %.2f  Keywords: %s",
                decision.intent.value,
                decision.route.value,
                decision.confidence,
                decision.matched_keywords,
            )
            return payload
        except Exception as e:
            self.logger.error(f"IntentStage failed: {e}", exc_info=True)
            # Return payload with default values on error
            payload.setdefault("intent", "question")
            payload.setdefault("route", "general")
            payload.setdefault("confidence", 0.0)
            payload.setdefault("matched_keywords", [])
            return payload


class ContextRetrievalStage(MapFunction):
    """Retrieve context from NeuroMem memory + SageVDB knowledge base.

    Merges results from two sources:
    1. ``MemoryIntegrationService.retrieve_context()`` — session memory
    2. ``KnowledgeManager.search()`` — SageVDB-backed vector store

    Attaches ``retrieval_results`` and ``context`` keys to the payload so
    that downstream ``QAPromptor`` can consume them.
    """

    def __init__(self, top_k_memory: int = 3, top_k_knowledge: int = 4, **kwargs: Any):
        super().__init__(**kwargs)
        self._top_k_memory = top_k_memory
        self._top_k_knowledge = top_k_knowledge

    def execute(self, payload: dict[str, Any] | StopSignal | None) -> dict[str, Any] | StopSignal | None:
        if payload is None or isinstance(payload, StopSignal):
            return payload

        self.logger.info("ContextRetrievalStage: Received payload")

        route = payload.get("route", WorkflowRoute.GENERAL.value)
        query: str = payload.get("query", payload.get("prompt", ""))
        session_id: str = payload.get("session_id", "")

        self.logger.info(f"ContextRetrievalStage: route={route}, query='{query[:50]}...'")

        retrieval_results: list[str] = []

        # --- 1. NeuroMem memory retrieval (always, if session exists) ---
        if session_id:
            try:
                from sage.studio.services.memory_integration import get_memory_service

                memory_service = get_memory_service(session_id)
                import asyncio

                loop = asyncio.new_event_loop()
                context_items = loop.run_until_complete(
                    memory_service.retrieve_context(query, max_items=self._top_k_memory)
                )
                loop.close()

                for item in context_items:
                    snippet = item.content if len(item.content) <= 400 else f"{item.content[:400]}..."
                    retrieval_results.append(snippet)

                self.logger.info(f"ContextRetrievalStage: Retrieved {len(context_items)} items from memory")
            except Exception as e:
                self.logger.warning(f"ContextRetrievalStage: Memory retrieval failed: {e}")
                # Continue without memory context

        # --- 2. SageVDB-backed knowledge base retrieval ---
        # Only perform KB search for routes that need evidence
        if route in (WorkflowRoute.SIMPLE_RAG.value, WorkflowRoute.CODE.value, WorkflowRoute.AGENTIC.value):
            self.logger.info(f"ContextRetrievalStage: Performing KB search (route={route})")
            try:
                from sage.studio.services.knowledge_manager import KnowledgeManager

                km = KnowledgeManager()
                import asyncio

                loop = asyncio.new_event_loop()
                km_results = loop.run_until_complete(
                    km.search(query, limit=self._top_k_knowledge, score_threshold=0.4)
                )
                loop.close()

                self.logger.info(f"ContextRetrievalStage: KB search returned {len(km_results)} results")
                for i, res in enumerate(km_results):
                    self.logger.info(f"  [{i}] score={res.score:.3f}, source={res.source}, content={res.content[:80]}...")
                    retrieval_results.append(res.content)
            except Exception as e:
                self.logger.error(f"ContextRetrievalStage: Knowledge base retrieval failed: {e}", exc_info=True)
                # Continue without KB context
        else:
            self.logger.info(f"ContextRetrievalStage: Skipping KB search (route={route}, not RAG/CODE/AGENTIC)")

        self.logger.info(f"ContextRetrievalStage: Total {len(retrieval_results)} retrieval results")
        payload["retrieval_results"] = retrieval_results
        return payload


class PromptStage(MapFunction):
    """Wrap ``QAPromptor`` while propagating pipeline metadata (response_queue, etc.)."""

    def __init__(self, config: dict[str, Any] | None = None, **kwargs: Any):
        super().__init__(**kwargs)
        self._promptor = QAPromptor(config or {})

    def execute(self, payload: dict[str, Any] | StopSignal | None) -> dict[str, Any] | StopSignal | None:
        if payload is None or isinstance(payload, StopSignal):
            return payload

        self.logger.info("PromptStage: Received payload")

        response_queue = payload.get("_response_queue")

        # QAPromptor expects dict with query + retrieval_results
        prompt_result = self._promptor.execute(payload)

        # QAPromptor returns [original_data, prompt_messages]
        if isinstance(prompt_result, (list, tuple)) and len(prompt_result) >= 2:
            prompt_messages = prompt_result[1]
        else:
            prompt_messages = prompt_result

        prepared = dict(payload)
        prepared["prompt"] = prompt_messages
        if response_queue is not None:
            prepared["_response_queue"] = response_queue
        return prepared


class GeneratorStage(MapFunction):
    """Invoke ``OpenAIGenerator`` (pointing at sagellm-gateway) inside the pipeline.

    The gateway URL is resolved from ``StudioPorts`` — never hardcoded.
    """

    def __init__(self, config: dict[str, Any] | None = None, **kwargs: Any):
        super().__init__(**kwargs)
        config = config or {}
        generator_config = self._build_generator_config(config)
        self._generator = OpenAIGenerator(generator_config)

    @staticmethod
    def _build_generator_config(config: dict[str, Any]) -> dict[str, Any]:
        """Build OpenAIGenerator config, resolving base_url from StudioPorts."""
        base_url = config.get("base_url")
        if not base_url:
            gateway_host = os.environ.get("SAGE_GATEWAY_HOST", "127.0.0.1")
            base_url = f"http://{gateway_host}:{StudioPorts.GATEWAY}/v1"

        model_name = config.get("model_name") or os.environ.get(
            "SAGE_CHAT_MODEL", "sage-default"
        )
        api_key = config.get("api_key") or os.environ.get("OPENAI_API_KEY", "EMPTY")

        return {
            "method": "openai",
            "model_name": model_name,
            "base_url": base_url,
            "api_key": api_key,
            "max_tokens": config.get("max_tokens", 2048),
            "temperature": config.get("temperature", 0.7),
        }

    def execute(self, payload: dict[str, Any] | StopSignal | None) -> dict[str, Any] | StopSignal | None:
        if payload is None or isinstance(payload, StopSignal):
            return payload

        response_queue = payload.get("_response_queue")
        prompt = payload.get("prompt")

        self.logger.info(f"GeneratorStage: About to call LLM with prompt type={type(prompt)}")

        try:
            # OpenAIGenerator expects [original_data, prompt]
            result = self._generator.execute([payload, prompt])

            self.logger.info(f"GeneratorStage: Got result from LLM, type={type(result)}")

            if isinstance(result, dict):
                result.setdefault("query", payload.get("query", ""))
                result.setdefault("generated", "")
                if response_queue is not None:
                    result["_response_queue"] = response_queue
                return result

            # Fallback: wrap scalar result
            return {
                "query": payload.get("query", ""),
                "generated": str(result),
                "_response_queue": response_queue,
            }
        except Exception as e:
            self.logger.error(f"GeneratorStage failed: {e}", exc_info=True)
            # Return error message as generated text
            return {
                "query": payload.get("query", ""),
                "generated": f"[Error] Failed to generate response: {str(e)}",
                "_response_queue": response_queue,
                "error": str(e),
            }


class PackageResultStage(MapFunction):
    """Normalise generator output into the final ``{text, meta}`` schema."""

    def execute(self, payload: dict[str, Any] | StopSignal | None) -> dict[str, Any] | StopSignal | None:
        if payload is None or isinstance(payload, StopSignal):
            return payload

        response_queue = payload.get("_response_queue")

        text = payload.get("generated", "")
        meta = {
            "query": payload.get("query", ""),
            "model": payload.get("model", ""),
            "intent": payload.get("intent", ""),
            "route": payload.get("route", ""),
            "confidence": payload.get("confidence", 0.0),
            "matched_keywords": payload.get("matched_keywords", []),
            "retrieval_count": len(payload.get("retrieval_results", [])),
        }

        result: dict[str, Any] = {"text": text, "meta": meta}
        if response_queue is not None:
            result["_response_queue"] = response_queue
        return result


# ---------------------------------------------------------------------------
# ChatPipelineService — lifecycle management
# ---------------------------------------------------------------------------


class ChatPipelineService:
    """Manages a long-lived SAGE DataStream pipeline for chat.

    Usage::

        service = ChatPipelineService()
        service.start()

        result = service.run({
            "prompt": "What is SAGE?",
            "session_id": "abc-123",
        })
        # result == {"text": "...", "meta": {...}}

        service.stop()
    """

    def __init__(
        self,
        generator_config: dict[str, Any] | None = None,
        promptor_config: dict[str, Any] | None = None,
        request_timeout: float = 600.0,  # Increased to 10min to allow KB loading on first request
    ):
        self._generator_config = generator_config or {}
        self._promptor_config = promptor_config or {}
        self._request_timeout = request_timeout

        self._bridge: PipelineBridge | None = None
        self._env: LocalEnvironment | None = None
        self._started = False
        self._lock = threading.Lock()

    # -- public interface ---------------------------------------------------

    def start(self) -> None:
        """Build and submit the SAGE pipeline.

        Must be called from the main thread (SAGE JobManager registers signal
        handlers which require the main thread).  FastAPI startup hooks satisfy
        this requirement.
        """
        with self._lock:
            if self._started:
                logger.info("ChatPipelineService already started")
                return

            logger.info("ChatPipelineService starting...")

            self._bridge = PipelineBridge()
            self._env = LocalEnvironment("studio_chat_pipeline")

            # Register the bridge-backed service so that it can be used via
            # call_service() from other pipelines if needed in the future.
            self._env.register_service(
                "chat_pipeline",
                PipelineService,
                self._bridge,
                request_timeout=self._request_timeout,
            )

            # Assemble the DataStream pipeline:
            #   Source → Intent → ContextRetrieval → Prompt → Generate → Package → Sink
            logger.info("ChatPipelineService: Assembling pipeline operators...")
            (
                self._env.from_source(PipelineServiceSource, self._bridge)
                .map(IntentStage)
                .map(ContextRetrievalStage)
                .map(PromptStage, self._promptor_config)
                .map(GeneratorStage, self._generator_config)
                .map(PackageResultStage)
                .sink(PipelineServiceSink)
            )

            # Submit pipeline — autostop=False so it keeps polling for requests.
            # env.submit() is non-blocking when autostop=False.
            logger.info("ChatPipelineService: Submitting pipeline (autostop=False)...")
            self._env.submit(autostop=False)
            self._started = True
            logger.info("ChatPipelineService started successfully")

            # Give pipeline time to start
            import time
            time.sleep(0.5)

    def stop(self) -> None:
        """Gracefully shut down the pipeline."""
        with self._lock:
            if not self._started:
                return
            if self._bridge is not None:
                self._bridge.close()
            self._started = False
            logger.info("ChatPipelineService stopped")

    def run(self, request: dict[str, Any]) -> dict[str, Any]:
        """Submit a chat request and block until the pipeline returns a result.

        Args:
            request: Must contain at least ``prompt`` (str).  Optional keys:
                     ``session_id``, ``history``, ``model``, ``stream``.

        Returns:
            ``{"text": str, "meta": dict}``

        Raises:
            RuntimeError: If the service has not been started.
            TimeoutError: If the pipeline does not respond within the timeout.
        """
        if not self._started or self._bridge is None:
            raise RuntimeError("ChatPipelineService is not running. Call start() first.")

        # Normalise: callers use "prompt" but operators use "query"
        payload: dict[str, Any] = dict(request)
        if "query" not in payload and "prompt" in payload:
            payload["query"] = payload.pop("prompt")

        logger.info("ChatPipelineService.run: Submitting payload to pipeline")
        response_q = self._bridge.submit(payload)

        logger.info(f"ChatPipelineService.run: Waiting for result (timeout={self._request_timeout}s)")
        try:
            result = response_q.get(timeout=self._request_timeout)
            logger.info(f"ChatPipelineService.run: Got result with keys: {list(result.keys()) if isinstance(result, dict) else type(result)}")

            # Validate result structure
            if not isinstance(result, dict):
                logger.warning(f"Pipeline returned non-dict result: {type(result)}")
                result = {"text": str(result), "meta": {}}
            elif "text" not in result:
                logger.warning(f"Pipeline result missing 'text' key, keys: {result.keys()}")
                result.setdefault("text", "")
                result.setdefault("meta", {})

            return result
        except queue.Empty:
            logger.error(f"ChatPipelineService.run: Timeout after {self._request_timeout}s")
            raise TimeoutError(f"Pipeline did not respond within {self._request_timeout}s")
        except Exception as e:
            logger.error(f"ChatPipelineService.run: Error getting result - {e}", exc_info=True)
            raise


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_instance: ChatPipelineService | None = None
_instance_lock = threading.Lock()


def get_chat_pipeline_service(
    *,
    generator_config: dict[str, Any] | None = None,
    promptor_config: dict[str, Any] | None = None,
) -> ChatPipelineService:
    """Return (and lazily start) the module-level ChatPipelineService singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = ChatPipelineService(
                generator_config=generator_config,
                promptor_config=promptor_config,
            )
            _instance.start()
        return _instance
