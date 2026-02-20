from __future__ import annotations

import os
import threading

from sage.studio.runtime.endpoints.contracts import EndpointCreate, EndpointProvider
from sage.studio.runtime.endpoints.registry import get_endpoint_registry

_BOOTSTRAP_LOCK = threading.Lock()
_BOOTSTRAPPED = False


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


def reset_endpoint_bootstrap_state() -> None:
    global _BOOTSTRAPPED
    with _BOOTSTRAP_LOCK:
        _BOOTSTRAPPED = False


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


__all__ = ["bootstrap_dashscope_endpoint_from_env", "reset_endpoint_bootstrap_state"]
