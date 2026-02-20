from __future__ import annotations

import os
import threading
from typing import Any

import sage.flownet.api as fn
from sage.flownet.config import FlownetConfig
from sage.flownet.runtime.runtime import try_get_runtime

from sage.studio.runtime.chat.contracts import ChatPipelineSettings
from sage.studio.runtime.chat.pipeline import build_chat_pipeline, create_chat_actor_refs


_ASSEMBLY_LOCK = threading.Lock()
_CHAT_PIPELINE = None
_CHAT_SETTINGS = ChatPipelineSettings()


def get_chat_pipeline():
    global _CHAT_PIPELINE

    if _CHAT_PIPELINE is not None:
        return _CHAT_PIPELINE

    with _ASSEMBLY_LOCK:
        if _CHAT_PIPELINE is not None:
            return _CHAT_PIPELINE

        _ensure_runtime_ready()
        actor_refs = create_chat_actor_refs()
        partition_plan, partition_addresses = _resolve_chat_partitioning(_CHAT_SETTINGS)
        _CHAT_PIPELINE = build_chat_pipeline(
            actor_refs=actor_refs,
            settings=_CHAT_SETTINGS,
            partition_plan=partition_plan,
            partition_addresses=partition_addresses,
        )
        return _CHAT_PIPELINE


def _ensure_runtime_ready() -> None:
    if try_get_runtime() is not None:
        return

    auto_config = os.environ.get("STUDIO_CHAT_AUTO_CONFIG", "1").strip().lower()
    if auto_config in {"0", "false", "off", "no"}:
        return

    # Local fallback for dev/tests. In production, runtime is expected to be bootstrapped by host/container.
    os.environ.setdefault("FLOWNET_NODE_MODE", "disabled")
    fn.configure_runtime(FlownetConfig(host="127.0.0.1", port=0, threads=2))


def _resolve_chat_partitioning(settings: ChatPipelineSettings) -> tuple[Any | None, list[str] | None]:
    request_id = os.environ.get(
        "STUDIO_CHAT_PLAN_REQUEST_ID",
        f"{settings.stage_id}:bootstrap",
    )

    try:
        plan = fn.runtime.resolve_plan(
            stage_id=settings.stage_id,
            request_id=request_id,
            num_partitions=settings.num_partitions,
            require_healthy=False,
        )
        plan_addresses = _extract_plan_addresses(plan, settings.num_partitions)
        if plan_addresses:
            return plan, None
    except Exception:
        pass

    local_addr = fn.runtime.local_address()
    return None, [local_addr] * settings.num_partitions


def _extract_plan_addresses(plan: Any, num_partitions: int) -> list[str] | None:
    partitions = getattr(plan, "partitions", None)
    if not isinstance(partitions, dict):
        return None

    addresses: list[str] = []
    for partition_id in range(num_partitions):
        address = partitions.get(str(partition_id))
        if address is None:
            address = partitions.get(partition_id)
        if not isinstance(address, str) or not address:
            return None
        addresses.append(address)
    return addresses


__all__ = ["get_chat_pipeline"]
