from __future__ import annotations

import os
import queue
import threading
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, cast
from urllib.parse import quote

import sage.flownet.api as fn
from sage.flownet.api import runtime as runtime_api
from sage.flownet.api.actor_method_ref import ActorMethodRef
from sage.flownet.core.stream_event import StreamEvent
from sage.flownet.runtime.flows.output_channel import RunOutputDone, RunOutputError, RunOutputGap

from sage.studio.contracts.models import StageEvent, StageEventState
from sage.studio.runtime.chat.assembly import get_chat_pipeline

_SERVICE_RUN_LOCK = threading.RLock()
_SERVICE_RUN: Any | None = None
_SERVICE_DISPATCHER: _SharedChatDispatcher | None = None
_SERVICE_RUN_SEQ = 0

_SUBSCRIBER_QUEUE_CAPACITY = 256
_REQUEST_BACKLOG_CAPACITY = 256
_COMPLETED_STATUS_CAPACITY = 1024
_DONE_EMIT_HOLD_S = float(os.environ.get("STUDIO_CHAT_DONE_EMIT_HOLD_S", "0.05"))
_DONE_RETRY_INTERVAL_S = float(os.environ.get("STUDIO_CHAT_DONE_RETRY_INTERVAL_S", "0.02"))
_DONE_FORCE_EMIT_S = float(os.environ.get("STUDIO_CHAT_DONE_FORCE_EMIT_S", "1.0"))
_CHAT_EGRESS_TOPIC_ID = os.environ.get(
    "STUDIO_CHAT_EGRESS_TOPIC_ID",
    "sage.studio.chat.egress",
)
_CHAT_EGRESS_EVENT_TYPE = "chat.event"
_CHAT_EGRESS_DONE_EVENT_TYPE = "chat.done"
_CHAT_EGRESS_ERROR_EVENT_TYPE = "chat.error"
_CHAT_INGRESS_TOPIC_ID = os.environ.get(
    "STUDIO_CHAT_INGRESS_TOPIC_ID",
    "sage.studio.chat.ingress",
)
_CHAT_INGRESS_EVENT_TYPE = "chat.request"
_TERMINAL_EVENT_STATES = {
    StageEventState.SUCCEEDED,
    StageEventState.FAILED,
    StageEventState.CANCELLED,
}


@dataclass(slots=True)
class _TopicEgressSubscription:
    stream: Any

    def close(self) -> None:
        unsubscribe = getattr(self.stream, "unsubscribe", None)
        if callable(unsubscribe):
            try:
                unsubscribe()
            except Exception:
                pass


class _TopicEventForwarder:
    def __init__(self, dispatcher: _SharedChatDispatcher):
        self._dispatcher = dispatcher

    def handle(self, event: StreamEvent):
        self._dispatcher.ingest_topic_event(event)
        return True


@dataclass(slots=True, frozen=True)
class ChatEventItem:
    kind: str
    event: StageEvent | None = None
    message: str | None = None
    meta: dict[str, Any] | None = None


@dataclass(slots=True)
class _Subscriber:
    runtime_request_id: str
    queue: queue.Queue[ChatEventItem]
    dropped_events: int = 0


@dataclass(slots=True)
class _RequestBinding:
    logical_request_id: str
    subscriber_ids: set[int] = field(default_factory=set)
    backlog: list[ChatEventItem] = field(default_factory=list)
    done: bool = False
    done_emitted: bool = False
    released: bool = False
    done_status: dict[str, Any] = field(default_factory=dict)
    done_meta: dict[str, Any] = field(default_factory=dict)
    max_event_seq: int = 0
    done_pending: bool = False
    done_pending_since: float | None = None


