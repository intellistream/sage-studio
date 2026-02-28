from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_TTL_DAYS = int(os.environ.get("STUDIO_VIDA_SESSION_TTL_DAYS", "7"))
_DEFAULT_WORKING_TOP_K = int(os.environ.get("STUDIO_VIDA_SESSION_RESTORE_WORKING_TOPK", "8"))
_DEFAULT_EPISODIC_TOP_K = int(os.environ.get("STUDIO_VIDA_SESSION_RESTORE_EPISODIC_TOPK", "4"))
_SESSION_MEMORY_ROOT = Path(
    os.environ.get(
        "STUDIO_VIDA_SESSION_MEMORY_DIR",
        str(Path.home() / ".local" / "share" / "sage" / "studio" / "vida_session_memory"),
    )
).expanduser()


@dataclass(slots=True)
class _SessionBridgeEntry:
    bridge: Any
    data_dir: Path
    last_active_ts: float


class SessionMemoryManager:
    def __init__(
        self,
        *,
        ttl_days: int = _DEFAULT_TTL_DAYS,
        working_top_k: int = _DEFAULT_WORKING_TOP_K,
        episodic_top_k: int = _DEFAULT_EPISODIC_TOP_K,
        memory_root: Path = _SESSION_MEMORY_ROOT,
    ) -> None:
        self._ttl_seconds = max(1, ttl_days) * 24 * 3600
        self._working_top_k = max(1, working_top_k)
        self._episodic_top_k = max(1, episodic_top_k)
        self._memory_root = memory_root
        self._memory_root.mkdir(parents=True, exist_ok=True)

        self._lock = asyncio.Lock()
        self._entries: dict[str, _SessionBridgeEntry] = {}

    async def on_session_created(self, session_id: str) -> None:
        await self.ensure_session(session_id)

    async def on_session_connected(self, session_id: str) -> dict[str, Any]:
        await self.ensure_session(session_id)
        return await self.restore_context(session_id=session_id, query="")

    async def on_session_deleted(self, session_id: str) -> None:
        entry = await self._pop_entry(session_id)
        if entry is not None:
            await entry.bridge.close()

        session_dir = self._session_data_dir(session_id)
        if session_dir.exists():
            shutil.rmtree(session_dir, ignore_errors=True)

    async def on_session_cleared(self, session_id: str) -> None:
        await self.on_session_deleted(session_id)
        await self.ensure_session(session_id)

    async def remember_message(
        self,
        *,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not content.strip():
            return

        bridge = await self._get_or_create_bridge(session_id)
        await bridge.store_working(
            content,
            metadata={"role": role, "session_id": session_id, **(metadata or {})},
        )
        if role == "assistant":
            await bridge.store_episodic(
                content,
                metadata={"role": role, "session_id": session_id, **(metadata or {})},
            )

    async def remember_turn(
        self,
        *,
        session_id: str,
        user_message: str,
        assistant_message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self.remember_message(
            session_id=session_id,
            role="user",
            content=user_message,
            metadata=metadata,
        )
        await self.remember_message(
            session_id=session_id,
            role="assistant",
            content=assistant_message,
            metadata=metadata,
        )
        bridge = await self._get_or_create_bridge(session_id)
        await bridge.store_episodic(
            f"Q: {user_message}\nA: {assistant_message}",
            metadata={"session_id": session_id, "source": "session_turn", **(metadata or {})},
        )

    async def restore_context(self, *, session_id: str, query: str) -> dict[str, Any]:
        bridge = await self._get_or_create_bridge(session_id)
        working = await bridge.recall_working(query="", top_k=self._working_top_k)
        episodic = await bridge.recall_episodic(query=query or "", top_k=self._episodic_top_k)
        return {
            "working": working,
            "episodic": episodic,
        }

    async def build_prompt_context(self, *, session_id: str, query: str) -> str:
        restored = await self.restore_context(session_id=session_id, query=query)
        lines: list[str] = []

        working = restored.get("working", [])
        episodic = restored.get("episodic", [])

        if working:
            lines.append("[Session Working Memory]")
            for item in working[: self._working_top_k]:
                text = _extract_text(item)
                if text:
                    lines.append(f"- {text}")

        if episodic:
            lines.append("[Session Episodic Memory]")
            for item in episodic[: self._episodic_top_k]:
                text = _extract_text(item)
                if text:
                    lines.append(f"- {text}")

        if not lines:
            return ""
        return "\n".join(lines)

    async def ensure_session(self, session_id: str) -> None:
        _ = await self._get_or_create_bridge(session_id)

    async def _get_or_create_bridge(self, session_id: str) -> Any:
        await self._cleanup_expired()

        async with self._lock:
            entry = self._entries.get(session_id)
            if entry is not None:
                entry.last_active_ts = time.time()
                return entry.bridge

        bridge = self._create_bridge_for_session(session_id)
        now = time.time()
        async with self._lock:
            self._entries[session_id] = _SessionBridgeEntry(
                bridge=bridge,
                data_dir=self._session_data_dir(session_id),
                last_active_ts=now,
            )
        return bridge

    async def _pop_entry(self, session_id: str) -> _SessionBridgeEntry | None:
        async with self._lock:
            return self._entries.pop(session_id, None)

    async def _cleanup_expired(self) -> None:
        now = time.time()
        expired_entries: list[tuple[str, _SessionBridgeEntry]] = []

        async with self._lock:
            for session_id, entry in list(self._entries.items()):
                if now - entry.last_active_ts > self._ttl_seconds:
                    expired_entries.append((session_id, entry))
                    self._entries.pop(session_id, None)

        for session_id, entry in expired_entries:
            try:
                await entry.bridge.close()
            except Exception:  # noqa: BLE001
                logger.exception("Failed to close expired session bridge: %s", session_id)
            if entry.data_dir.exists():
                shutil.rmtree(entry.data_dir, ignore_errors=True)

    def _create_bridge_for_session(self, session_id: str) -> Any:
        from sage.middleware.operators.vida import VidaMemoryBridge

        base = f"vida.session.{session_id}"

        class _SessionScopedVidaMemoryBridge(VidaMemoryBridge):
            _WORKING_COLLECTION = f"{base}.working"
            _EPISODIC_COLLECTION = f"{base}.episodic"
            _SEMANTIC_COLLECTION = f"{base}.semantic"

        session_data_dir = self._session_data_dir(session_id)
        session_data_dir.mkdir(parents=True, exist_ok=True)

        return _SessionScopedVidaMemoryBridge(
            config={
                "data_dir": str(session_data_dir),
                "working_memory": {"max_size": 50},
                "episodic_memory": {},
                "semantic_memory": {},
            }
        )

    def _session_data_dir(self, session_id: str) -> Path:
        return self._memory_root / session_id


def _extract_text(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for key in ("text", "content", "summary", "value"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


_SESSION_MEMORY_MANAGER: SessionMemoryManager | None = None


def get_session_memory_manager() -> SessionMemoryManager:
    global _SESSION_MEMORY_MANAGER
    if _SESSION_MEMORY_MANAGER is None:
        _SESSION_MEMORY_MANAGER = SessionMemoryManager()
    return _SESSION_MEMORY_MANAGER


__all__ = ["SessionMemoryManager", "get_session_memory_manager"]
