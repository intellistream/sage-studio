from __future__ import annotations

from typing import Any, cast

from sage.flownet.core.exceptions import ExceptionDecision, ExceptionEvent
from sage.flownet.core.stream_event import StreamEvent

from sage.studio.contracts.models import StageEvent, StageEventState
from sage.studio.runtime.adapters import InferenceCallError, request_chat_completion
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
        session_state = payload.get("session_state")
        if not isinstance(session_state, dict):
            session_state = {}
        turn_count = int(session_state.get("turn_count", 0))
        resolved = resolve_endpoint_for_model(model)
        route_note = _format_route_note(model=model, resolved=resolved)

        if message == "__raise__":
            raise RuntimeError("placeholder model execution failed.")

        response_text = _generate_response_text(
            message=message,
            turn_count=turn_count,
            resolved=resolved,
        )

        return [
            StageEvent(
                run_id=run_id,
                request_id=request_id,
                stage="chat.generation.started",
                state=StageEventState.RUNNING,
                message=f"placeholder generation started ({route_note})",
            ),
            StageEvent(
                run_id=run_id,
                request_id=request_id,
                stage="chat.generation.succeeded",
                state=StageEventState.SUCCEEDED,
                message=f"{response_text} ({route_note})",
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


def _format_route_note(*, model: str, resolved: ResolvedEndpoint | None) -> str:
    normalized_model = model.strip() or "unknown-model"
    if resolved is None:
        return f"model={normalized_model},endpoint=unresolved"
    return (
        f"model={normalized_model},endpoint={resolved.endpoint_id},provider={resolved.provider}"
    )


def _generate_response_text(*, message: str, turn_count: int, resolved: ResolvedEndpoint | None) -> str:
    if resolved is None:
        return f"placeholder response(turn={turn_count}): {message}"
    if not _supports_live_inference(resolved):
        return f"placeholder response(turn={turn_count}): {message}"

    try:
        return request_chat_completion(endpoint=resolved, message=message)
    except InferenceCallError as exc:
        raise RuntimeError(f"provider_call_failed:{exc}") from exc


def _supports_live_inference(resolved: ResolvedEndpoint) -> bool:
    if not resolved.api_key:
        return False
    if not resolved.matched_model:
        return False
    return resolved.provider in {"alibaba_dashscope", "openai_compatible", "openrouter", "groq", "openai"}


__all__ = [
    "ChatFlowErrorHandler",
    "ExtractMessage",
    "GenerateAIResponse",
    "SessionFilter",
    "SessionKeyByTailShard",
    "SessionStateProcessor",
]
