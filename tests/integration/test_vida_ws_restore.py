from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from sage.studio.api.app import app


class _FakeSessionMemoryManager:
    async def on_session_connected(self, session_id: str):
        _ = session_id
        return {
            "working": [{"text": "w1"}],
            "episodic": [{"text": "e1"}],
        }


def test_vida_ws_connect_emits_restore_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        "sage.studio.api.vida_ws.get_session_memory_manager",
        lambda: _FakeSessionMemoryManager(),
    )

    client = TestClient(app)
    session_id = f"sess-{uuid.uuid4().hex}"

    with client.websocket_connect(f"/vida/ws/session/{session_id}") as websocket:
        first = websocket.receive_json()
        second = websocket.receive_json()

    assert first["type"] == "meta"
    assert first["status"] == "connected"
    assert first["session_id"] == session_id
    assert first["restored"]["working_count"] == 1
    assert first["restored"]["episodic_count"] == 1

    assert second["type"] == "session_restore"
    assert second["status"] == "ok"
    assert second["session_id"] == session_id
    assert len(second["working"]) == 1
    assert len(second["episodic"]) == 1