class _SharedChatDispatcher:
    def __init__(self, run: Any):
        self._run = run
        self._lock = threading.Lock()
        self._closed = False
        self._next_subscriber_id = 1
        self._subscribers: dict[int, _Subscriber] = {}
        self._requests: dict[str, _RequestBinding] = {}
        self._logical_index: dict[str, set[str]] = {}
        self._completed_status: dict[str, dict[str, Any]] = {}
        self._topic_subscription = _subscribe_chat_egress(dispatcher=self)

    @property
    def run(self) -> Any:
        return self._run

    def bound_to(self, run: Any) -> bool:
        return self._run is run

    def stop(self) -> None:
        topic_subscription: _TopicEgressSubscription | None = None
        with self._lock:
            self._closed = True
            topic_subscription = self._topic_subscription
            self._topic_subscription = None
        if topic_subscription is not None:
            topic_subscription.close()
        with self._lock:
            self._subscribers.clear()
            self._requests.clear()
            self._logical_index.clear()

    def ingest_topic_event(self, event: StreamEvent) -> None:
        with self._lock:
            if self._closed:
                return
        self._route_item(event)

    def bind_request(self, *, runtime_request_id: str, logical_request_id: str) -> None:
        if not runtime_request_id:
            return
        logical = logical_request_id or runtime_request_id
        with self._lock:
            binding = self._requests.get(runtime_request_id)
            if binding is None:
                binding = _RequestBinding(logical_request_id=logical)
                self._requests[runtime_request_id] = binding
                self._logical_index.setdefault(logical, set()).add(runtime_request_id)
                return
            if binding.logical_request_id == logical:
                return
            old_ids = self._logical_index.get(binding.logical_request_id)
            if old_ids is not None:
                old_ids.discard(runtime_request_id)
                if not old_ids:
                    self._logical_index.pop(binding.logical_request_id, None)
            binding.logical_request_id = logical
            self._logical_index.setdefault(logical, set()).add(runtime_request_id)

    def subscribe(
        self,
        *,
        runtime_request_id: str,
        logical_request_id: str | None = None,
    ) -> ChatEventSubscription:
        if not runtime_request_id:
            raise ValueError("runtime_request_id must be non-empty.")

        with self._lock:
            if self._closed:
                raise RuntimeError("chat dispatcher is closed")
            binding = self._requests.get(runtime_request_id)
            if binding is None:
                logical = logical_request_id or runtime_request_id
                binding = _RequestBinding(logical_request_id=logical)
                self._requests[runtime_request_id] = binding
                self._logical_index.setdefault(logical, set()).add(runtime_request_id)
            queue_obj: queue.Queue[ChatEventItem] = queue.Queue(maxsize=_SUBSCRIBER_QUEUE_CAPACITY)
            subscriber_id = self._next_subscriber_id
            self._next_subscriber_id += 1
            self._subscribers[subscriber_id] = _Subscriber(
                runtime_request_id=runtime_request_id,
                queue=queue_obj,
            )
            binding.subscriber_ids.add(subscriber_id)
            backlog = list(binding.backlog)
            binding.backlog.clear()
            done_status = dict(binding.done_status)
            done_meta = dict(binding.done_meta)
            done_without_backlog = binding.done_emitted and not backlog

        for item in backlog:
            queue_obj.put(item)
        if done_without_backlog:
            queue_obj.put(
                ChatEventItem(
                    kind="done",
                    meta={
                        "status": done_status,
                        "final_seq": done_meta.get("final_seq"),
                        "reason": done_meta.get("reason"),
                    },
                )
            )

        return ChatEventSubscription(
            dispatcher=self,
            subscriber_id=subscriber_id,
            queue_obj=queue_obj,
            runtime_request_id=runtime_request_id,
            logical_request_id=binding.logical_request_id,
        )

    def unsubscribe(self, subscriber_id: int, *, release_request: bool = True) -> None:
        runtime_request_id: str | None = None
        should_release = False
        with self._lock:
            subscriber = self._subscribers.pop(subscriber_id, None)
            if subscriber is None:
                return
            runtime_request_id = subscriber.runtime_request_id
            binding = self._requests.get(runtime_request_id)
            if binding is None:
                return
            binding.subscriber_ids.discard(subscriber_id)
            if binding.subscriber_ids:
                return
            if binding.done:
                self._drop_request_binding_locked(runtime_request_id)
                return
            if release_request and not binding.released:
                binding.released = True
                should_release = True

        if should_release and runtime_request_id is not None:
            release_chat_service_request(self._run, request_id=runtime_request_id)

    def request_status(self, runtime_request_id: str) -> dict[str, Any]:
        with self._lock:
            completed = self._completed_status.get(runtime_request_id)
            if completed is not None:
                return dict(completed)
            binding = self._requests.get(runtime_request_id)
            if binding is not None and binding.done_status:
                return dict(binding.done_status)
        return self._snapshot_runtime_status(runtime_request_id)

    def _route_item(self, item: Any) -> None:
        if isinstance(item, StreamEvent):
            self._route_topic_event(item)
            return
        if isinstance(item, StageEvent):
            self._route_stage_event(item)
            return
        if isinstance(item, RunOutputDone):
            self._route_done(item)
            return
        if isinstance(item, RunOutputGap):
            self._route_gap(item)
            return
        if isinstance(item, RunOutputError):
            self._route_error(item)
            return
        self._broadcast_notice(f"unexpected_stream_item={type(item).__name__}")

    def _route_topic_event(self, event: StreamEvent) -> None:
        event_type = str(getattr(event, "event_type", "") or "")
        payload = getattr(event, "payload", None)
        tags_obj = getattr(event, "tags", None)
        tags: dict[str, str] = {}
        if isinstance(tags_obj, Mapping):
            tags = {str(k): str(v) for k, v in tags_obj.items()}
        runtime_request_id = tags.get("request_id", "")

        if event_type == _CHAT_EGRESS_EVENT_TYPE:
            stage_event = _coerce_stage_event(payload)
            if stage_event is None:
                self._broadcast_notice(
                    f"invalid_chat_event_payload={type(payload).__name__}",
                )
                return
            event_seq = _to_optional_int(tags.get("__seq__"))
            if runtime_request_id:
                self._mark_event_seq(runtime_request_id, event_seq)
            if runtime_request_id:
                self.bind_request(
                    runtime_request_id=runtime_request_id,
                    logical_request_id=stage_event.request_id,
                )
            self._route_stage_event(stage_event)
            if runtime_request_id:
                self._schedule_done_emit(runtime_request_id, delay=0.0)
            return

        if event_type == _CHAT_EGRESS_DONE_EVENT_TYPE:
            return

        if event_type == _CHAT_EGRESS_ERROR_EVENT_TYPE:
            if not runtime_request_id and isinstance(payload, Mapping):
                runtime_request_id = str(payload.get("request_id") or "")
            if not runtime_request_id:
                return
            error_type = "runtime_error"
            message = "runtime_error"
            traceback_text = ""
            error_event = None
            if isinstance(payload, Mapping):
                error_type = str(payload.get("error_type") or "runtime_error")
                message = str(payload.get("message") or error_type)
                traceback_text = str(payload.get("traceback_text") or "")
                error_event = payload.get("event")
            self._route_error(
                RunOutputError(
                    request_id=runtime_request_id,
                    error_type=error_type,
                    message=message,
                    traceback_text=traceback_text,
                    event=error_event,
                )
            )
            return

        self._broadcast_notice(
            f"unexpected_topic_event_type={event_type or 'unknown'}",
        )

    def _route_stage_event(self, event: StageEvent) -> None:
        with self._lock:
            runtime_ids = tuple(self._logical_index.get(event.request_id, ()))
        if not runtime_ids:
            return
        item = ChatEventItem(kind="event", event=event)
        # Only close the stream when the stage is truly terminal.  Intermediate
        # reasoning-step SUCCEEDED events (e.g. "routing", "retrieval") must
        # NOT close the stream; only failures/cancels and the final generation
        # stage SUCCEEDED are stream-terminal.
        _is_stream_terminal = event.state in {
            StageEventState.FAILED,
            StageEventState.CANCELLED,
        } or (
            event.state == StageEventState.SUCCEEDED
            and (event.stage.startswith("chat.generation") or event.stage.endswith(".error"))
        )
        for runtime_request_id in runtime_ids:
            self._emit_item(runtime_request_id, item)
            if _is_stream_terminal:
                self._route_done(
                    RunOutputDone(
                        request_id=runtime_request_id,
                        reason="terminal_stage_event",
                    )
                )

    def _route_done(self, done: RunOutputDone) -> None:
        runtime_request_id = done.request_id
        if not runtime_request_id:
            return
        status = self._snapshot_runtime_status(runtime_request_id)
        status["request_done"] = True
        status["delivery_done"] = True
        status["watermark_done"] = True
        status["request_watermark_done"] = True

        should_release = False
        with self._lock:
            binding = self._requests.get(runtime_request_id)
            if binding is None:
                self._remember_completed_status_locked(runtime_request_id, status)
                return
            if binding.done and binding.done_emitted:
                return
            binding.done = True
            binding.done_status = dict(status)
            binding.done_meta = {
                "status": dict(status),
                "final_seq": done.final_seq,
                "reason": done.reason,
            }
            binding.done_pending = True
            binding.done_pending_since = time.monotonic()
            self._remember_completed_status_locked(runtime_request_id, status)
            if not binding.released:
                binding.released = True
                should_release = True

        if should_release:
            release_chat_service_request(self._run, request_id=runtime_request_id)
        self._schedule_done_emit(runtime_request_id)

    def _route_gap(self, gap: RunOutputGap) -> None:
        runtime_request_id = gap.request_id
        if not runtime_request_id:
            return
        self._emit_item(
            runtime_request_id,
            ChatEventItem(
                kind="gap",
                message=f"event_gap:seq={gap.seq},reason={gap.reason}",
                meta={"seq": gap.seq, "reason": gap.reason},
            ),
        )

    def _route_error(self, error: RunOutputError) -> None:
        runtime_request_id = error.request_id
        if not runtime_request_id:
            return
        self._emit_item(
            runtime_request_id,
            ChatEventItem(
                kind="error",
                message=f"runtime_error={error.error_type}",
                meta={
                    "error_type": error.error_type,
                    "traceback_text": error.traceback_text,
                    "event": error.event,
                },
            ),
        )
        self._route_done(
            RunOutputDone(
                runtime_request_id,
                reason="runtime_error",
            )
        )

    def _emit_item(self, runtime_request_id: str, item: ChatEventItem) -> None:
        with self._lock:
            binding = self._requests.get(runtime_request_id)
            if binding is None:
                return
            subscriber_ids = tuple(binding.subscriber_ids)
            if not subscriber_ids:
                self._append_backlog_locked(binding, item)
                return
            subscribers = [
                self._subscribers[sub_id]
                for sub_id in subscriber_ids
                if sub_id in self._subscribers
            ]
        for subscriber in subscribers:
            self._enqueue_to_subscriber(subscriber, item)

    def _schedule_done_emit(self, runtime_request_id: str, *, delay: float | None = None) -> None:
        interval = _DONE_EMIT_HOLD_S if delay is None else max(0.0, float(delay))
        timer = threading.Timer(
            interval,
            self._emit_done_after_hold,
            args=(runtime_request_id,),
        )
        timer.daemon = True
        timer.start()

    def _emit_done_after_hold(self, runtime_request_id: str) -> None:
        with self._lock:
            if self._closed:
                return
            binding = self._requests.get(runtime_request_id)
            if binding is None:
                return
            if not binding.done or binding.done_emitted:
                return
            if not self._ready_to_emit_done(binding):
                self._schedule_done_emit(runtime_request_id, delay=_DONE_RETRY_INTERVAL_S)
                return
            done_meta = dict(binding.done_meta)
            done_status = dict(binding.done_status)
            binding.done_emitted = True
            binding.done_pending = False
        self._emit_item(
            runtime_request_id,
            ChatEventItem(
                kind="done",
                meta={
                    "status": done_status,
                    "final_seq": done_meta.get("final_seq"),
                    "reason": done_meta.get("reason"),
                },
            ),
        )
        with self._lock:
            self._trim_orphan_done_bindings_locked()

    def _mark_event_seq(self, runtime_request_id: str, seq: int | None) -> None:
        if seq is None or seq < 0:
            return
        with self._lock:
            binding = self._requests.get(runtime_request_id)
            if binding is None:
                return
            if seq > binding.max_event_seq:
                binding.max_event_seq = seq

    @staticmethod
    def _ready_to_emit_done(binding: _RequestBinding) -> bool:
        if not binding.done_pending:
            return False
        final_seq = _to_optional_int(binding.done_meta.get("final_seq"))
        if final_seq is None:
            return True
        if binding.max_event_seq >= final_seq:
            return True
        since = binding.done_pending_since
        if since is None:
            return False
        return (time.monotonic() - since) >= _DONE_FORCE_EMIT_S

    def _enqueue_to_subscriber(self, subscriber: _Subscriber, item: ChatEventItem) -> None:
        try:
            subscriber.queue.put_nowait(item)
            return
        except queue.Full:
            subscriber.dropped_events += 1
        try:
            subscriber.queue.get_nowait()
        except queue.Empty:
            pass
        try:
            subscriber.queue.put_nowait(item)
        except queue.Full:
            subscriber.dropped_events += 1

    def _broadcast_notice(self, message: str) -> None:
        notice = ChatEventItem(kind="notice", message=message)
        with self._lock:
            subscribers = list(self._subscribers.values())
        for subscriber in subscribers:
            self._enqueue_to_subscriber(subscriber, notice)

    def _append_backlog_locked(self, binding: _RequestBinding, item: ChatEventItem) -> None:
        if len(binding.backlog) >= _REQUEST_BACKLOG_CAPACITY:
            binding.backlog.pop(0)
        binding.backlog.append(item)

    def _drop_request_binding_locked(self, runtime_request_id: str) -> None:
        binding = self._requests.pop(runtime_request_id, None)
        if binding is None:
            return
        logical_ids = self._logical_index.get(binding.logical_request_id)
        if logical_ids is None:
            return
        logical_ids.discard(runtime_request_id)
        if not logical_ids:
            self._logical_index.pop(binding.logical_request_id, None)

    def _remember_completed_status_locked(
        self,
        runtime_request_id: str,
        status: dict[str, Any],
    ) -> None:
        self._completed_status[runtime_request_id] = dict(status)
        while len(self._completed_status) > _COMPLETED_STATUS_CAPACITY:
            oldest = next(iter(self._completed_status))
            self._completed_status.pop(oldest, None)

    def _trim_orphan_done_bindings_locked(self) -> None:
        if len(self._requests) <= _COMPLETED_STATUS_CAPACITY:
            return
        removable = [
            runtime_request_id
            for runtime_request_id, binding in self._requests.items()
            if binding.done and not binding.subscriber_ids
        ]
        for runtime_request_id in removable:
            if len(self._requests) <= _COMPLETED_STATUS_CAPACITY:
                return
            self._drop_request_binding_locked(runtime_request_id)

    def _snapshot_runtime_status(self, runtime_request_id: str) -> dict[str, Any]:
        status_fn = getattr(self._run, "request_delivery_status", None)
        status: dict[str, Any] = {}
        if callable(status_fn):
            try:
                snapshot = status_fn(runtime_request_id)
                if isinstance(snapshot, dict):
                    status = dict(snapshot)
            except Exception:
                status = {}
        status.setdefault("request_id", runtime_request_id)
        status.setdefault("delivery_done", False)
        status.setdefault("watermark_done", bool(status.get("delivery_done")))
        status.setdefault("request_done", bool(status.get("delivery_done")))
        status.setdefault(
            "request_watermark_done",
            bool(status.get("request_done")) and bool(status.get("watermark_done")),
        )
        stats = status.get("stats")
        if not isinstance(stats, dict):
            status["stats"] = {}
        return status


