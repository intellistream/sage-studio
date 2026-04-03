"""Minimal auth stubs for SAGE Studio.

Studio is a single-user local tool; real authentication is not required.
These endpoints satisfy the frontend's auth-checking flow without restricting
access.  A persistent "guest" user is always returned.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel


class UserResponse(BaseModel):
    id: int = 1
    username: str = "studio-user"
    created_at: str = ""
    is_guest: bool = False


class TokenResponse(BaseModel):
    access_token: str = "studio-local-token"
    token_type: str = "bearer"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def build_auth_router() -> APIRouter:
    router = APIRouter(prefix="/api/auth", tags=["auth"])

    @router.get("/me", response_model=UserResponse)
    async def get_me() -> UserResponse:
        return UserResponse(created_at=_now_iso())

    @router.post("/login", response_model=TokenResponse)
    async def login() -> TokenResponse:
        return TokenResponse()

    @router.post("/guest", response_model=TokenResponse)
    async def guest_login() -> TokenResponse:
        return TokenResponse()

    @router.post("/logout")
    async def logout() -> dict[str, str]:
        return {"status": "ok"}

    @router.post("/register", response_model=UserResponse)
    async def register() -> UserResponse:
        return UserResponse(created_at=_now_iso())

    return router


__all__ = ["build_auth_router"]
