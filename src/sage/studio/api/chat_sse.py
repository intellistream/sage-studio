from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Generator
from typing import TYPE_CHECKING, Any

from sage.studio.contracts.models import StageEvent, StageEventState

if TYPE_CHECKING:
    pass

_TERMINAL_STATES = {
    StageEventState.SUCCEEDED,
    StageEventState.FAILED,
    StageEventState.CANCELLED,
}
_EVENT_POLL_TIMEOUT_S = 0.2
_KEEPALIVE_INTERVAL_S = 10.0
_MAX_KEEPALIVE_COUNT = int(os.environ.get("STUDIO_CHAT_SSE_MAX_KEEPALIVE_COUNT", "12"))

# Stage kind → frontend step_type mapping (from AgentOrchestrator stage names)
STAGE_KIND_TO_STEP_TYPE: dict[str, str] = {
    "routing": "thinking",
    "retrieval": "retrieval",
    "agentic": "tool_call",
    "tool_call": "tool_call",
    "response": "response",
}

# Stage names that carry text content (LLM generation output) → emit as delta
_GENERATION_STAGE_PREFIX = "chat.generation"


def _stage_to_step_type(stage: str) -> str:
    """Derive frontend step_type from a dotted stage name (e.g. 'routing' -> 'thinking')."""
    kind = stage.split(".")[0]
    return STAGE_KIND_TO_STEP_TYPE.get(kind, kind)


def _is_generation_stage(stage: str) -> bool:
    """Return True when the stage carries LLM text output (should emit as 'delta')."""
    return stage.startswith(_GENERATION_STAGE_PREFIX)


