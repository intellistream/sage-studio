from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from sage.studio.contracts.models import StageEvent, StageEventState
from sage.studio.runtime.chat import open_chat_event_subscription
from sage.studio.runtime.session_memory import get_session_memory_manager

_HISTORY_LIMIT = int(os.environ.get("STUDIO_VIDA_WS_HISTORY_LIMIT", "256"))
_POLL_TIMEOUT_S = float(os.environ.get("STUDIO_VIDA_WS_POLL_TIMEOUT_S", "0.2"))


@dataclass(slots=True)
class _SessionRuntimeContext:
    session_id: str
    request_id: str
    model: str
    runtime_request_id: str
    seen_step_ids: set[str] = field(default_factory=set)


class ConnectionManager:
    def __init__(self, *, history_limit: int = _HISTORY_LIMIT) -> None:
        self._history_limit = max(1, history_limit)
        self._lock = asyncio.Lock()
        self._session_sockets: dict[str, set[WebSocket]] = defaultdict(set)
        self._session_history: dict[str, deque[dict[str, Any]]] = {}
        self._stream_tasks: dict[str, asyncio.Task[None]] = {}
        self._runtime_to_session: dict[str, str] = {}
        self._assistant_buffers: dict[str, list[str]] = {}

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._session_sockets[session_id].add(websocket)
            history = list(self._session_history.get(session_id, []))

        if history:
            await self._safe_send_many(websocket, history)

    async def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            sockets = self._session_sockets.get(session_id)
            if sockets is None:
                return
            sockets.discard(websocket)
            if not sockets:
                self._session_sockets.pop(session_id, None)

    async def push_to_session(
        self, session_id: str, payload: dict[str, Any], *, persist: bool = True
    ) -> None:
        async with self._lock:
            if persist:
                history = self._session_history.get(session_id)
                if history is None:
                    history = deque(maxlen=self._history_limit)
                    self._session_history[session_id] = history
                history.append(dict(payload))
            sockets = list(self._session_sockets.get(session_id, set()))

        stale: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_json(payload)
            except Exception:
                stale.append(ws)

        if stale:
            async with self._lock:
                current = self._session_sockets.get(session_id)
                if current is not None:
                    for ws in stale:
                        current.discard(ws)
                    if not current:
                        self._session_sockets.pop(session_id, None)

    async def attach_runtime_stream(
        self,
        *,
        session_id: str,
        runtime_request_id: str,
        request_id: str,
        model: str,
    ) -> None:
        async with self._lock:
            existing = self._stream_tasks.get(runtime_request_id)
            if existing is not None and not existing.done():
                return
            context = _SessionRuntimeContext(
                session_id=session_id,
                request_id=request_id,
                model=model,
                runtime_request_id=runtime_request_id,
            )
            task = asyncio.create_task(
                self._pump_runtime_stream(context),
                name=f"vida_ws_runtime_{runtime_request_id}",
            )
            self._stream_tasks[runtime_request_id] = task
            self._runtime_to_session[runtime_request_id] = session_id
            self._assistant_buffers[runtime_request_id] = []

    async def _pump_runtime_stream(self, context: _SessionRuntimeContext) -> None:
        subscription = open_chat_event_subscription(
            runtime_request_id=context.runtime_request_id,
            logical_request_id=context.request_id,
            ordered_event_backpressure="block",
        )
        try:
            terminal = False
            while not terminal:
                item = await asyncio.to_thread(subscription.read_item, _POLL_TIMEOUT_S)
                if item is None:
                    continue
                payload, terminal = self._map_item(context, item)
                if payload is not None:
                    await self.push_to_session(context.session_id, payload, persist=True)
                if terminal:
                    await self._persist_assistant_message(context)
        finally:
            await asyncio.to_thread(subscription.close)
            async with self._lock:
                self._stream_tasks.pop(context.runtime_request_id, None)
                self._runtime_to_session.pop(context.runtime_request_id, None)
                self._assistant_buffers.pop(context.runtime_request_id, None)

    def _map_item(
        self, context: _SessionRuntimeContext, item: Any
    ) -> tuple[dict[str, Any] | None, bool]:
        if item.kind == "done":
            return (
                {
                    "type": "meta",
                    "status": "stream_end",
                    "message_id": context.request_id,
                    "session_id": context.session_id,
                    "model": context.model,
                    "runtime_request_id": context.runtime_request_id,
                    "timestamp": time.time(),
                },
                True,
            )

        if item.kind == "error":
            return (
                {
                    "type": "error",
                    "status": "failed",
                    "message_id": context.request_id,
                    "session_id": context.session_id,
                    "model": context.model,
                    "runtime_request_id": context.runtime_request_id,
                    "error": item.message or "runtime_error",
                    "timestamp": time.time(),
                },
                True,
            )

        if item.kind == "gap":
            return (
                {
                    "type": "meta",
                    "status": "notice",
                    "message_id": context.request_id,
                    "session_id": context.session_id,
                    "model": context.model,
                    "runtime_request_id": context.runtime_request_id,
                    "content": item.message or "event_gap",
                    "timestamp": time.time(),
                },
                False,
            )

        if item.kind == "notice":
            return (
                {
                    "type": "meta",
                    "status": "notice",
                    "message_id": context.request_id,
                    "session_id": context.session_id,
                    "model": context.model,
                    "runtime_request_id": context.runtime_request_id,
                    "content": item.message or "stream_notice",
                    "timestamp": time.time(),
                },
                False,
            )

        if item.kind != "event" or item.event is None:
            return None, False

        payload = self._map_stage_event(context, item.event)
        return payload, False

    def _map_stage_event(
        self, context: _SessionRuntimeContext, event: StageEvent
    ) -> dict[str, Any]:
        stage = event.stage
        step_type = self._stage_to_step_type(stage)

        common: dict[str, Any] = {
            "session_id": event.run_id,
            "message_id": event.request_id,
            "runtime_request_id": context.runtime_request_id,
            "model": context.model,
            "timestamp": time.time(),
        }

        if event.state in {StageEventState.FAILED, StageEventState.CANCELLED}:
            return {
                **common,
                "type": "step_update",
                "step_id": stage,
                "step_type": step_type,
                "status": "failed",
                "content": "",
                "error": event.message or "stage_failed",
            }

        if event.state == StageEventState.SUCCEEDED:
            if self._is_generation_stage(stage):
                self._append_assistant_chunk(context.runtime_request_id, event.message or "")
                payload = {
                    **common,
                    "type": "delta",
                    "content": event.message or "",
                }
                if event.metrics:
                    payload["metrics"] = event.metrics
                return payload
            return {
                **common,
                "type": "step_update",
                "step_id": stage,
                "step_type": step_type,
                "status": "completed",
                "content": event.message or "",
            }

        if self._is_generation_stage(stage):
            self._append_assistant_chunk(context.runtime_request_id, event.message or "")
            payload = {
                **common,
                "type": "delta",
                "content": event.message or "",
            }
            if event.metrics:
                payload["metrics"] = event.metrics
            return payload

        event_type = "step" if stage not in context.seen_step_ids else "step_update"
        context.seen_step_ids.add(stage)
        return {
            **common,
            "type": event_type,
            "step_id": stage,
            "step_type": step_type,
            "status": "running",
            "content": event.message or "",
        }

    @staticmethod
    def _is_generation_stage(stage: str) -> bool:
        return stage.startswith("chat.generation")

    @staticmethod
    def _stage_to_step_type(stage: str) -> str:
        kind = stage.split(".")[0]
        mapping = {
            "routing": "thinking",
            "retrieval": "retrieval",
            "agentic": "tool_call",
            "tool_call": "tool_call",
            "response": "response",
        }
        return mapping.get(kind, kind)

    async def _safe_send_many(
        self, websocket: WebSocket, payloads: Iterable[dict[str, Any]]
    ) -> None:
        for payload in payloads:
            await websocket.send_json(payload)

    def _append_assistant_chunk(self, runtime_request_id: str, chunk: str) -> None:
        if not chunk:
            return
        buffer = self._assistant_buffers.get(runtime_request_id)
        if buffer is None:
            return
        buffer.append(chunk)

    async def _persist_assistant_message(self, context: _SessionRuntimeContext) -> None:
        buffer = self._assistant_buffers.get(context.runtime_request_id, [])
        if not buffer:
            return

        content = "".join(buffer).strip()
        if not content:
            return

        session_memory = get_session_memory_manager()
        await session_memory.remember_message(
            session_id=context.session_id,
            role="assistant",
            content=content,
            metadata={
                "request_id": context.request_id,
                "runtime_request_id": context.runtime_request_id,
                "model": context.model,
                "source": "chat_stream",
            },
        )


connection_manager = ConnectionManager()


__all__ = ["ConnectionManager", "connection_manager"]
