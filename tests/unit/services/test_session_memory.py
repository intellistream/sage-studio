from __future__ import annotations

from pathlib import Path

import pytest

from sage.studio.runtime.session_memory import SessionMemoryManager


class _FakeBridge:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True

    async def store_working(self, content: str, metadata: dict | None = None) -> str:
        _ = (content, metadata)
        return "ok"

    async def store_episodic(self, content: str, metadata: dict | None = None) -> str:
        _ = (content, metadata)
        return "ok"

    async def recall_working(self, query: str = "", top_k: int = 5, **kwargs):
        _ = (query, top_k, kwargs)
        return [{"text": "working-1"}, {"content": "working-2"}]

    async def recall_episodic(self, query: str = "", top_k: int = 5, **kwargs):
        _ = (query, top_k, kwargs)
        return [{"text": "episodic-1"}]


@pytest.mark.asyncio
async def test_session_memory_ttl_cleanup_removes_expired_entries(tmp_path: Path) -> None:
    manager = SessionMemoryManager(ttl_days=1, memory_root=tmp_path)
    manager._ttl_seconds = 1

    bridge_a = _FakeBridge()
    bridge_b = _FakeBridge()

    created = {"s1": bridge_a, "s2": bridge_b}

    def _fake_create_bridge(session_id: str):
        return created[session_id]

    manager._create_bridge_for_session = _fake_create_bridge  # type: ignore[method-assign]

    await manager.ensure_session("s1")
    s1_dir = tmp_path / "s1"
    s1_dir.mkdir(parents=True, exist_ok=True)

    manager._entries["s1"].last_active_ts = 0.0

    await manager.ensure_session("s2")

    assert "s1" not in manager._entries
    assert bridge_a.closed is True
    assert not s1_dir.exists()


@pytest.mark.asyncio
async def test_session_memory_restore_and_prompt_context(tmp_path: Path) -> None:
    manager = SessionMemoryManager(ttl_days=7, memory_root=tmp_path)
    bridge = _FakeBridge()

    def _fake_create_bridge(_session_id: str):
        return bridge

    manager._create_bridge_for_session = _fake_create_bridge  # type: ignore[method-assign]

    restored = await manager.on_session_connected("abc")
    assert len(restored["working"]) == 2
    assert len(restored["episodic"]) == 1

    prompt_context = await manager.build_prompt_context(session_id="abc", query="hello")
    assert "[Session Working Memory]" in prompt_context
    assert "working-1" in prompt_context
    assert "[Session Episodic Memory]" in prompt_context
    assert "episodic-1" in prompt_context
