from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from sage.studio.runtime.vida_runtime import get_vida_runtime_manager


class VidaStartRequest(BaseModel):
    reload_config: bool = False


class VidaStopRequest(BaseModel):
    drain: bool = True


class VidaTriggerRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class VidaToggleTriggerRequest(BaseModel):
    enabled: bool


def build_vida_admin_router() -> APIRouter:
    router = APIRouter(prefix="/vida/admin", tags=["vida-admin"])

    @router.post("/start")
    async def start_vida_runtime(req: VidaStartRequest) -> dict[str, Any]:
        runtime = get_vida_runtime_manager()
        if req.reload_config:
            runtime.reload_config()

        try:
            return await runtime.start()
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/stop")
    async def stop_vida_runtime(req: VidaStopRequest) -> dict[str, Any]:
        runtime = get_vida_runtime_manager()
        try:
            return await runtime.stop(drain=req.drain)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/status")
    async def get_vida_runtime_status() -> dict[str, Any]:
        runtime = get_vida_runtime_manager()
        result = runtime.status()
        if runtime.is_running:
            try:
                result["memory_usage"] = await runtime.memory_usage()
            except RuntimeError:
                result["memory_usage"] = {
                    "working_count": 0,
                    "episodic_count": 0,
                    "semantic_count": 0,
                }
        return result

    @router.get("/triggers")
    async def list_vida_triggers() -> dict[str, Any]:
        runtime = get_vida_runtime_manager()
        return {
            "triggers": runtime.list_triggers(),
        }

    @router.post("/triggers/{trigger_name}/toggle")
    async def toggle_vida_trigger(
        trigger_name: str, req: VidaToggleTriggerRequest
    ) -> dict[str, Any]:
        runtime = get_vida_runtime_manager()
        try:
            return runtime.set_trigger_enabled(trigger_name=trigger_name, enabled=req.enabled)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/trigger/{trigger_name}")
    async def trigger_vida_runtime(trigger_name: str, req: VidaTriggerRequest) -> dict[str, Any]:
        runtime = get_vida_runtime_manager()
        try:
            return await runtime.trigger(trigger_name=trigger_name, payload=req.payload)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/reflections")
    async def list_vida_reflections(limit: int = 20) -> dict[str, Any]:
        runtime = get_vida_runtime_manager()
        return {
            "items": runtime.list_reflections(limit=limit),
        }

    return router


__all__ = ["build_vida_admin_router"]
