from __future__ import annotations

import json
import urllib.request
import uuid

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from sage.studio.api.chat_sse import ChatSSEStreamAdapter
from sage.studio.api.llm import _get_gateway_url, _is_embedding_model, _selected
from sage.studio.contracts.models import RunKind, RunRef


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = Field(default="")
    messages: list[ChatMessage]
    session_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    stream: bool = True


class ChatRunCreateRequest(BaseModel):
    model: str = Field(min_length=1)
    session_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    message: str


class ChatRunAcceptedResponse(BaseModel):
    run: RunRef
    status: str
    stream_key: str
    model: str
    runtime_request_id: str


class ChatRunResponse(BaseModel):
    run_id: str
    request_id: str
    runtime_request_id: str


def build_chat_router() -> APIRouter:
    router = APIRouter(prefix="/api/chat/v1", tags=["chat-v1"])

    @router.post("/runs", response_model=ChatRunAcceptedResponse)
    async def create_chat_run(
        req: ChatRunCreateRequest,
        x_workspace_id: str | None = Header(default=None),
        x_user_id: str | None = Header(default=None),
        x_request_id: str | None = Header(default=None),
    ) -> ChatRunAcceptedResponse:
        from sage.studio.runtime.chat import submit_chat_service_request

        user_text = req.message.strip()
        if not user_text:
            raise HTTPException(status_code=400, detail="message must not be empty")

        request_id = (x_request_id or "").strip() or uuid.uuid4().hex
        workspace_id = (x_workspace_id or "workspace-dev").strip() or "workspace-dev"
        _ = (x_user_id or "dev-user").strip() or "dev-user"
        run_id = f"run-{request_id}"

        runtime_request_id = submit_chat_service_request(
            request_id=request_id,
            run_id=run_id,
            session_id=req.session_id,
            model=req.model,
            message=user_text,
        )
        return ChatRunAcceptedResponse(
            run=RunRef(
                run_id=run_id,
                request_id=request_id,
                workspace_id=workspace_id,
                kind=RunKind.CHAT,
            ),
            status="accepted",
            stream_key=run_id,
            model=req.model,
            runtime_request_id=runtime_request_id,
        )

    @router.get("/runs/{runtime_request_id}/events")
    async def stream_chat_run_events(
        runtime_request_id: str,
        model: str,
        request_id: str,
    ):
        from sage.studio.runtime.chat import open_chat_event_subscription

        subscription = open_chat_event_subscription(
            runtime_request_id=runtime_request_id,
            logical_request_id=request_id,
            ordered_event_backpressure="block",
        )
        adapter = ChatSSEStreamAdapter(
            subscription=subscription,
            request_id=request_id,
            model=model,
        )
        return StreamingResponse(adapter.iter_sse(), media_type="text/event-stream")

    @router.post("/chat/completions")
    async def chat_completions(
        req: ChatCompletionRequest,
        x_workspace_id: str | None = Header(default=None),
        x_user_id: str | None = Header(default=None),
        x_request_id: str | None = Header(default=None),
    ):
        from sage.studio.runtime.chat import (
            open_chat_event_subscription,
            submit_chat_service_request,
        )

        if not req.messages:
            raise HTTPException(status_code=400, detail="messages must not be empty")
        if not req.stream:
            raise HTTPException(status_code=400, detail="chat completions currently support stream=true only")

        user_text = req.messages[-1].content.strip()
        if not user_text:
            raise HTTPException(status_code=400, detail="last message content must not be empty")

        request_id = (x_request_id or "").strip() or uuid.uuid4().hex
        _ = (x_workspace_id or "workspace-dev").strip() or "workspace-dev"
        _ = (x_user_id or "dev-user").strip() or "dev-user"

        # Auto-resolve model if the frontend didn't specify one
        effective_model = req.model.strip() if req.model else ""
        if not effective_model:
            effective_model = _auto_resolve_chat_model()
        if not effective_model:
            raise HTTPException(
                status_code=503,
                detail="no_model_available: no LLM model found. Start an engine with: sage llm engine start <model>",
            )

        run_id = f"run-{request_id}"
        runtime_request_id = submit_chat_service_request(
            request_id=request_id,
            run_id=run_id,
            session_id=req.session_id,
            model=effective_model,
            message=user_text,
            ordered_event_backpressure="block",
        )
        subscription = open_chat_event_subscription(
            runtime_request_id=runtime_request_id,
            logical_request_id=request_id,
            ordered_event_backpressure="block",
        )
        adapter = ChatSSEStreamAdapter(
            subscription=subscription,
            request_id=request_id,
            model=effective_model,
        )
        return StreamingResponse(adapter.iter_sse(), media_type="text/event-stream")

    return router


def _auto_resolve_chat_model() -> str:
    """Best-effort model resolution: check selected state, then probe gateway."""
    selected = _selected.get("model_name", "").strip()
    if selected and not _is_embedding_model(selected):
        return selected

    gateway_url = _get_gateway_url()
    try:
        req = urllib.request.Request(
            f"{gateway_url}/v1/models",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
        for m in data.get("data", []):
            model_id = m.get("id", "")
            if model_id and not _is_embedding_model(model_id):
                return model_id
    except Exception:
        pass
    return ""


__all__ = ["ChatCompletionRequest", "ChatMessage", "build_chat_router"]
