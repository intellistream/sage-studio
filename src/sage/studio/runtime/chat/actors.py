from __future__ import annotations

import asyncio
import queue
import threading
import time
from collections.abc import Generator
from typing import Any, cast

from sage.flownet.core.exceptions import ExceptionDecision, ExceptionEvent
from sage.flownet.core.stream_event import StreamEvent

from sage.studio.contracts.models import StageEvent, StageEventState
from sage.studio.runtime.adapters import (
    ChatCompletionResult,
    InferenceCallError,
    request_chat_completion,
)
from sage.studio.runtime.endpoints import ResolvedEndpoint, resolve_endpoint_for_model


class SessionFilter:
    def handle(self, payload: Any) -> bool:
        if isinstance(payload, StageEvent):
            return True
        if isinstance(payload, StreamEvent):
            payload = payload.payload
        if not isinstance(payload, dict):
            return False
        session_id = payload.get("session_id")
        return isinstance(session_id, str) and bool(session_id.strip())


class ExtractMessage:
    def handle(self, payload: Any) -> dict[str, Any] | StageEvent:
        if isinstance(payload, StageEvent):
            return payload
        if isinstance(payload, StreamEvent):
            payload = payload.payload
        if not isinstance(payload, dict):
            raise ValueError("chat payload must be a dict-like record.")
        message = payload.get("message")
        normalized = message.strip() if isinstance(message, str) else ""
        if not normalized:
            raise ValueError("chat message cannot be empty.")
        return {
            **payload,
            "message": normalized,
            "stage": "chat.prepare",
        }


class SessionKeyByTailShard:
    def handle(self, payload: Any) -> Any:
        if isinstance(payload, int):
            # Keep control partition markers stable for manual done routing.
            return payload
        if isinstance(payload, StageEvent):
            return f"run:{payload.run_id[-4:]}"
        if not isinstance(payload, dict):
            return "unknown_tail4:0000"
        user_id = payload.get("user_id")
        if isinstance(user_id, str) and user_id.strip():
            return f"user_tail4:{user_id.strip()[-4:]}"
        session_id = payload.get("session_id")
        if isinstance(session_id, str) and session_id.strip():
            return f"session_tail4:{session_id.strip()[-4:]}"
        request_id = payload.get("request_id")
        if isinstance(request_id, str) and request_id.strip():
            return f"request_tail4:{request_id.strip()[-4:]}"
        return "unknown_tail4:0000"


class SessionStateProcessor:
    def handle(self, payload: Any, state_ctx: Any) -> dict[str, Any] | StageEvent | None:
        if isinstance(payload, StageEvent):
            return payload
        if not isinstance(payload, dict):
            return None
        session_id = cast(str, payload.get("session_id", ""))
        if not session_id:
            raise ValueError("missing session_id during process stage.")

        state = state_ctx.get(default={"turn_count": 0, "recent_messages": []})
        if not isinstance(state, dict):
            state = {"turn_count": 0, "recent_messages": []}

        turn_count = int(state.get("turn_count", 0)) + 1
        recent_messages = state.get("recent_messages", [])
        if not isinstance(recent_messages, list):
            recent_messages = []
        recent_messages = [str(item) for item in recent_messages]
        recent_messages.append(str(payload.get("message", "")))
        next_state = {
            "turn_count": turn_count,
            "recent_messages": recent_messages[-5:],
        }
        state_ctx.set(next_state)

        return {
            **payload,
            "session_state": next_state,
            "stage": "chat.session_ready",
        }


