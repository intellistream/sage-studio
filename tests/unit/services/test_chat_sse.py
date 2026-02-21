from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sage.studio.api.chat_sse import ChatSSEStreamAdapter
from sage.studio.contracts.models import StageEvent, StageEventState


@dataclass
class _FakeItem:
    kind: str
    event: StageEvent | None = None
    message: str | None = None


class _FakeSubscription:
    def __init__(self, items: list[_FakeItem]):
        self._items = items
        self.closed = False

    def read_item(self, timeout: float) -> _FakeItem | None:
        _ = timeout
        if not self._items:
            return None
        return self._items.pop(0)

    def delivery_status(self) -> dict[str, Any]:
        return {"stats": {"dropped_total": 0}}

    def close(self) -> None:
        self.closed = True


def _stage_event(*, state: StageEventState, message: str | None) -> StageEvent:
    return StageEvent(
        run_id="session-1",
        request_id="req-1",
        stage="reasoning",
        state=state,
        message=message,
        timestamp=datetime.now(timezone.utc),
    )


def test_chat_sse_emits_chat_v2_events_and_done() -> None:
    sub = _FakeSubscription(
        [
            _FakeItem(kind="event", event=_stage_event(state=StageEventState.SUCCEEDED, message="hello")),
            _FakeItem(kind="done"),
        ]
    )

    adapter = ChatSSEStreamAdapter(subscription=sub, request_id="req-1", model="sage-default")
    chunks = list(adapter.iter_sse())

    assert any(chunk.startswith("event: chat.v2\n") for chunk in chunks)
    assert any('"type": "delta"' in chunk for chunk in chunks)
    assert any("data: [DONE]" in chunk for chunk in chunks)
    assert sub.closed is True


def test_chat_sse_maps_runtime_error_to_error_event() -> None:
    sub = _FakeSubscription([_FakeItem(kind="error", message="runtime exploded")])

    adapter = ChatSSEStreamAdapter(subscription=sub, request_id="req-2", model="sage-default")
    chunks = list(adapter.iter_sse())

    assert any('"type": "error"' in chunk for chunk in chunks)
    assert any('"error": "runtime exploded"' in chunk for chunk in chunks)
    assert any("data: [DONE]" in chunk for chunk in chunks)


def test_chat_sse_emits_timeout_error_after_keepalive_threshold() -> None:
    sub = _FakeSubscription([])

    adapter = ChatSSEStreamAdapter(
        subscription=sub,
        request_id="req-timeout",
        model="sage-default",
        event_poll_timeout_s=0.0,
        keepalive_interval_s=0.0,
        max_keepalive_count=2,
    )
    chunks = list(adapter.iter_sse())

    assert sum(1 for chunk in chunks if chunk.startswith(": keepalive")) >= 2
    assert any('"type": "error"' in chunk for chunk in chunks)
    assert any('"error": "stream_timeout_waiting_for_runtime"' in chunk for chunk in chunks)
    assert any("data: [DONE]" in chunk for chunk in chunks)
