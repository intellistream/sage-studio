from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from sage.studio.runtime.endpoints import ResolvedEndpoint


class InferenceCallError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChatCompletionResult:
    content: str
    metrics: dict[str, Any] | None = None


def request_chat_completion(
    *, endpoint: ResolvedEndpoint, message: str, timeout_s: float = 30.0
) -> ChatCompletionResult:
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
    return ChatCompletionResult(content=content, metrics=_extract_metrics(data))


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


def _extract_metrics(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    top_metrics = payload.get("metrics")
    if isinstance(top_metrics, dict) and top_metrics:
        return top_metrics

    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            choice_metrics = first.get("metrics")
            if isinstance(choice_metrics, dict) and choice_metrics:
                return choice_metrics
            delta = first.get("delta")
            if isinstance(delta, dict):
                delta_metrics = delta.get("metrics")
                if isinstance(delta_metrics, dict) and delta_metrics:
                    return delta_metrics

    usage = payload.get("usage")
    if isinstance(usage, dict) and usage and _contains_rate_metric(usage):
        return usage

    return None


def _contains_rate_metric(metrics: dict[str, Any]) -> bool:
    metric_keys = {
        "tokens_per_second",
        "token_per_second",
        "throughput_tps",
        "tps",
    }
    return any(key in metrics for key in metric_keys)


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


__all__ = ["ChatCompletionResult", "InferenceCallError", "request_chat_completion"]