class GenerateAIResponse:
    def handle(self, payload: Any) -> list[StageEvent]:
        if isinstance(payload, StageEvent):
            return [payload]
        if not isinstance(payload, dict):
            return []
        message = cast(str, payload.get("message", ""))
        model = cast(str, payload.get("model", ""))
        run_id = cast(str, payload.get("run_id", "unknown"))
        request_id = cast(str, payload.get("request_id", "unknown"))

        resolved = resolve_endpoint_for_model(model)
        if resolved is None:
            raise RuntimeError(
                f"no_endpoint_configured: no LLM endpoint available for model={model!r}. "
                "Start an engine with: sage llm engine start <model>"
            )
        if not resolved.matched_model:
            raise RuntimeError(
                f"model_not_registered: model={model!r} is not registered in endpoint={resolved.endpoint_id!r}"
            )

        response = _call_inference(endpoint=resolved, message=message)
        response_text = response.content

        # Guard against empty/whitespace-only responses from small models
        if not response_text or not response_text.strip():
            response_text = (
                "(The model returned an empty response. "
                "This may happen with small models. Please try rephrasing your question.)"
            )

        return [
            StageEvent(
                run_id=run_id,
                request_id=request_id,
                stage="chat.generation.succeeded",
                state=StageEventState.SUCCEEDED,
                message=response_text,
                metrics=response.metrics,
            ),
        ]


class ChatFlowErrorHandler:
    def handle(self, event: ExceptionEvent) -> ExceptionDecision:
        payload = _first_payload_arg(event)
        run_id = _extract_field(payload, "run_id", fallback="unknown-run")
        request_id = _extract_field(payload, "request_id", fallback="unknown-request")
        stage = _extract_field(payload, "stage", fallback="chat.flow")
        failed = StageEvent(
            run_id=run_id,
            request_id=request_id,
            stage=f"{stage}.error",
            state=StageEventState.FAILED,
            message=f"request_id={request_id} {event.error_type}: {event.message}",
        )
        return ExceptionDecision.fallback(failed)


def _first_payload_arg(event: ExceptionEvent) -> Any:
    payload_data = event.context.payload
    if payload_data is None or not payload_data.args:
        return None
    return payload_data.args[0]


def _extract_field(payload: Any, field: str, *, fallback: str) -> str:
    if isinstance(payload, StageEvent):
        return cast(str, getattr(payload, field, fallback))
    if isinstance(payload, StreamEvent):
        payload = payload.payload
    if isinstance(payload, dict):
        value = payload.get(field, fallback)
        return str(value)
    return fallback


def _call_inference(*, endpoint: ResolvedEndpoint, message: str) -> ChatCompletionResult:
    """Call the LLM endpoint synchronously. Raises RuntimeError on failure."""
    if endpoint.provider not in {
        "alibaba_dashscope",
        "openai_compatible",
        "openrouter",
        "groq",
        "openai",
    }:
        raise RuntimeError(
            f"provider_not_supported: provider={endpoint.provider!r} endpoint={endpoint.endpoint_id!r}"
        )
    if not endpoint.api_key:
        raise RuntimeError(
            f"endpoint_missing_api_key: endpoint={endpoint.endpoint_id!r} has no API key configured"
        )
    try:
        return request_chat_completion(endpoint=endpoint, message=message)
    except InferenceCallError as exc:
        raise RuntimeError(f"provider_call_failed: {exc}") from exc


# ──────────────────────────────────────────────────────────────────────────────
# Orchestrated actor helpers
# ──────────────────────────────────────────────────────────────────────────────

_QUEUE_SENTINEL = object()


def _agent_step_status_to_state(status: str) -> StageEventState:
    """Map AgentStep.status string to StageEventState."""
    if status == "running":
        return StageEventState.RUNNING
    if status == "failed":
        return StageEventState.FAILED
    return StageEventState.SUCCEEDED