class ChatEventSubscription:
    def __init__(
        self,
        *,
        dispatcher: _SharedChatDispatcher,
        subscriber_id: int,
        queue_obj: queue.Queue[ChatEventItem],
        runtime_request_id: str,
        logical_request_id: str,
    ):
        self._dispatcher = dispatcher
        self._subscriber_id = subscriber_id
        self._queue = queue_obj
        self._closed = False
        self._done = False
        self._done_status: dict[str, Any] = {}
        self._run = dispatcher.run
        self.request_id = runtime_request_id
        self.logical_request_id = logical_request_id or runtime_request_id

    def read_item(self, timeout: float = 5.0) -> ChatEventItem | None:
        try:
            item = self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

        if item.kind == "done":
            self._done = True
            status = item.meta.get("status") if isinstance(item.meta, dict) else None
            if isinstance(status, dict):
                self._done_status = dict(status)
            return item
        if item.kind == "error":
            status = self._dispatcher.request_status(self.request_id)
            status["request_done"] = True
            status["request_watermark_done"] = True
            self._done_status = status
        return item

    def read(self, timeout: float = 5.0):
        item = self.read_item(timeout=timeout)
        if item is None:
            raise queue.Empty()
        if item.kind == "event" and item.event is not None:
            return item.event
        if item.kind == "done":
            meta = item.meta or {}
            return RunOutputDone(
                self.request_id,
                final_seq=meta.get("final_seq"),
                reason=meta.get("reason"),
            )
        if item.kind == "gap":
            meta = item.meta or {}
            seq = int(meta.get("seq", 0))
            reason = str(meta.get("reason", "unknown_gap"))
            return RunOutputGap(self.request_id, seq=seq, reason=reason)
        if item.kind == "error":
            meta = item.meta or {}
            error_type = str(meta.get("error_type", "runtime_error"))
            traceback_text = str(meta.get("traceback_text", ""))
            event = meta.get("event")
            return RunOutputError(
                request_id=self.request_id,
                error_type=error_type,
                message=item.message or f"runtime_error={error_type}",
                traceback_text=traceback_text,
                event=event,
            )
        return item.message or "stream_notice"

    def request_done(self) -> bool:
        return bool(self.delivery_status().get("request_done"))

    def delivery_done(self) -> bool:
        status = self.delivery_status()
        return bool(status.get("delivery_done"))

    def delivery_status(self) -> dict[str, Any]:
        if self._done_status:
            return dict(self._done_status)
        status = self._dispatcher.request_status(self.request_id)
        if self._done:
            status["request_done"] = True
            status["delivery_done"] = True
            status["watermark_done"] = True
            status["request_watermark_done"] = True
        return status

    def request_watermark_done(self) -> bool:
        status = self.delivery_status()
        marker = status.get("request_watermark_done")
        if marker is not None:
            return bool(marker)
        request_done = bool(status.get("request_done"))
        watermark_done = status.get("watermark_done")
        if watermark_done is None:
            watermark_done = status.get("delivery_done")
        return request_done and bool(watermark_done)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._dispatcher.unsubscribe(self._subscriber_id, release_request=True)

    def __enter__(self) -> ChatEventSubscription:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.close()
        return False


