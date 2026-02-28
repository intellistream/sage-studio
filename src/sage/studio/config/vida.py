from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class VidaAgentConfig(BaseModel):
    state_file: str = ".vida_agent_state.json"
    working_top_k: int = 10
    episodic_top_k: int = 5
    semantic_top_k: int = 5
    working_memory_capacity: int = 20
    drain_timeout_seconds: float = 5.0
    persist_on_each_step: bool = True
    close_memory_on_shutdown: bool = True


class VidaMemoryConfig(BaseModel):
    data_dir: str | None = None
    working_memory: dict[str, Any] = Field(default_factory=dict)
    episodic_memory: dict[str, Any] = Field(default_factory=dict)
    semantic_memory: dict[str, Any] = Field(default_factory=dict)


class VidaReflectionConfig(BaseModel):
    enabled: bool = True
    interval_seconds: int = 1800
    top_k_episodes: int = 10
    reflection_query: str = ""


class VidaTriggerConfig(BaseModel):
    enabled: bool = False
    interval_triggers: dict[str, float] = Field(default_factory=dict)


class VidaRuntimeConfig(BaseModel):
    enabled: bool = False
    auto_start: bool = False
    model: str = ""
    gateway_url: str = ""
    react_loop: dict[str, Any] = Field(default_factory=lambda: {"max_steps": 5, "step_delay": 0.0})
    agent: VidaAgentConfig = Field(default_factory=VidaAgentConfig)
    memory: VidaMemoryConfig = Field(default_factory=VidaMemoryConfig)
    reflection: VidaReflectionConfig = Field(default_factory=VidaReflectionConfig)
    trigger: VidaTriggerConfig = Field(default_factory=VidaTriggerConfig)


def load_vida_runtime_config() -> VidaRuntimeConfig:
    merged: dict[str, Any] = {}
    yaml_path = _resolve_config_path()
    if yaml_path is not None and yaml_path.exists():
        merged = _load_yaml_config(yaml_path)

    _apply_env_overrides(merged)
    return VidaRuntimeConfig.model_validate(merged)


def _resolve_config_path() -> Path | None:
    env_path = os.environ.get("STUDIO_VIDA_CONFIG_FILE", "").strip()
    if env_path:
        return Path(env_path).expanduser().resolve()

    default_path = Path(__file__).resolve().with_name("vida.yaml")
    if default_path.exists():
        return default_path
    return None


def _load_yaml_config(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("vida.yaml found but PyYAML is not installed") from exc

    with path.open("r", encoding="utf-8") as file:
        loaded = yaml.safe_load(file) or {}

    if not isinstance(loaded, dict):
        raise RuntimeError("vida.yaml root must be a mapping")
    return loaded


def _apply_env_overrides(config: dict[str, Any]) -> None:
    _set_env(config, ["enabled"], "STUDIO_VIDA_ENABLED", _as_bool)
    _set_env(config, ["auto_start"], "STUDIO_VIDA_AUTO_START", _as_bool)
    _set_env(config, ["model"], "STUDIO_VIDA_MODEL", str)
    _set_env(config, ["gateway_url"], "STUDIO_VIDA_GATEWAY_URL", str)

    _set_env(config, ["agent", "state_file"], "STUDIO_VIDA_STATE_FILE", str)
    _set_env(
        config, ["agent", "working_memory_capacity"], "STUDIO_VIDA_WORKING_MEMORY_CAPACITY", int
    )
    _set_env(config, ["agent", "drain_timeout_seconds"], "STUDIO_VIDA_DRAIN_TIMEOUT_SECONDS", float)

    _set_env(config, ["memory", "data_dir"], "STUDIO_VIDA_MEMORY_DATA_DIR", str)

    _set_env(config, ["reflection", "enabled"], "STUDIO_VIDA_REFLECTION_ENABLED", _as_bool)
    _set_env(
        config, ["reflection", "interval_seconds"], "STUDIO_VIDA_REFLECTION_INTERVAL_SECONDS", int
    )
    _set_env(config, ["reflection", "top_k_episodes"], "STUDIO_VIDA_REFLECTION_TOPK", int)

    _set_env(config, ["trigger", "enabled"], "STUDIO_VIDA_TRIGGER_ENABLED", _as_bool)


def _set_env(
    config: dict[str, Any],
    path: list[str],
    env_name: str,
    caster: Any,
) -> None:
    raw = os.environ.get(env_name)
    if raw is None:
        return
    value = caster(raw)

    current = config
    for key in path[:-1]:
        next_value = current.get(key)
        if not isinstance(next_value, dict):
            next_value = {}
            current[key] = next_value
        current = next_value
    current[path[-1]] = value


def _as_bool(raw: str) -> bool:
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {raw}")


__all__ = ["VidaRuntimeConfig", "load_vida_runtime_config"]
