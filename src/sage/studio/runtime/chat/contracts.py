from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ChatPipelineSettings:
    stage_id: str = "sage-studio-chat-session"
    num_partitions: int = 8
    state_ttl_s: float = 3600.0
    # Reserved for feature graph assembly (MVP deferred).
    feature_profile_id: str | None = None
    # Reserved for canvas-authored flow reference (MVP deferred).
    canvas_flow_ref: str | None = None


__all__ = ["ChatPipelineSettings"]