class OrchestratedResponseActor:
    """Flownet actor that routes messages through AgentOrchestrator.

    Returns a *generator* so that Flownet's ``flatmap`` emits each StageEvent
    immediately as it is produced, providing progressive reasoning-step display
    in the frontend rather than a single batched burst.

    Design:
    - A background OS thread runs the async orchestrator pipeline.
    - Each item yielded by the orchestrator is put onto a ``queue.Queue``.
    - The generator reads from the queue, yielding StageEvents as they arrive.
    - ``str`` items (LLM token chunks) are emitted as ``RUNNING`` generation
      events; the SSE adapter forwards these as ``delta`` frames immediately.
    - A final ``SUCCEEDED`` generation event (empty content) closes the stream
      and carries throughput metrics.
    """

    def handle(self, payload: Any) -> Generator[StageEvent, None, None]:
        if isinstance(payload, StageEvent):
            yield payload
            return
        if not isinstance(payload, dict):
            return

        message = cast(str, payload.get("message", ""))
        run_id = cast(str, payload.get("run_id", "unknown"))
        request_id = cast(str, payload.get("request_id", "unknown"))
        session_id = cast(str, payload.get("session_id", run_id))

        out: queue.Queue = queue.Queue()

        def _worker() -> None:
            """Run the orchestrator async generator in a dedicated event loop."""
            async def _run() -> None:
                try:
                    # Late import — catches ImportError inside the error guard.
                    from sage.studio.services.agent_orchestrator import (
                        get_orchestrator,  # noqa: PLC0415
                    )
                    orchestrator = get_orchestrator()
                    async for item in orchestrator.process_message(
                        message=message, session_id=session_id
                    ):
                        out.put(item)
                except Exception as exc:  # noqa: BLE001
                    out.put(exc)
                finally:
                    out.put(_QUEUE_SENTINEL)

            asyncio.run(_run())

        worker_thread = threading.Thread(target=_worker, daemon=True)
        worker_thread.start()

        t0 = time.perf_counter()
        text_chunks: list[str] = []
        had_error = False

        while True:
            item = out.get()

            if item is _QUEUE_SENTINEL:
                break

            if isinstance(item, Exception):
                yield StageEvent(
                    run_id=run_id,
                    request_id=request_id,
                    stage="chat.flow.error",
                    state=StageEventState.FAILED,
                    message=f"orchestrator_failed: {item}",
                )
                had_error = True
                break

            if isinstance(item, str):
                # LLM token chunk — emit immediately as a streaming delta.
                text_chunks.append(item)
                yield StageEvent(
                    run_id=run_id,
                    request_id=request_id,
                    stage="chat.generation.response",
                    state=StageEventState.RUNNING,
                    message=item,
                )
            elif hasattr(item, "type") and hasattr(item, "status"):
                # AgentStep — routing / retrieval / tool-call / response step.
                stage = str(item.type.value if hasattr(item.type, "value") else item.type)
                status_str = str(item.status.value if hasattr(item.status, "value") else item.status)
                state = _agent_step_status_to_state(status_str)
                yield StageEvent(
                    run_id=run_id,
                    request_id=request_id,
                    stage=stage,
                    state=state,
                    message=str(item.content),
                )

        worker_thread.join(timeout=5)

        if had_error:
            return

        # ── terminal generation event ────────────────────────────────────────
        # All text content was already sent as RUNNING deltas above.  This
        # SUCCEEDED event carries only metrics and tells the SSE adapter (and
        # service._route_stage_event) that the stream is done.
        elapsed = time.perf_counter() - t0
        final_text = "".join(text_chunks)

        if not final_text.strip():
            # Nothing was streamed — emit the fallback text as the sole delta.
            fallback = (
                "(The model returned an empty response. "
                "This may happen with small models. Please try rephrasing your question.)"
            )
            yield StageEvent(
                run_id=run_id,
                request_id=request_id,
                stage="chat.generation.response",
                state=StageEventState.RUNNING,
                message=fallback,
            )
            final_text = fallback

        metrics: dict[str, float] | None = None
        if elapsed > 0.05:  # noqa: PLR2004
            word_count = len(final_text.split())
            approx_tokens = max(1, int(word_count * 1.3))
            tps = round(approx_tokens / elapsed, 1)
            metrics = {"throughput_tps": tps}

        yield StageEvent(
            run_id=run_id,
            request_id=request_id,
            stage="chat.generation.response",
            state=StageEventState.SUCCEEDED,
            message="",  # content already sent as RUNNING deltas
            metrics=metrics,
        )


__all__ = [
    "ChatFlowErrorHandler",
    "ExtractMessage",
    "GenerateAIResponse",
    "OrchestratedResponseActor",
    "SessionFilter",
    "SessionKeyByTailShard",
    "SessionStateProcessor",
]
