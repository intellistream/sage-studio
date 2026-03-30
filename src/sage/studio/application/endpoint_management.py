from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sage.studio.runtime.endpoints import (
    EndpointCreate,
    EndpointProvider,
    EndpointProviderPreset,
    EndpointUpdate,
    ManagedEndpoint,
    get_endpoint_registry,
)
from sage.studio.runtime.endpoints.model_discovery import discover_models_for_endpoint
from sage.studio.runtime.endpoints.secrets import decrypt_endpoint_secret, mask_endpoint_secret


@dataclass(slots=True, frozen=True)
class EndpointUpsertRequest:
    endpoint_id: str
    provider: EndpointProvider
    display_name: str
    base_url: str
    model_ids: tuple[str, ...] = ()
    enabled: bool = True
    is_default: bool = False
    auto_discover_models: bool = False
    extra_headers: tuple[tuple[str, str], ...] = ()
    api_key: str | None = None


@dataclass(slots=True, frozen=True)
class EndpointPatchRequest:
    display_name: str | None = None
    base_url: str | None = None
    model_ids: tuple[str, ...] | None = None
    enabled: bool | None = None
    is_default: bool | None = None
    extra_headers: tuple[tuple[str, str], ...] | None = None
    replace_api_key: bool = False
    api_key: str | None = None


@dataclass(slots=True, frozen=True)
class EndpointView:
    endpoint_id: str
    provider: str
    display_name: str
    base_url: str
    model_ids: tuple[str, ...]
    enabled: bool
    is_default: bool
    extra_headers: tuple[tuple[str, str], ...]
    has_api_key: bool
    api_key_masked: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class EndpointProviderView:
    provider: str
    display_name: str
    default_base_url: str
    default_model_ids: tuple[str, ...]
    default_extra_headers: tuple[tuple[str, str], ...]
    requires_api_key: bool
    notes: str


def list_provider_presets() -> list[EndpointProviderView]:
    registry = get_endpoint_registry()
    return [_provider_to_view(item) for item in registry.list_provider_presets()]


def list_endpoints() -> list[EndpointView]:
    registry = get_endpoint_registry()
    return [_endpoint_to_view(item) for item in registry.list_endpoints()]


def get_endpoint(endpoint_id: str) -> EndpointView | None:
    registry = get_endpoint_registry()
    record = registry.get_endpoint(endpoint_id)
    if record is None:
        return None
    return _endpoint_to_view(record)


def create_endpoint(command: EndpointUpsertRequest) -> EndpointView:
    registry = get_endpoint_registry()
    normalized_model_ids = _normalize_model_ids(command.model_ids)
    created = registry.create_endpoint(
        EndpointCreate(
            endpoint_id=command.endpoint_id.strip(),
            provider=command.provider,
            display_name=_require_non_empty(command.display_name, field="display_name"),
            base_url=_require_non_empty(command.base_url, field="base_url"),
            model_ids=normalized_model_ids,
            enabled=command.enabled,
            is_default=command.is_default,
            extra_headers=_normalize_headers(command.extra_headers),
            api_key=_normalize_optional_secret(command.api_key),
        )
    )
    if command.auto_discover_models and not normalized_model_ids:
        discovered_models = _discover_models_for_record(created)
        created = registry.update_endpoint(
            created.endpoint_id,
            EndpointUpdate(
                model_ids=discovered_models,
            ),
        )
    return _endpoint_to_view(created)


def update_endpoint(endpoint_id: str, command: EndpointPatchRequest) -> EndpointView:
    registry = get_endpoint_registry()
    updated = registry.update_endpoint(
        endpoint_id.strip(),
        EndpointUpdate(
            display_name=_normalize_optional_text(command.display_name, field="display_name"),
            base_url=_normalize_optional_text(command.base_url, field="base_url"),
            model_ids=_normalize_model_ids(command.model_ids)
            if command.model_ids is not None
            else None,
            enabled=command.enabled,
            is_default=command.is_default,
            extra_headers=_normalize_headers(command.extra_headers)
            if command.extra_headers is not None
            else None,
            replace_api_key=command.replace_api_key,
            api_key=_normalize_optional_secret(command.api_key),
        ),
    )
    return _endpoint_to_view(updated)