ChatFlowStreamItem = ChatEventItem
ChatFlowStream = ChatEventSubscription


def run_chat_flow(
    *,
    request_id: str,
    run_id: str,
    session_id: str,
    model: str,
    message: str,
) -> list[StageEvent]:
    flow = get_chat_pipeline()
    payload = _build_chat_payload(
        request_id=request_id,
        run_id=run_id,
        session_id=session_id,
        model=model,
        message=message,
    )
    result = flow(payload)

    if not all(isinstance(item, StageEvent) for item in result):
        raise TypeError("Chat flow must emit StageEvent items only.")

    return cast(list[StageEvent], result)


def probe_chat_service_run(run: Any | None = None) -> bool:
    current = run
    if current is None:
        current = _SERVICE_RUN
    if current is None:
        return False

    status_fn = getattr(current, "status", None)
    if not callable(status_fn):
        return False
    try:
        status = str(status_fn())
    except Exception:
        return False
    if status != "running":
        return False

    ingress_state_fn = getattr(current, "ingress_state", None)
    if callable(ingress_state_fn):
        try:
            if str(ingress_state_fn()) == "closed":
                return False
        except Exception:
            return False

    return True


def ensure_chat_service_run(*, ordered_event_backpressure: str = "block"):
    global _SERVICE_RUN

    cached = _SERVICE_RUN
    if probe_chat_service_run(cached):
        _ = _ensure_chat_dispatcher(cached)
        return cached

    with _SERVICE_RUN_LOCK:
        cached = _SERVICE_RUN
        if probe_chat_service_run(cached):
            _ = _ensure_chat_dispatcher(cached)
            return cached
        run = _start_chat_service_run(
            ordered_event_backpressure=ordered_event_backpressure,
        )
        _SERVICE_RUN = run
        _ = _ensure_chat_dispatcher(run)
        return run


