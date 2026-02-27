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
    embedding_models: list[AvailableModel] = []
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
_DEFAULT_CHAT_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"


def _is_embedding_model(model_id: str) -> bool:
    """Return True if the model name looks like an embedding / non-chat model."""
    lower = model_id.lower()
    return any(kw in lower for kw in _EMBEDDING_KEYWORDS)


def _get_gateway_url() -> str:
    host = os.environ.get("SAGE_GATEWAY_HOST", "localhost")
    port = os.environ.get("SAGE_GATEWAY_PORT", "8889")
    return f"http://{host}:{port}"


def _preferred_chat_model_name() -> str:
    configured = os.environ.get("SAGE_DEFAULT_MODEL", _DEFAULT_CHAT_MODEL).strip()
    return configured or _DEFAULT_CHAT_MODEL


def _pick_active_chat_model(chat_model_names: list[str]) -> str | None:
    if not chat_model_names:
        return None

    selected = _selected.get("model_name", "").strip()
    if selected and selected in chat_model_names and not _is_embedding_model(selected):
        return selected

    preferred = _preferred_chat_model_name()
    if preferred in chat_model_names:
        return preferred

    return chat_model_names[0]


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


async def _try_auto_register_local_llm_engines(gateway_url: str) -> bool:
    """Best-effort: register healthy local LLM engines into Gateway control plane.

    Returns True if at least one registration call succeeded.
    """
    candidate_ports = [*range(8901, 8911), 8001]
    register_url = f"{gateway_url}/v1/management/engines/register"
    any_registered = False

    async with httpx.AsyncClient(timeout=2.0) as client:
        for port in candidate_ports:
            try:
                health = await client.get(f"http://127.0.0.1:{port}/health")
                if health.status_code != 200:
                    continue
            except Exception:
                continue

            model_name: str | None = None
            try:
                models_resp = await client.get(f"http://127.0.0.1:{port}/v1/models")
                if models_resp.status_code == 200:
                    data = models_resp.json()
                    models = data.get("data", []) if isinstance(data, dict) else []
                    if models:
                        model_name = models[0].get("id")
            except Exception:
                pass

            if not model_name:
                try:
                    info_resp = await client.get(f"http://127.0.0.1:{port}/info")
                    if info_resp.status_code == 200:
                        info = info_resp.json()
                        if isinstance(info, dict):
                            model_name = info.get("model")
                except Exception:
                    pass

            if not model_name:
                continue

            payload = {
                "engine_id": f"engine-llm-{port}",
                "model_id": model_name,
                "host": "127.0.0.1",
                "port": port,
                "engine_kind": "llm",
            }
            try:
                register_resp = await client.post(register_url, json=payload)
                if register_resp.status_code in (200, 201):
                    any_registered = True
            except Exception:
                pass

    return any_registered


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

        # If only embedding/no chat models are visible, try a one-shot local auto-registration.
        if not any(
            (m.get("id") and not _is_embedding_model(m.get("id", "")))
            for m in raw_models
        ):
            if await _try_auto_register_local_llm_engines(gateway_url):
                refreshed = await _probe_gateway(gateway_url)
                if refreshed is not None:
                    raw_models = refreshed.get("data", [])

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

        # Separate chat models from embedding models in response
        available = [m for m in all_models if m.engine_type != "embedding"]
        embedding_models_list = [m for m in all_models if m.engine_type == "embedding"]

        # Determine currently active model — prefer an explicitly selected chat model
        active_model = _pick_active_chat_model(chat_model_names)
        active_base_url = _selected.get("base_url") or (f"{gateway_url}/v1" if available else None)

        return LLMStatusResponse(
            running=True,
            healthy=True,
            service_type="gateway",
            model_name=active_model,
            base_url=active_base_url,
            is_local=True,
            available_models=available,
            embedding_models=embedding_models_list,
        )

    @router.post("/select", status_code=200)
    async def select_model(body: SelectModelRequest) -> dict[str, str]:
        _selected["model_name"] = body.model_name
        _selected["base_url"] = body.base_url
        logger.info("LLM model selected: %s at %s", body.model_name, body.base_url)
        return {"status": "ok", "model_name": body.model_name}

    return router


__all__ = ["build_llm_router", "LLMStatusResponse"]
