from __future__ import annotations

import json
import os
import threading
import urllib.request

from sage.studio.runtime.endpoints.contracts import EndpointCreate, EndpointProvider
from sage.studio.runtime.endpoints.registry import get_endpoint_registry

_BOOTSTRAP_LOCK = threading.Lock()
_BOOTSTRAPPED = False
_GATEWAY_BOOTSTRAPPED = False

# Heuristics for identifying embedding / non-chat models by name
_EMBEDDING_KEYWORDS = ("bge-", "bge_", "embed", "text-embedding", "e5-", "m3e-", "gte-")


def bootstrap_dashscope_endpoint_from_env() -> None:
    global _BOOTSTRAPPED

    with _BOOTSTRAP_LOCK:
        if _BOOTSTRAPPED:
            return
        _BOOTSTRAPPED = True

        api_key = _resolve_dashscope_api_key()
        if not api_key:
            return

        endpoint_id = os.environ.get("STUDIO_DASHSCOPE_ENDPOINT_ID", "ep-dashscope-default").strip() or "ep-dashscope-default"
        endpoint = os.environ.get(
            "STUDIO_DASHSCOPE_ENDPOINT",
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        ).strip()
        model = os.environ.get("STUDIO_DASHSCOPE_MODEL", "qwen-plus").strip() or "qwen-plus"

        registry = get_endpoint_registry()
        if registry.get_endpoint(endpoint_id) is not None:
            return
        has_existing = bool(registry.list_endpoints())

        registry.create_endpoint(
            EndpointCreate(
                endpoint_id=endpoint_id,
                provider=EndpointProvider.ALIBABA_DASHSCOPE,
                display_name="Alibaba DashScope",
                base_url=endpoint,
                model_ids=(model,),
                enabled=True,
                is_default=(not has_existing),
                api_key=api_key,
            )
        )


def bootstrap_gateway_endpoint_from_env() -> None:
    """Probe the local SAGE Gateway and register its chat models in the endpoint registry.

    Uses a synchronous HTTP call so it can be invoked from worker threads.
    Embedding-only models (bge-*, embed*, etc.) are excluded.
    Uses the placeholder key ``sk-local`` so the inference guard allows the call.
    """
    global _GATEWAY_BOOTSTRAPPED

    with _BOOTSTRAP_LOCK:
        if _GATEWAY_BOOTSTRAPPED:
            return
        _GATEWAY_BOOTSTRAPPED = True

        host = os.environ.get("SAGE_GATEWAY_HOST", "localhost")
        port = os.environ.get("SAGE_GATEWAY_PORT", "8889")
        gateway_base = f"http://{host}:{port}"

        # Synchronous probe — must not use asyncio here (called from thread worker)
        try:
            req = urllib.request.Request(
                f"{gateway_base}/v1/models",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read())
        except Exception:
            # Gateway not reachable — skip silently
            return

        raw_models: list[dict] = data.get("data", [])
        chat_model_ids = tuple(
            m["id"]
            for m in raw_models
            if m.get("id") and not _is_embedding_model(m["id"])
        )

        if not chat_model_ids:
            return

        registry = get_endpoint_registry()
        endpoint_id = "ep-sage-gateway-local"

        existing = registry.get_endpoint(endpoint_id)
        if existing is not None:
            # Already registered — nothing more to do (model list is stable)
            return

        has_existing = bool(registry.list_endpoints())
        registry.create_endpoint(
            EndpointCreate(
                endpoint_id=endpoint_id,
                provider=EndpointProvider.OPENAI_COMPATIBLE,
                display_name="SAGE Local Gateway",
                base_url=f"{gateway_base}/v1",
                model_ids=chat_model_ids,
                enabled=True,
                is_default=(not has_existing),
                api_key="sk-local",  # placeholder — gateway does not require auth
            )
        )


def _is_embedding_model(model_id: str) -> bool:
    """Return True if the model name looks like an embedding / non-chat model."""
    lower = model_id.lower()
    return any(kw in lower for kw in _EMBEDDING_KEYWORDS)


def reset_endpoint_bootstrap_state() -> None:
    global _BOOTSTRAPPED, _GATEWAY_BOOTSTRAPPED
    with _BOOTSTRAP_LOCK:
        _BOOTSTRAPPED = False
        _GATEWAY_BOOTSTRAPPED = False


def _resolve_dashscope_api_key() -> str | None:
    env_candidates = (
        "STUDIO_ALIBABA_API_KEY",
        "ALIBABA_API_KEY",
        "DASHSCOPE_API_KEY",
    )
    for key_name in env_candidates:
        value = os.environ.get(key_name)
        if value and value.strip():
            return value.strip()

    key_file = os.environ.get("STUDIO_ALIBABA_API_KEY_FILE")
    if key_file and key_file.strip():
        try:
            content = open(key_file.strip(), "r", encoding="utf-8").read().strip()
        except OSError:
            return None
        return content or None

    return None


__all__ = [
    "bootstrap_dashscope_endpoint_from_env",
    "bootstrap_gateway_endpoint_from_env",
    "reset_endpoint_bootstrap_state",
]
