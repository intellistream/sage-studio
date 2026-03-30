from __future__ import annotations

from typing import Any

import httpx

from sage.studio.runtime.endpoints.contracts import EndpointProvider

_OPENAI_STYLE_PROVIDERS = {
    EndpointProvider.ALIBABA_DASHSCOPE,
    EndpointProvider.OPENAI,
    EndpointProvider.OPENROUTER,
    EndpointProvider.GROQ,
    EndpointProvider.OLLAMA,
    EndpointProvider.OPENAI_COMPATIBLE,
    EndpointProvider.AZURE_OPENAI,
}

_FALLBACK_MODELS: dict[EndpointProvider, tuple[str, ...]] = {
    EndpointProvider.ALIBABA_DASHSCOPE: ("qwen-plus", "qwen-turbo", "qwen-max"),
    EndpointProvider.OPENAI: ("gpt-4.1-mini", "gpt-4o-mini"),
    EndpointProvider.ANTHROPIC: ("claude-3-7-sonnet-latest", "claude-3-5-haiku-latest"),
    EndpointProvider.OPENROUTER: ("openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet"),
    EndpointProvider.GROQ: ("llama-3.3-70b-versatile", "llama-3.1-8b-instant"),
    EndpointProvider.AZURE_OPENAI: ("gpt-4o-mini",),
    EndpointProvider.GEMINI: ("gemini-2.0-flash", "gemini-1.5-pro"),
    EndpointProvider.OLLAMA: ("llama3.1:8b", "qwen2.5:7b"),
    EndpointProvider.OPENAI_COMPATIBLE: ("model-1",),
}


def discover_models_for_endpoint(
    *,
    provider: EndpointProvider,
    base_url: str,
    api_key: str | None,
    timeout_s: float = 8.0,
) -> tuple[str, ...]:
    urls = _candidate_urls(provider=provider, base_url=base_url)
    headers = _build_headers(provider=provider, api_key=api_key)

    for url in urls:
        try:
            with httpx.Client(timeout=timeout_s) as client:
                response = client.get(url, headers=headers)
                response.raise_for_status()
                discovered = _extract_model_ids(response.json())
                if discovered:
                    return discovered
        except (httpx.HTTPError, ValueError, TypeError):
            continue

    fallback = _FALLBACK_MODELS.get(provider, ())
    return tuple(fallback)


def _candidate_urls(*, provider: EndpointProvider, base_url: str) -> tuple[str, ...]:
    normalized = base_url.strip().rstrip("/")
    if not normalized:
        return ()
    root = _to_api_root(normalized)
    if provider in _OPENAI_STYLE_PROVIDERS:
        return (f"{root}/models",)
    if provider == EndpointProvider.ANTHROPIC:
        return (f"{root}/models",)
    if provider == EndpointProvider.GEMINI:
        return (f"{root}/models",)
    return (f"{root}/models",)


def _to_api_root(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized[: -len("/chat/completions")]
    if normalized.endswith("/completions"):
        return normalized[: -len("/completions")]
    return normalized


def _build_headers(*, provider: EndpointProvider, api_key: str | None) -> dict[str, str]:
    headers: dict[str, str] = {"accept": "application/json"}
    token = (api_key or "").strip()
    if provider == EndpointProvider.ANTHROPIC:
        if token:
            headers["x-api-key"] = token
        headers["anthropic-version"] = "2023-06-01"
        return headers
    if token:
        headers["authorization"] = f"Bearer {token}"
    return headers


def _extract_model_ids(payload: Any) -> tuple[str, ...]:
    if isinstance(payload, dict):
        for key in ("data", "models"):
            container = payload.get(key)
            extracted = _extract_from_sequence(container)
            if extracted:
                return extracted
    if isinstance(payload, list):
        extracted = _extract_from_sequence(payload)
        if extracted:
            return extracted
    return ()


def _extract_from_sequence(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    seen: set[str] = set()
    model_ids: list[str] = []
    for item in value:
        model_id = _extract_id(item)
        if not model_id:
            continue
        if model_id in seen:
            continue
        seen.add(model_id)
        model_ids.append(model_id)
    return tuple(model_ids)


def _extract_id(item: Any) -> str | None:
    if isinstance(item, str):
        value = item.strip()
        return value or None
    if isinstance(item, dict):
        for key in ("id", "model", "name"):
            raw = item.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    return None


__all__ = ["discover_models_for_endpoint"]