def set_endpoint_enabled(endpoint_id: str, enabled: bool) -> EndpointView:
    registry = get_endpoint_registry()
    updated = registry.set_enabled(endpoint_id.strip(), enabled)
    return _endpoint_to_view(updated)


def set_default_endpoint(endpoint_id: str) -> EndpointView:
    registry = get_endpoint_registry()
    updated = registry.set_default(endpoint_id.strip())
    return _endpoint_to_view(updated)


def delete_endpoint(endpoint_id: str) -> None:
    registry = get_endpoint_registry()
    registry.delete_endpoint(endpoint_id.strip())


def refresh_endpoint_models(endpoint_id: str) -> EndpointView:
    registry = get_endpoint_registry()
    endpoint = registry.get_endpoint(endpoint_id.strip())
    if endpoint is None:
        raise KeyError(endpoint_id)
    discovered_models = _discover_models_for_record(endpoint)
    updated = registry.update_endpoint(
        endpoint.endpoint_id,
        EndpointUpdate(model_ids=discovered_models),
    )
    return _endpoint_to_view(updated)


def resolve_endpoint_for_model(model_id: str) -> EndpointView | None:
    registry = get_endpoint_registry()
    resolved = registry.resolve_endpoint_for_model(model_id)
    if resolved is None:
        return None
    return _endpoint_to_view(resolved)


def _endpoint_to_view(record: ManagedEndpoint) -> EndpointView:
    return EndpointView(
        endpoint_id=record.endpoint_id,
        provider=record.provider.value,
        display_name=record.display_name,
        base_url=record.base_url,
        model_ids=record.model_ids,
        enabled=record.enabled,
        is_default=record.is_default,
        extra_headers=record.extra_headers,
        has_api_key=bool(record.api_key),
        api_key_masked=mask_endpoint_secret(record.api_key),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _provider_to_view(record: EndpointProviderPreset) -> EndpointProviderView:
    return EndpointProviderView(
        provider=record.provider.value,
        display_name=record.display_name,
        default_base_url=record.default_base_url,
        default_model_ids=record.default_model_ids,
        default_extra_headers=record.default_extra_headers,
        requires_api_key=record.requires_api_key,
        notes=record.notes,
    )


def _normalize_model_ids(model_ids: tuple[str, ...] | None) -> tuple[str, ...]:
    if not model_ids:
        return ()
    normalized: list[str] = []
    seen: set[str] = set()
    for item in model_ids:
        value = item.strip()
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return tuple(normalized)


def _normalize_headers(headers: tuple[tuple[str, str], ...] | None) -> tuple[tuple[str, str], ...]:
    if not headers:
        return ()
    normalized: list[tuple[str, str]] = []
    seen: set[str] = set()
    for key, value in headers:
        normalized_key = key.strip()
        normalized_value = value.strip()
        if not normalized_key:
            continue
        dedupe_key = normalized_key.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append((normalized_key, normalized_value))
    return tuple(normalized)


def _normalize_optional_secret(secret: str | None) -> str | None:
    if secret is None:
        return None
    normalized = secret.strip()
    if not normalized:
        return None
    return normalized


def _normalize_optional_text(value: str | None, *, field: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} must not be empty")
    return normalized


def _require_non_empty(value: str, *, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} must not be empty")
    return normalized


def _discover_models_for_record(record: ManagedEndpoint) -> tuple[str, ...]:
    api_key = decrypt_endpoint_secret(record.api_key)
    discovered = discover_models_for_endpoint(
        provider=record.provider,
        base_url=record.base_url,
        api_key=api_key,
    )
    if not discovered:
        raise ValueError("model discovery returned empty list")
    return discovered


__all__ = [
    "EndpointPatchRequest",
    "EndpointProviderView",
    "EndpointUpsertRequest",
    "EndpointView",
    "create_endpoint",
    "delete_endpoint",
    "get_endpoint",
    "list_endpoints",
    "list_provider_presets",
    "refresh_endpoint_models",
    "resolve_endpoint_for_model",
    "set_default_endpoint",
    "set_endpoint_enabled",
    "update_endpoint",
]
