from __future__ import annotations

import json
import time
from collections.abc import Callable, Generator
from typing import TYPE_CHECKING, Any

from sage.studio.contracts.models import StageEvent, StageEventState

if TYPE_CHECKING:
    from sage.studio.runtime.chat import ChatEventItem, ChatEventSubscription

_TERMINAL_STATES = {
    StageEventState.SUCCEEDED,
    StageEventState.FAILED,
    StageEventState.CANCELLED,
}
_EVENT_POLL_TIMEOUT_S = 0.2
_KEEPALIVE_INTERVAL_S = 10.0


class ChatSSEStreamAdapter:
    def __init__(
        self,
        *,
        subscription: Any,
        request_id: str,
        model: str,
        event_poll_timeout_s: float = _EVENT_POLL_TIMEOUT_S,
        keepalive_interval_s: float = _KEEPALIVE_INTERVAL_S,
        monotonic: Callable[[], float] = time.monotonic,
        now_ts: Callable[[], float] = time.time,
    ):
        self._subscription = subscription
        self._request_id = request_id
        self._model = model
        self._event_poll_timeout_s = event_poll_timeout_s
        self._keepalive_interval_s = keepalive_interval_s
        self._monotonic = monotonic
        self._now_ts = now_ts

    def iter_sse(self) -> Generator[str, None, None]:
        last_keepalive = self._monotonic()
        final_status: dict[str, Any] = {}
        try:
            while True:
                item = self._subscription.read_item(timeout=self._event_poll_timeout_s)
                if item is None:
                    now = self._monotonic()
                    if (now - last_keepalive) >= self._keepalive_interval_s:
                        last_keepalive = now
                        yield _sse_keepalive()
                    continue

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
            return _sse_stage_event(event=item.event, model=self._model), False
        return None, False


def _sse_stage_event(*, event: StageEvent, model: str) -> str:
    finish_reason: str | None = None
    if event.state in _TERMINAL_STATES:
        finish_reason = "stop" if event.state == StageEventState.SUCCEEDED else "error"
    payload = {
        "id": f"chatcmpl-{event.request_id}",
        "object": "chat.completion.chunk",
        "created": int(event.timestamp.timestamp()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"content": event.message or ""},
                "finish_reason": finish_reason,
            }
        ],
        "stage_event": event.model_dump(mode="json"),
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\\n\\n"


def _sse_done(*, request_id: str, model: str, now_ts: Callable[[], float] = time.time) -> str:
    payload = {
        "id": f"chatcmpl-{request_id}",
        "object": "chat.completion.chunk",
        "created": int(now_ts()),
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\\n\\ndata: [DONE]\\n\\n"


def _sse_keepalive() -> str:
    return ": keepalive\\n\\n"


def _sse_system_notice(
    *,
    request_id: str,
    model: str,
    message: str,
    now_ts: Callable[[], float] = time.time,
) -> str:
    payload = {
        "id": f"chatcmpl-{request_id}",
        "object": "chat.completion.system",
        "created": int(now_ts()),
        "model": model,
        "notice": message,
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\\n\\n"


def _extract_dropped_total(status: dict[str, Any]) -> int:
    stats = status.get("stats")
    if not isinstance(stats, dict):
        return 0
    try:
        return int(stats.get("dropped_total", 0))
    except (TypeError, ValueError):
        return 0


__all__ = ["ChatSSEStreamAdapter"]
