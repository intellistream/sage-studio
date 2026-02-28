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


def _stage_event(
    *, state: StageEventState, message: str | None, stage: str = "reasoning"
) -> StageEvent:
    return StageEvent(
        run_id="session-1",
        request_id="req-1",
        stage=stage,
        state=state,
        message=message,
        timestamp=datetime.now(timezone.utc),
    )


def test_chat_sse_emits_chat_v2_events_and_done() -> None:
    # Use a generation stage so SUCCEEDED maps to a delta
    sub = _FakeSubscription(
        [
            _FakeItem(
                kind="event",
                event=_stage_event(
                    state=StageEventState.SUCCEEDED,
                    message="hello",
                    stage="chat.generation.response",
                ),
            ),
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


def test_chat_sse_includes_metrics_from_stage_event() -> None:
    sub = _FakeSubscription(
        [
            _FakeItem(
                kind="event",
                event=StageEvent(
                    run_id="session-2",
                    request_id="req-3",
                    stage="chat.generation.succeeded",
                    state=StageEventState.SUCCEEDED,
                    message="hello",
                    metrics={"throughput_tps": 25.4},
                    timestamp=datetime.now(timezone.utc),
                ),
            ),
            _FakeItem(kind="done"),
        ]
    )

    adapter = ChatSSEStreamAdapter(subscription=sub, request_id="req-3", model="sage-default")
    chunks = list(adapter.iter_sse())

    assert any('"metrics": {"throughput_tps": 25.4}' in chunk for chunk in chunks)


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


# ──────────────────────────────────────────────────────────────────────────────
# Issue #35: StageEvent → step / step_update SSE mapping
# ──────────────────────────────────────────────────────────────────────────────


def test_stage_running_first_emits_step() -> None:
    """First RUNNING event for a stage → SSE type 'step' with status 'running'."""
    sub = _FakeSubscription(
        [
            _FakeItem(
                kind="event",
                event=_stage_event(
                    state=StageEventState.RUNNING, message="正在分析...", stage="routing"
                ),
            ),
            _FakeItem(kind="done"),
        ]
    )
    adapter = ChatSSEStreamAdapter(subscription=sub, request_id="req-step", model="sage-default")
    chunks = list(adapter.iter_sse())

    step_chunks = [c for c in chunks if '"type": "step"' in c]
    assert len(step_chunks) == 1
    assert '"step_id": "routing"' in step_chunks[0]
    assert '"step_type": "thinking"' in step_chunks[0]
    assert '"status": "running"' in step_chunks[0]


def test_stage_running_subsequent_emits_step_update() -> None:
    """Second RUNNING event for the same stage → SSE type 'step_update'."""
    sub = _FakeSubscription(
        [
            _FakeItem(
                kind="event",
                event=_stage_event(state=StageEventState.RUNNING, message="start", stage="routing"),
            ),
            _FakeItem(
                kind="event",
                event=_stage_event(
                    state=StageEventState.RUNNING, message="update", stage="routing"
                ),
            ),
            _FakeItem(kind="done"),
        ]
    )
    adapter = ChatSSEStreamAdapter(subscription=sub, request_id="req-step2", model="sage-default")
    chunks = list(adapter.iter_sse())

    step_chunks = [c for c in chunks if '"type": "step"' in c and '"step_update"' not in c]
    update_chunks = [
        c for c in chunks if '"type": "step_update"' in c and '"status": "running"' in c
    ]
    assert len(step_chunks) == 1, "exactly one 'step' event (first RUNNING)"
    assert len(update_chunks) == 1, "exactly one 'step_update' event (second RUNNING)"


def test_stage_succeeded_non_generation_emits_step_update_completed() -> None:
    """SUCCEEDED on a reasoning stage (non-generation) → step_update with status 'completed'."""
    sub = _FakeSubscription(
        [
            _FakeItem(
                kind="event",
                event=_stage_event(
                    state=StageEventState.SUCCEEDED,
                    message="路由完成",
                    stage="routing",
                ),
            ),
            _FakeItem(kind="done"),
        ]
    )
    adapter = ChatSSEStreamAdapter(
        subscription=sub, request_id="req-completed", model="sage-default"
    )
    chunks = list(adapter.iter_sse())

    update_chunks = [c for c in chunks if '"type": "step_update"' in c]
    assert len(update_chunks) == 1
    assert '"status": "completed"' in update_chunks[0]
    assert '"step_id": "routing"' in update_chunks[0]
    assert '"type": "delta"' not in update_chunks[0]


def test_stage_failed_emits_step_update_failed() -> None:
    """FAILED StageEvent → step_update with status 'failed' and error field."""
    sub = _FakeSubscription(
        [
            _FakeItem(
                kind="event",
                event=_stage_event(
                    state=StageEventState.FAILED,
                    message="retrieval error",
                    stage="retrieval",
                ),
            ),
            _FakeItem(kind="done"),
        ]
    )
    adapter = ChatSSEStreamAdapter(subscription=sub, request_id="req-failed", model="sage-default")
    chunks = list(adapter.iter_sse())

    update_chunks = [c for c in chunks if '"type": "step_update"' in c]
    assert len(update_chunks) == 1
    assert '"status": "failed"' in update_chunks[0]
    assert '"error": "retrieval error"' in update_chunks[0]
    assert '"step_type": "retrieval"' in update_chunks[0]


def test_stage_generation_succeeded_emits_delta() -> None:
    """SUCCEEDED on a generation stage → delta with text content."""
    sub = _FakeSubscription(
        [
            _FakeItem(
                kind="event",
                event=_stage_event(
                    state=StageEventState.SUCCEEDED,
                    message="The answer is 42.",
                    stage="chat.generation.response",
                ),
            ),
            _FakeItem(kind="done"),
        ]
    )
    adapter = ChatSSEStreamAdapter(subscription=sub, request_id="req-delta", model="sage-default")
    chunks = list(adapter.iter_sse())

    delta_chunks = [c for c in chunks if '"type": "delta"' in c]
    assert len(delta_chunks) == 1
    assert '"content": "The answer is 42."' in delta_chunks[0]
    assert '"type": "step_update"' not in delta_chunks[0]


def test_stage_retrieval_running_uses_correct_step_type() -> None:
    """Stage 'retrieval' → step_type 'retrieval'."""
    sub = _FakeSubscription(
        [
            _FakeItem(
                kind="event",
                event=_stage_event(
                    state=StageEventState.RUNNING, message="searching", stage="retrieval"
                ),
            ),
            _FakeItem(kind="done"),
        ]
    )
    adapter = ChatSSEStreamAdapter(subscription=sub, request_id="req-ret", model="sage-default")
    chunks = list(adapter.iter_sse())

    step_chunks = [c for c in chunks if '"type": "step"' in c]
    assert any('"step_type": "retrieval"' in c for c in step_chunks)
