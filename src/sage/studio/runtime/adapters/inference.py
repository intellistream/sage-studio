from __future__ import annotations

import os
from typing import Any

import httpx

from sage.studio.runtime.endpoints import ResolvedEndpoint


class InferenceCallError(RuntimeError):
    pass


def request_chat_completion(*, endpoint: ResolvedEndpoint, message: str, timeout_s: float = 30.0) -> str:
    url = _build_chat_completions_url(endpoint.base_url)
    headers = {
        "content-type": "application/json",
    }
    if endpoint.api_key:
        headers["authorization"] = f"Bearer {endpoint.api_key}"

    for key, value in endpoint.extra_headers:
        normalized_key = key.strip()
        if not normalized_key:
            continue
        headers[normalized_key] = value

    max_tokens = _resolve_max_tokens()
    request_timeout_s = _resolve_timeout(timeout_s)

    payload = {
        "model": endpoint.model_id,
        "messages": [
            {
                "role": "user",
                "content": message,
            }
        ],
        "stream": False,
        "max_tokens": max_tokens,
    }

    try:
        with httpx.Client(timeout=request_timeout_s) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        raise InferenceCallError(f"provider_http_error:{type(exc).__name__}") from exc
    except ValueError as exc:
        raise InferenceCallError("provider_response_not_json") from exc

    content = _extract_text_content(data)
    if content is None:
        raise InferenceCallError("provider_response_missing_content")
    return content


def _build_chat_completions_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _extract_text_content(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None

    message = first.get("message")
    if isinstance(message, dict):
        text = message.get("content")
        if isinstance(text, str):
            return text.strip()

    text = first.get("text")
    if isinstance(text, str):
        return text.strip()

    delta = first.get("delta")
    if isinstance(delta, dict):
        delta_text = delta.get("content")
        if isinstance(delta_text, str):
            return delta_text.strip()

    return None


def _resolve_max_tokens() -> int:
    raw = os.environ.get("STUDIO_CHAT_MAX_TOKENS", "128").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 128
    return max(16, min(value, 512))


def _resolve_timeout(default_timeout_s: float) -> float:
    raw = os.environ.get("STUDIO_CHAT_PROVIDER_TIMEOUT_S", "90").strip()
    try:
        configured = float(raw)
    except ValueError:
        configured = 90.0
    return max(10.0, configured, default_timeout_s)


__all__ = ["InferenceCallError", "request_chat_completion"]
