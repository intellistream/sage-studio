from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from sage.studio.runtime.vida_runtime import get_vida_runtime_manager


def build_vida_memory_router() -> APIRouter:
    router = APIRouter(prefix="/vida/memory", tags=["vida-memory"])

    @router.get("/recall")
    async def recall_vida_memory(
        query: str,
        top_k: int = 10,
        layer: str | None = None,
    ) -> dict[str, Any]:
        runtime = get_vida_runtime_manager()
        try:
            return await runtime.recall_memory(query=query, top_k=top_k, layer=layer)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/list")
    async def list_vida_memory(
        layer: str,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        runtime = get_vida_runtime_manager()
        try:
            return await runtime.list_memory(layer=layer, page=page, page_size=page_size)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router


__all__ = ["build_vida_memory_router"]