def bootstrap_chat_service(*, ordered_event_backpressure: str = "block") -> None:
    _ = get_chat_pipeline()
    _ = ensure_chat_service_run(
        ordered_event_backpressure=ordered_event_backpressure,
    )


def submit_chat_service_request(
    *,
    request_id: str,
    run_id: str,
    session_id: str,
    model: str,
    message: str,
    ordered_event_backpressure: str = "block",
) -> str:
    payload = _build_chat_payload(
        request_id=request_id,
        run_id=run_id,
        session_id=session_id,
        model=model,
        message=message,
    )
    run = ensure_chat_service_run(
        ordered_event_backpressure=ordered_event_backpressure,
    )
    dispatcher = _ensure_chat_dispatcher(run)
    runtime_request_id = _new_runtime_request_id(run)
    _ensure_request_started(run, runtime_request_id)
    dispatcher.bind_request(
        runtime_request_id=runtime_request_id,
        logical_request_id=request_id,
    )
    try:
        _publish_chat_ingress_payload(
            payload=payload,
            runtime_request_id=runtime_request_id,
            logical_request_id=request_id,
        )
        return runtime_request_id
    except Exception:
        _invalidate_service_run_if_current(run)
        run = ensure_chat_service_run(
            ordered_event_backpressure=ordered_event_backpressure,
        )
        _ = _ensure_chat_dispatcher(run)
        _ensure_request_started(run, runtime_request_id)
        _publish_chat_ingress_payload(
            payload=payload,
            runtime_request_id=runtime_request_id,
            logical_request_id=request_id,
        )
        return runtime_request_id


