from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from sage.studio.api.chat import _auto_resolve_chat_model
from sage.studio.runtime.chat import submit_chat_service_request
from sage.studio.runtime.connection_manager import connection_manager
from sage.studio.runtime.session_memory import get_session_memory_manager


class VidaWSChatRequest(BaseModel):
    type: str = Field(default="chat")
    message: str
    model: str = Field(default="")
    request_id: str | None = None


def build_vida_ws_router() -> APIRouter:
    router = APIRouter(prefix="/vida/ws", tags=["vida-ws"])

    @router.websocket("/session/{session_id}")
    async def vida_session(websocket: WebSocket, session_id: str) -> None:
        await websocket.accept()
        await connection_manager.connect(session_id, websocket)

        session_memory = get_session_memory_manager()
        restored = await session_memory.on_session_connected(session_id)
        restored_working = restored.get("working", [])
        restored_episodic = restored.get("episodic", [])

        await connection_manager.push_to_session(
            session_id,
            {
                "type": "meta",
                "status": "connected",
                "session_id": session_id,
                "restored": {
                    "working_count": len(restored_working),
                    "episodic_count": len(restored_episodic),
                },
                "timestamp": time.time(),
            },
            persist=False,
        )

        if restored_working or restored_episodic:
            await connection_manager.push_to_session(
                session_id,
                {
                    "type": "session_restore",
                    "status": "ok",
                    "session_id": session_id,
                    "working": restored_working,
                    "episodic": restored_episodic,
                    "timestamp": time.time(),
                },
                persist=True,
            )

        try:
            while True:
                incoming = await websocket.receive_json()
                if not isinstance(incoming, dict):
                    await _send_ws_error(
                        session_id=session_id,
                        message="invalid_payload: json object expected",
                    )
                    continue

                msg_type = str(incoming.get("type", "chat")).strip().lower()
                if msg_type == "ping":
                    await connection_manager.push_to_session(
                        session_id,
                        {
                            "type": "pong",
                            "session_id": session_id,
                            "timestamp": time.time(),
                        },
                        persist=False,
                    )
                    continue

                if msg_type == "notify":
                    await connection_manager.push_to_session(
                        session_id,
                        {
                            "type": "notification",
                            "status": "notice",
                            "session_id": session_id,
                            "content": str(incoming.get("content", "")),
                            "timestamp": time.time(),
                        },
                        persist=True,
                    )
                    continue

                if msg_type != "chat":
                    await _send_ws_error(
                        session_id=session_id,
                        message=f"unsupported_type: {msg_type}",
                    )
                    continue

                await _handle_chat_message(session_id=session_id, raw=incoming)

        except WebSocketDisconnect:
            await connection_manager.disconnect(session_id, websocket)
        except Exception as exc:  # noqa: BLE001
            await _send_ws_error(session_id=session_id, message=f"websocket_error: {exc}")
            await connection_manager.disconnect(session_id, websocket)

    return router


async def _handle_chat_message(*, session_id: str, raw: dict[str, Any]) -> None:
    parsed = VidaWSChatRequest.model_validate(raw)
    user_text = parsed.message.strip()
    if not user_text:
        await _send_ws_error(session_id=session_id, message="message must not be empty")
        return

    request_id = (parsed.request_id or "").strip() or uuid.uuid4().hex
    run_id = f"run-{request_id}"

    effective_model = parsed.model.strip() if parsed.model else ""
    if not effective_model:
        effective_model = _auto_resolve_chat_model()
    if not effective_model:
        await _send_ws_error(
            session_id=session_id,
            message="no_model_available: start an engine first",
            request_id=request_id,
        )
        return

    session_memory = get_session_memory_manager()
    memory_prefix = await session_memory.build_prompt_context(
        session_id=session_id, query=user_text
    )
    runtime_message = user_text
    if memory_prefix:
        runtime_message = f"{memory_prefix}\n\n[Current User Message]\n{user_text}"

    await session_memory.remember_message(
        session_id=session_id,
        role="user",
        content=user_text,
        metadata={
            "request_id": request_id,
            "model": effective_model,
            "source": "vida_ws",
        },
    )

    runtime_request_id = submit_chat_service_request(
        request_id=request_id,
        run_id=run_id,
        session_id=session_id,
        model=effective_model,
        message=runtime_message,
        ordered_event_backpressure="block",
    )

    await connection_manager.attach_runtime_stream(
        session_id=session_id,
        runtime_request_id=runtime_request_id,
        request_id=request_id,
        model=effective_model,
    )

    await connection_manager.push_to_session(
        session_id,
        {
            "type": "meta",
            "status": "accepted",
            "session_id": session_id,
            "message_id": request_id,
            "runtime_request_id": runtime_request_id,
            "model": effective_model,
            "timestamp": time.time(),
        },
        persist=True,
    )


async def _send_ws_error(*, session_id: str, message: str, request_id: str | None = None) -> None:
    await connection_manager.push_to_session(
        session_id,
        {
            "type": "error",
            "status": "failed",
            "session_id": session_id,
            "message_id": request_id,
            "error": message,
            "timestamp": time.time(),
        },
        persist=False,
    )


__all__ = ["build_vida_ws_router"]
