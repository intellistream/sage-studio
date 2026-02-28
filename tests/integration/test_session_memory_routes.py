from __future__ import annotations

from fastapi.testclient import TestClient

from sage.studio.api.app import app


class _FakeSessionMemoryManager:
    def __init__(self) -> None:
        self.created: list[str] = []
        self.deleted: list[str] = []
        self.cleared: list[str] = []
        self.remembered: list[tuple[str, str, str]] = []

    async def on_session_created(self, session_id: str) -> None:
        self.created.append(session_id)

    async def on_session_deleted(self, session_id: str) -> None:
        self.deleted.append(session_id)

    async def on_session_cleared(self, session_id: str) -> None:
        self.cleared.append(session_id)

    async def remember_message(
        self,
        *,
        session_id: str,
        role: str,
        content: str,
        metadata: dict | None = None,
    ) -> None:
        _ = metadata
        self.remembered.append((session_id, role, content))


def test_session_lifecycle_triggers_memory_hooks(monkeypatch):
    fake_manager = _FakeSessionMemoryManager()
    monkeypatch.setattr(
        "sage.studio.api.sessions.get_session_memory_manager",
        lambda: fake_manager,
    )

    client = TestClient(app)

    create_resp = client.post("/api/chat/sessions", json={"title": "session-memory"})
    assert create_resp.status_code == 201
    session_id = create_resp.json()["id"]
    assert fake_manager.created == [session_id]

    add_resp = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"role": "user", "content": "hello memory"},
    )
    assert add_resp.status_code == 201
    assert fake_manager.remembered[-1] == (session_id, "user", "hello memory")

    clear_resp = client.post(f"/api/chat/sessions/{session_id}/clear")
    assert clear_resp.status_code == 200
    assert fake_manager.cleared == [session_id]

    delete_resp = client.delete(f"/api/chat/sessions/{session_id}")
    assert delete_resp.status_code == 204
    assert fake_manager.deleted == [session_id]
