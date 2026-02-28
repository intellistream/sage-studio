from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_SCHEMA_VERSION = "v1"


class RunKind(str, Enum):
    CHAT = "chat"
    EXPERIMENT = "experiment"
    SWARM = "swarm"


class StageEventState(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ArtifactKind(str, Enum):
    INPUT = "input"
    OUTPUT = "output"
    LOG = "log"
    CHECKPOINT = "checkpoint"


class RunRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = CONTRACT_SCHEMA_VERSION
    run_id: str
    request_id: str
    workspace_id: str
    kind: RunKind
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StageEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = CONTRACT_SCHEMA_VERSION
    run_id: str
    request_id: str
    stage: str
    state: StageEventState
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    message: str | None = None
    metrics: dict[str, Any] | None = None


class ArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = CONTRACT_SCHEMA_VERSION
    run_id: str
    artifact_id: str
    uri: str
    kind: ArtifactKind


class BudgetPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = CONTRACT_SCHEMA_VERSION
    max_duration_seconds: int | None = Field(default=None, ge=1)
    max_total_tokens: int | None = Field(default=None, ge=1)
    max_cost_usd: float | None = Field(default=None, ge=0.0)
    max_concurrency: int | None = Field(default=None, ge=1)
