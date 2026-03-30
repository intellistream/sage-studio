from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class StudioError(Exception):
    """Structured error for startup and orchestration path."""

    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


@dataclass(slots=True)
class PortConflictError(StudioError):
    """Raised when required port is already occupied."""
