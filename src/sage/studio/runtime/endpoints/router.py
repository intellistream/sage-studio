from __future__ import annotations

from dataclasses import dataclass

from sage.studio.runtime.endpoints.bootstrap import bootstrap_dashscope_endpoint_from_env
from sage.studio.runtime.endpoints.registry import get_endpoint_registry
from sage.studio.runtime.endpoints.secrets import decrypt_endpoint_secret


@dataclass(slots=True, frozen=True)
class ResolvedEndpoint:
    endpoint_id: str
    provider: str
    base_url: str
    model_id: str
    matched_model: bool
    api_key: str | None
    extra_headers: tuple[tuple[str, str], ...]


def resolve_endpoint_for_model(model_id: str) -> ResolvedEndpoint | None:
    bootstrap_dashscope_endpoint_from_env()

    normalized_model = model_id.strip()
    if not normalized_model:
        return None

    registry = get_endpoint_registry()
    endpoint = registry.resolve_endpoint_for_model(normalized_model)
    if endpoint is None:
        return None
    try:
        decrypted_key = decrypt_endpoint_secret(endpoint.api_key)
    except ValueError:
        decrypted_key = None

    return ResolvedEndpoint(
        endpoint_id=endpoint.endpoint_id,
        provider=endpoint.provider.value,
        base_url=endpoint.base_url,
        model_id=normalized_model,
        matched_model=normalized_model in endpoint.model_ids,
        api_key=decrypted_key,
        extra_headers=endpoint.extra_headers,
    )


__all__ = ["ResolvedEndpoint", "resolve_endpoint_for_model"]