class ChatSSEStreamAdapter:
    def __init__(
        self,
        *,
        subscription: Any,
        request_id: str,
        model: str,
        event_poll_timeout_s: float = _EVENT_POLL_TIMEOUT_S,
        keepalive_interval_s: float = _KEEPALIVE_INTERVAL_S,
        max_keepalive_count: int = _MAX_KEEPALIVE_COUNT,
        monotonic: Callable[[], float] = time.monotonic,
        now_ts: Callable[[], float] = time.time,
    ):
        self._subscription = subscription
        self._request_id = request_id
        self._model = model
        self._event_poll_timeout_s = event_poll_timeout_s
        self._keepalive_interval_s = keepalive_interval_s
        self._max_keepalive_count = max(1, int(max_keepalive_count))
        self._monotonic = monotonic
        self._now_ts = now_ts
        # Track step_ids already announced so we can distinguish first RUNNING (→ step)
        # from subsequent RUNNING events for the same step (→ step_update).
        self._seen_step_ids: set[str] = set()

    def iter_sse(self) -> Generator[str, None, None]:
        last_keepalive = self._monotonic()
        keepalive_count = 0
        final_status: dict[str, Any] = {}
        try:
            while True:
                item = self._subscription.read_item(timeout=self._event_poll_timeout_s)
                if item is None:
                    now = self._monotonic()
                    if (now - last_keepalive) >= self._keepalive_interval_s:
                        last_keepalive = now
                        keepalive_count += 1
                        yield _sse_keepalive()
                        if keepalive_count >= self._max_keepalive_count:
                            yield _sse_system_notice(
                                request_id=self._request_id,
                                model=self._model,
                                message="stream_timeout_waiting_for_runtime",
                                event_type="error",
                                now_ts=self._now_ts,
                            )
                            break
                    continue

                keepalive_count = 0
                chunk, terminal = self._map_item(item)
                if chunk is not None:
                    yield chunk
                if terminal:
                    break
        finally:
            try:
                final_status = self._subscription.delivery_status()
            finally:
                self._subscription.close()

        dropped = _extract_dropped_total(final_status)
        if dropped > 0:
            yield _sse_system_notice(
                request_id=self._request_id,
                model=self._model,
                message=f"runtime_backpressure_dropped_events={dropped}",
                now_ts=self._now_ts,
            )
        yield _sse_done(request_id=self._request_id, model=self._model, now_ts=self._now_ts)

    def _map_item(self, item: Any) -> tuple[str | None, bool]:
        if item.kind == "done":
            return None, True
        if item.kind == "error":
            return (
                _sse_system_notice(
                    request_id=self._request_id,
                    model=self._model,
                    message=item.message or "runtime_error",
                    event_type="error",
                    now_ts=self._now_ts,
                ),
                True,
            )
        if item.kind == "gap":
            return (
                _sse_system_notice(
                    request_id=self._request_id,
                    model=self._model,
                    message=item.message or "event_gap",
                    now_ts=self._now_ts,
                ),
                False,
            )
        if item.kind == "notice":
            return (
                _sse_system_notice(
                    request_id=self._request_id,
                    model=self._model,
                    message=item.message or "stream_notice",
                    now_ts=self._now_ts,
                ),
                False,
            )
        if item.kind == "event" and item.event is not None:
            return self._sse_stage_event(event=item.event, model=self._model), False
        return None, False

    def _sse_stage_event(self, *, event: StageEvent, model: str) -> str:
        """Translate a StageEvent into the correct SSE frame.

        Mapping:
        - RUNNING + generation stage  → ``delta``       streaming token chunk
        - RUNNING (first occurrence)  → ``step``        status: running
        - RUNNING (subsequent)        → ``step_update`` status: running  (partial content)
        - SUCCEEDED + generation      → ``delta``       empty content + metrics  (terminal)
        - SUCCEEDED + reasoning       → ``step_update`` status: completed
        - FAILED / CANCELLED          → ``step_update`` status: failed
        """
        stage = event.stage
        step_type = _stage_to_step_type(stage)

        # ── terminal error ──────────────────────────────────────────────────
        if event.state in {StageEventState.FAILED, StageEventState.CANCELLED}:
            payload: dict[str, Any] = {
                "type": "step_update",
                "step_id": stage,
                "step_type": step_type,
                "status": "failed",
                "content": "",
                "error": event.message,
            }
            return f"event: chat.v2\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

        # ── success ─────────────────────────────────────────────────────────
        if event.state == StageEventState.SUCCEEDED:
            if _is_generation_stage(stage):
                # LLM text output → streaming delta
                payload = {
                    "type": "delta",
                    "session_id": event.run_id,
                    "message_id": event.request_id,
                    "content": event.message or "",
                }
                if event.metrics:
                    payload["metrics"] = event.metrics
            else:
                # Reasoning / routing / retrieval step completed
                payload = {
                    "type": "step_update",
                    "step_id": stage,
                    "step_type": step_type,
                    "status": "completed",
                    "content": event.message or "",
                }
            return f"event: chat.v2\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

        # ── running + generation stage → streaming token delta ──────────────
        # LLM token chunks arrive as RUNNING chat.generation.* events so that
        # the browser can append text progressively without waiting for the
        # full response.  The subsequent SUCCEEDED event (empty content) closes
        # the stream and carries throughput metrics.
        if _is_generation_stage(stage):
            payload = {
                "type": "delta",
                "session_id": event.run_id,
                "message_id": event.request_id,
                "content": event.message or "",
            }
            if event.metrics:
                payload["metrics"] = event.metrics
            return f"event: chat.v2\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

        # ── running / intermediate ───────────────────────────────────────────
        if stage not in self._seen_step_ids:
            self._seen_step_ids.add(stage)
            sse_type = "step"
        else:
            sse_type = "step_update"

        payload = {
            "type": sse_type,
            "step_id": stage,
            "step_type": step_type,
            "status": "running",
            "content": event.message or "",
        }
        return f"event: chat.v2\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _sse_done(*, request_id: str, model: str, now_ts: Callable[[], float] = time.time) -> str:
    payload = {
        "type": "meta",
        "status": "stream_end",
        "message_id": request_id,
        "content": "",
    }
    return (
        f"event: chat.v2\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        "event: chat.v2\ndata: [DONE]\n\n"
    )


def _sse_keepalive() -> str:
    return ": keepalive\n\n"


def _sse_system_notice(
    *,
    request_id: str,
    model: str,
    message: str,
    event_type: str = "meta",
    now_ts: Callable[[], float] = time.time,
) -> str:
    payload = {
        "type": event_type,
        "message_id": request_id,
        "status": "notice" if event_type == "meta" else "failed",
        "content": message if event_type == "meta" else "",
        "error": message if event_type == "error" else None,
    }
    return f"event: chat.v2\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _extract_dropped_total(status: dict[str, Any]) -> int:
    stats = status.get("stats")
    if not isinstance(stats, dict):
        return 0
    try:
        return int(stats.get("dropped_total", 0))
    except (TypeError, ValueError):
        return 0


__all__ = ["ChatSSEStreamAdapter"]
