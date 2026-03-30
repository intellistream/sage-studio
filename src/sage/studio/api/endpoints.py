from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from sage.studio.application import (
    EndpointPatchRequest,
    EndpointUpsertRequest,
    EndpointView,
    create_endpoint,
    delete_endpoint,
    get_endpoint,
    list_endpoints,
    list_provider_presets,
    refresh_endpoint_models,
    set_default_endpoint,
    set_endpoint_enabled,
    update_endpoint,
)
from sage.studio.runtime.endpoints import EndpointProvider


class EndpointProviderResponse(BaseModel):
    provider: str
    display_name: str
    default_base_url: str
    default_model_ids: list[str]
    default_extra_headers: dict[str, str]
    requires_api_key: bool
    notes: str


class ManagedEndpointResponse(BaseModel):
    endpoint_id: str
    provider: str
    display_name: str
    base_url: str
    model_ids: list[str]
    enabled: bool
    is_default: bool
    extra_headers: dict[str, str]
    has_api_key: bool
    api_key_masked: str | None
    created_at: str
    updated_at: str


class EndpointCreateRequest(BaseModel):
    endpoint_id: str | None = None
    provider: EndpointProvider
    display_name: str
    base_url: str
    model_ids: list[str] = Field(default_factory=list)
    enabled: bool = True
    is_default: bool = False
    auto_discover_models: bool = False
    extra_headers: dict[str, str] = Field(default_factory=dict)
    api_key: str | None = None


class EndpointUpdateRequest(BaseModel):
    display_name: str | None = None
    base_url: str | None = None
    model_ids: list[str] | None = None
    enabled: bool | None = None
    is_default: bool | None = None
    extra_headers: dict[str, str] | None = None
    api_key: str | None = None


class EndpointStatusRequest(BaseModel):
    enabled: bool


def build_endpoint_router() -> APIRouter:
    router = APIRouter(prefix="/api/config/v1", tags=["config-v1"])

    @router.get("/endpoint-providers", response_model=list[EndpointProviderResponse])
    async def get_endpoint_providers() -> list[EndpointProviderResponse]:
        return [
            EndpointProviderResponse(
                provider=item.provider,
                display_name=item.display_name,
                default_base_url=item.default_base_url,
                default_model_ids=list(item.default_model_ids),
                default_extra_headers=dict(item.default_extra_headers),
                requires_api_key=item.requires_api_key,
                notes=item.notes,
            )
            for item in list_provider_presets()
        ]

    @router.get("/endpoints", response_model=list[ManagedEndpointResponse])
    async def get_endpoints() -> list[ManagedEndpointResponse]:
        return [_to_response(item) for item in list_endpoints()]

    @router.get("/endpoints/{endpoint_id}", response_model=ManagedEndpointResponse)
    async def get_endpoint_by_id(endpoint_id: str) -> ManagedEndpointResponse:
        endpoint = get_endpoint(endpoint_id)
        if endpoint is None:
            raise HTTPException(status_code=404, detail="endpoint not found")
        return _to_response(endpoint)

    @router.post("/endpoints", response_model=ManagedEndpointResponse)
    async def create_endpoint_entry(req: EndpointCreateRequest) -> ManagedEndpointResponse:
        endpoint_id = (req.endpoint_id or "").strip() or f"ep-{uuid.uuid4().hex[:12]}"
        try:
            created = create_endpoint(
                EndpointUpsertRequest(
                    endpoint_id=endpoint_id,
                    provider=req.provider,
                    display_name=req.display_name,
                    base_url=req.base_url,
                    model_ids=tuple(req.model_ids),
                    enabled=req.enabled,
                    is_default=req.is_default,
                    auto_discover_models=req.auto_discover_models,
                    extra_headers=tuple(req.extra_headers.items()),
                    api_key=req.api_key,
                )
            )
        except ValueError as exc:
            message = str(exc)
            status_code = 409 if "already exists" in message else 400
            raise HTTPException(status_code=status_code, detail=message) from exc
        return _to_response(created)

    @router.patch("/endpoints/{endpoint_id}", response_model=ManagedEndpointResponse)
    async def patch_endpoint(
        endpoint_id: str, req: EndpointUpdateRequest
    ) -> ManagedEndpointResponse:
        try:
            updated = update_endpoint(
                endpoint_id,
                EndpointPatchRequest(
                    display_name=req.display_name,
                    base_url=req.base_url,
                    model_ids=tuple(req.model_ids) if req.model_ids is not None else None,
                    enabled=req.enabled,
                    is_default=req.is_default,
                    extra_headers=tuple(req.extra_headers.items())
                    if req.extra_headers is not None
                    else None,
                    replace_api_key=("api_key" in req.model_fields_set),
                    api_key=req.api_key,
                ),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="endpoint not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _to_response(updated)

    @router.post("/endpoints/{endpoint_id}/enabled", response_model=ManagedEndpointResponse)
    async def set_endpoint_status(
        endpoint_id: str, req: EndpointStatusRequest
    ) -> ManagedEndpointResponse:
        try:
            updated = set_endpoint_enabled(endpoint_id, req.enabled)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="endpoint not found") from exc
        return _to_response(updated)

    @router.post("/endpoints/{endpoint_id}/default", response_model=ManagedEndpointResponse)
    async def set_default(endpoint_id: str) -> ManagedEndpointResponse:
        try:
            updated = set_default_endpoint(endpoint_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="endpoint not found") from exc
        return _to_response(updated)

    @router.post("/endpoints/{endpoint_id}/models/refresh", response_model=ManagedEndpointResponse)
    async def refresh_models(endpoint_id: str) -> ManagedEndpointResponse:
        try:
            updated = refresh_endpoint_models(endpoint_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="endpoint not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _to_response(updated)

    @router.delete("/endpoints/{endpoint_id}", status_code=204)
    async def remove_endpoint(endpoint_id: str) -> None:
        try:
            delete_endpoint(endpoint_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="endpoint not found") from exc

    return router


def _to_response(item: EndpointView) -> ManagedEndpointResponse:
    return ManagedEndpointResponse(
        endpoint_id=item.endpoint_id,
        provider=item.provider,
        display_name=item.display_name,
        base_url=item.base_url,
        model_ids=list(item.model_ids),
        enabled=item.enabled,
        is_default=item.is_default,
        extra_headers=dict(item.extra_headers),
        has_api_key=item.has_api_key,
        api_key_masked=item.api_key_masked,
        created_at=item.created_at.isoformat(),
        updated_at=item.updated_at.isoformat(),
    )


__all__ = ["build_endpoint_router"]
