from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from sage.studio.api.auth import build_auth_router
from sage.studio.api.canvas import build_canvas_router
from sage.studio.api.endpoints import build_endpoint_router
from sage.studio.config.ports import StudioPorts
from sage.studio.runtime.endpoints import bootstrap_dashscope_endpoint_from_env


def _build_cors_origins() -> list[str]:
    origins: set[str] = set()
    for port in StudioPorts.get_frontend_dev_ports():
        origins.add(f"http://localhost:{port}")
        origins.add(f"http://127.0.0.1:{port}")
        origins.add(f"http://0.0.0.0:{port}")
    return sorted(origins)


@asynccontextmanager
async def _app_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    bootstrap_dashscope_endpoint_from_env()
    try:
        yield
    finally:
        pass


def create_app() -> FastAPI:
    app = FastAPI(title="SAGE Studio Core", lifespan=_app_lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_build_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(build_auth_router())
    app.include_router(build_endpoint_router())
    app.include_router(build_canvas_router())

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "sage-studio"}

    _mount_frontend_dist(app)

    return app


def _mount_frontend_dist(app: FastAPI) -> None:
    dist_dir = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    index_file = dist_dir / "index.html"
    if not dist_dir.exists() or not index_file.exists():
        return

    app.mount("/assets", StaticFiles(directory=str(dist_dir / "assets")), name="assets")

    @app.get("/", include_in_schema=False)
    async def root_index() -> FileResponse:
        return FileResponse(index_file)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        # Return 404 for API routes that weren't matched by any registered handler
        # so the frontend receives a proper error instead of an HTML SPA response.
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail=f"Not found: /{full_path}")
        candidate = dist_dir / full_path
        if candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_file)


app = create_app()


__all__ = ["app", "create_app"]
