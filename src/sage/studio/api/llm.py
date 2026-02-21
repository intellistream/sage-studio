"""LLM status and model selection endpoints.

Routes:
    GET  /api/llm/status  – Returns current LLM service status.
    POST /api/llm/select  – Selects a model / updates the active endpoint.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response schemas (must match the TypeScript LLMStatus interface in api.ts)
# ---------------------------------------------------------------------------


class AvailableModel(BaseModel):
    name: str
    base_url: str
    is_local: bool
    description: str | None = None
    healthy: bool | None = None
    engine_type: str | None = None
    device: str | None = None


class LLMStatusResponse(BaseModel):
    running: bool
    healthy: bool
    service_type: str  # 'gateway' | 'local' | 'remote' | 'none'
    model_name: str | None = None
    base_url: str | None = None
    is_local: bool = False
    available_models: list[AvailableModel] = []
    error: str | None = None


class SelectModelRequest(BaseModel):
    model_name: str
    base_url: str


# ---------------------------------------------------------------------------
# Active model selection (in-memory, single-process)
# ---------------------------------------------------------------------------

_selected: dict[str, str] = {}  # keys: "model_name", "base_url"

# Embedding-model name keywords — kept in sync with bootstrap.py
_EMBEDDING_KEYWORDS = ("bge-", "bge_", "embed", "text-embedding", "e5-", "m3e-", "gte-")


def _is_embedding_model(model_id: str) -> bool:
    """Return True if the model name looks like an embedding / non-chat model."""
    lower = model_id.lower()
    return any(kw in lower for kw in _EMBEDDING_KEYWORDS)


def _get_gateway_url() -> str:
    host = os.environ.get("SAGE_GATEWAY_HOST", "localhost")
    port = os.environ.get("SAGE_GATEWAY_PORT", "8889")
    return f"http://{host}:{port}"


async def _probe_gateway(gateway_url: str) -> dict[str, Any] | None:
    """Try to reach the Gateway's /v1/models or /health endpoint."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{gateway_url}/v1/models")
            if r.status_code == 200:
                return r.json()
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


def build_llm_router() -> APIRouter:
    router = APIRouter(prefix="/api/llm", tags=["llm"])

    @router.get("/status", response_model=LLMStatusResponse)
    async def get_llm_status() -> LLMStatusResponse:
        gateway_url = _get_gateway_url()
        models_data = await _probe_gateway(gateway_url)

        if models_data is None:
            # Gateway unreachable — return "not running" status
            return LLMStatusResponse(
                running=False,
                healthy=False,
                service_type="none",
                error="LLM service not available. Start it with: sage llm engine start <model>",
            )

        # Gateway is reachable — parse /v1/models response (OpenAI format)
        raw_models: list[dict[str, Any]] = models_data.get("data", [])

        # Separate chat models from embedding models for display
        all_models: list[AvailableModel] = []
        chat_model_names: list[str] = []
        for m in raw_models:
            model_id: str = m.get("id", "")
            if not model_id:
                continue
            is_embed = _is_embedding_model(model_id)
            all_models.append(
                AvailableModel(
                    name=model_id,
                    base_url=f"{gateway_url}/v1",
                    is_local=True,
                    healthy=True,
                    engine_type="embedding" if is_embed else "gateway",
                    description="Embedding model" if is_embed else None,
                )
            )
            if not is_embed:
                chat_model_names.append(model_id)

        # Show all models in UI, but default to a chat model
        available = all_models

        # Determine currently active model — prefer an explicitly selected chat model
        active_model = _selected.get("model_name")
        if not active_model:
            # Default to first chat model; fall back to first model if only embedding engines running
            active_model = (chat_model_names[0] if chat_model_names else None) or (
                available[0].name if available else None
            )
        active_base_url = _selected.get("base_url") or (f"{gateway_url}/v1" if available else None)

        return LLMStatusResponse(
            running=True,
            healthy=True,
            service_type="gateway",
            model_name=active_model,
            base_url=active_base_url,
            is_local=True,
            available_models=available,
        )

    @router.post("/select", status_code=200)
    async def select_model(body: SelectModelRequest) -> dict[str, str]:
        _selected["model_name"] = body.model_name
        _selected["base_url"] = body.base_url
        logger.info("LLM model selected: %s at %s", body.model_name, body.base_url)
        return {"status": "ok", "model_name": body.model_name}

    return router


__all__ = ["build_llm_router", "LLMStatusResponse"]
