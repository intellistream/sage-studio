from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import threading

from sage.studio.runtime.endpoints.contracts import (
    EndpointCreate,
    EndpointProviderPreset,
    EndpointUpdate,
    ManagedEndpoint,
    PROVIDER_PRESETS,
)
from sage.studio.runtime.endpoints.secrets import encrypt_endpoint_secret


class EndpointRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, ManagedEndpoint] = {}

    def list_provider_presets(self) -> tuple[EndpointProviderPreset, ...]:
        return PROVIDER_PRESETS

    def list_endpoints(self) -> list[ManagedEndpoint]:
        with self._lock:
            return sorted(self._records.values(), key=lambda item: item.endpoint_id)

    def get_endpoint(self, endpoint_id: str) -> ManagedEndpoint | None:
        with self._lock:
            return self._records.get(endpoint_id)

    def create_endpoint(self, command: EndpointCreate) -> ManagedEndpoint:
        with self._lock:
            if command.endpoint_id in self._records:
                raise ValueError(f"endpoint_id already exists: {command.endpoint_id}")

            created = ManagedEndpoint(
                endpoint_id=command.endpoint_id,
                provider=command.provider,
                display_name=command.display_name,
                base_url=command.base_url,
                model_ids=command.model_ids,
                enabled=command.enabled,
                is_default=command.is_default,
                extra_headers=command.extra_headers,
                api_key=encrypt_endpoint_secret(command.api_key),
            )
            self._records[created.endpoint_id] = created
            if created.is_default:
                self._set_default_locked(created.endpoint_id)
            elif len(self._records) == 1:
                self._set_default_locked(created.endpoint_id)
            return self._records[created.endpoint_id]

    def update_endpoint(self, endpoint_id: str, command: EndpointUpdate) -> ManagedEndpoint:
        with self._lock:
            current = self._records.get(endpoint_id)
            if current is None:
                raise KeyError(endpoint_id)

            now = datetime.now(timezone.utc)
            updated = replace(
                current,
                display_name=command.display_name if command.display_name is not None else current.display_name,
                base_url=command.base_url if command.base_url is not None else current.base_url,
                model_ids=command.model_ids if command.model_ids is not None else current.model_ids,
                enabled=command.enabled if command.enabled is not None else current.enabled,
                extra_headers=command.extra_headers if command.extra_headers is not None else current.extra_headers,
                api_key=(
                    encrypt_endpoint_secret(command.api_key)
                    if command.replace_api_key
                    else current.api_key
                ),
                updated_at=now,
            )
            self._records[endpoint_id] = updated

            if command.is_default is True:
                self._set_default_locked(endpoint_id)
            elif command.is_default is False and updated.is_default:
                self._records[endpoint_id] = replace(updated, is_default=False, updated_at=now)

            return self._records[endpoint_id]

    def set_enabled(self, endpoint_id: str, enabled: bool) -> ManagedEndpoint:
        with self._lock:
            current = self._records.get(endpoint_id)
            if current is None:
                raise KeyError(endpoint_id)
            updated = replace(current, enabled=enabled, updated_at=datetime.now(timezone.utc))
            self._records[endpoint_id] = updated
            return updated

    def set_default(self, endpoint_id: str) -> ManagedEndpoint:
        with self._lock:
            if endpoint_id not in self._records:
                raise KeyError(endpoint_id)
            self._set_default_locked(endpoint_id)
            return self._records[endpoint_id]

    def delete_endpoint(self, endpoint_id: str) -> None:
        with self._lock:
            existed = self._records.pop(endpoint_id, None)
            if existed is None:
                raise KeyError(endpoint_id)
            if existed.is_default:
                for candidate_id in sorted(self._records.keys()):
                    self._set_default_locked(candidate_id)
                    break

    def resolve_endpoint_for_model(self, model_id: str) -> ManagedEndpoint | None:
        normalized_model = model_id.strip()
        with self._lock:
            if not self._records:
                return None

            matched = [
                endpoint
                for endpoint in self._records.values()
                if endpoint.enabled and normalized_model in endpoint.model_ids
            ]
            if matched:
                return sorted(matched, key=lambda item: item.endpoint_id)[0]

            enabled = [endpoint for endpoint in self._records.values() if endpoint.enabled]
            defaults = [endpoint for endpoint in enabled if endpoint.is_default]
            if defaults:
                return sorted(defaults, key=lambda item: item.endpoint_id)[0]
            if enabled:
                return sorted(enabled, key=lambda item: item.endpoint_id)[0]
            return None

    def reset(self) -> None:
        with self._lock:
            self._records.clear()

    def _set_default_locked(self, endpoint_id: str) -> None:
        now = datetime.now(timezone.utc)
        for record_id, record in list(self._records.items()):
            self._records[record_id] = replace(
                record,
                is_default=(record_id == endpoint_id),
                updated_at=now,
            )


_ENDPOINT_REGISTRY = EndpointRegistry()


def get_endpoint_registry() -> EndpointRegistry:
    return _ENDPOINT_REGISTRY


def reset_endpoint_registry() -> None:
    _ENDPOINT_REGISTRY.reset()


__all__ = ["EndpointRegistry", "get_endpoint_registry", "reset_endpoint_registry"]