def _ensure_request_started(run: Any, runtime_request_id: str) -> None:
    if not runtime_request_id:
        return
    starter = getattr(run, "start_request", None)
    if not callable(starter):
        return
    try:
        starter(runtime_request_id)
    except Exception:
        pass


def open_chat_event_subscription(
    *,
    runtime_request_id: str,
    logical_request_id: str | None = None,
    ordered_event_backpressure: str = "block",
) -> ChatEventSubscription:
    run = ensure_chat_service_run(
        ordered_event_backpressure=ordered_event_backpressure,
    )
    dispatcher = _ensure_chat_dispatcher(run)
    return dispatcher.subscribe(
        runtime_request_id=runtime_request_id,
        logical_request_id=logical_request_id,
    )


def open_chat_service_stream(
    *,
    request_id: str,
    logical_request_id: str | None = None,
    ordered_event_backpressure: str = "block",
) -> ChatEventSubscription:
    return open_chat_event_subscription(
        runtime_request_id=request_id,
        logical_request_id=logical_request_id,
        ordered_event_backpressure=ordered_event_backpressure,
    )


def release_chat_service_request(run: Any, *, request_id: str) -> None:
    if not request_id:
        return

    output_getter = getattr(run, "output", None)
    output = output_getter("output") if callable(output_getter) else None
    if output is None:
        return

    finish = getattr(output, "finish", None)
    if callable(finish):
        try:
            finish(request_id)
        except Exception:
            pass

    release_request = getattr(output, "release_request", None)
    if callable(release_request):
        try:
            release_request(request_id)
        except Exception:
            pass
        return

    release_channel = getattr(output, "_release_request_channel", None)
    if callable(release_channel):
        try:
            release_channel(request_id)
        except Exception:
            pass


def reset_chat_service_run_for_tests() -> None:
    global _SERVICE_RUN
    global _SERVICE_DISPATCHER

    with _SERVICE_RUN_LOCK:
        run = _SERVICE_RUN
        dispatcher = _SERVICE_DISPATCHER
        _SERVICE_RUN = None
        _SERVICE_DISPATCHER = None

    if dispatcher is not None:
        dispatcher.stop()

    if run is None:
        return

    cancel = getattr(run, "cancel", None)
    if callable(cancel):
        try:
            cancel()
        except Exception:
            pass


def _start_chat_service_run(*, ordered_event_backpressure: str):
    return runtime_api.submit_flow(
        get_chat_pipeline(),
        ingress={
            "kind": "topic",
            "topic_id": _CHAT_INGRESS_TOPIC_ID,
            "event_type": _CHAT_INGRESS_EVENT_TYPE,
            "tags": {"channel": "sage.studio.chat"},
        },
        egress={
            "kind": "topic",
            "topic_id": _CHAT_EGRESS_TOPIC_ID,
            "event_type": _CHAT_EGRESS_EVENT_TYPE,
            "done_event_type": _CHAT_EGRESS_DONE_EVENT_TYPE,
            "error_event_type": _CHAT_EGRESS_ERROR_EVENT_TYPE,
            "tags": {"channel": "sage.studio.chat"},
        },
        run_config={
            "run_id": _next_service_run_id(),
            "ordered_event_backpressure": ordered_event_backpressure,
        },
    )


def _next_service_run_id() -> str:
    global _SERVICE_RUN_SEQ
    _SERVICE_RUN_SEQ += 1
    return f"sage-studio-chat-service-run-{_SERVICE_RUN_SEQ}"


def _invalidate_service_run_if_current(run: Any) -> None:
    global _SERVICE_RUN
    global _SERVICE_DISPATCHER
    dispatcher_to_stop: _SharedChatDispatcher | None = None
    with _SERVICE_RUN_LOCK:
        if _SERVICE_RUN is not run:
            return
        _SERVICE_RUN = None
        dispatcher = _SERVICE_DISPATCHER
        if dispatcher is not None and dispatcher.bound_to(run):
            dispatcher_to_stop = dispatcher
            _SERVICE_DISPATCHER = None
    if dispatcher_to_stop is not None:
        dispatcher_to_stop.stop()


def _ensure_chat_dispatcher(run: Any) -> _SharedChatDispatcher:
    global _SERVICE_DISPATCHER
    with _SERVICE_RUN_LOCK:
        dispatcher = _SERVICE_DISPATCHER
        if dispatcher is not None and dispatcher.bound_to(run):
            return dispatcher
        if dispatcher is not None:
            dispatcher.stop()
        dispatcher = _SharedChatDispatcher(run)
        _SERVICE_DISPATCHER = dispatcher
        return dispatcher


def _subscribe_chat_egress(dispatcher: _SharedChatDispatcher) -> _TopicEgressSubscription:
    forwarder = _TopicEventForwarder(dispatcher)
    actor_ref = runtime_api.make_object_actor(forwarder)
    sink_ref = ActorMethodRef(
        address=actor_ref.address,
        actor_id=actor_ref.actor_id,
        method="handle",
    )
    stream = fn.from_topic(_CHAT_EGRESS_TOPIC_ID).write(sink_ref).submit()
    return _TopicEgressSubscription(stream=stream)


def compile_chat_flow_task():
    return get_chat_pipeline().compile()


def list_chat_connector_topics() -> list[dict[str, Any]]:
    return [
        {
            "topic_id": _CHAT_INGRESS_TOPIC_ID,
            "uri": _topic_uri(_CHAT_INGRESS_TOPIC_ID),
            "role": "ingress",
            "event_types": [_CHAT_INGRESS_EVENT_TYPE],
            "channel": "sage.studio.chat",
        },
        {
            "topic_id": _CHAT_EGRESS_TOPIC_ID,
            "uri": _topic_uri(_CHAT_EGRESS_TOPIC_ID),
            "role": "egress",
            "event_types": [
                _CHAT_EGRESS_EVENT_TYPE,
                _CHAT_EGRESS_DONE_EVENT_TYPE,
                _CHAT_EGRESS_ERROR_EVENT_TYPE,
            ],
            "channel": "sage.studio.chat",
        },
    ]


def _build_chat_payload(
    *,
    request_id: str,
    run_id: str,
    session_id: str,
    model: str,
    message: str,
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "run_id": run_id,
        "session_id": session_id,
        "model": model,
        "message": message,
        "stage": "chat.receive",
    }


def _coerce_stage_event(payload: Any) -> StageEvent | None:
    if isinstance(payload, StageEvent):
        return payload
    if isinstance(payload, Mapping):
        try:
            return StageEvent.model_validate(dict(payload))
        except Exception:
            return None
    return None


def _to_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _publish_chat_ingress_payload(
    *,
    payload: dict[str, Any],
    runtime_request_id: str,
    logical_request_id: str,
) -> None:
    tags = {
        "request_id": runtime_request_id,
        "logical_request_id": logical_request_id,
        "channel": "sage.studio.chat",
    }
    fn.get_services().require_topics().emit_topic_event(
        _CHAT_INGRESS_TOPIC_ID,
        _CHAT_INGRESS_EVENT_TYPE,
        payload,
        tags,
    )


def _new_runtime_request_id(run: Any) -> str:
    new_request_id = getattr(run, "new_request_id", None)
    if callable(new_request_id):
        try:
            value = str(new_request_id()).strip()
            if value:
                return value
        except Exception:
            pass
    return uuid.uuid4().hex


def _topic_uri(topic_id: str) -> str:
    return f"topic://{quote(str(topic_id or '').strip(), safe='')}"


__all__ = [
    "ChatEventItem",
    "ChatEventSubscription",
    "ChatFlowStreamItem",
    "ChatFlowStream",
    "bootstrap_chat_service",
    "compile_chat_flow_task",
    "ensure_chat_service_run",
    "open_chat_event_subscription",
    "open_chat_service_stream",
    "list_chat_connector_topics",
    "probe_chat_service_run",
    "release_chat_service_request",
    "reset_chat_service_run_for_tests",
    "run_chat_flow",
    "submit_chat_service_request",
]
