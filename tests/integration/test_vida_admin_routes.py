from __future__ import annotations

from fastapi.testclient import TestClient

from sage.studio.api.app import app


class _FakeRuntimeManager:
    def __init__(self) -> None:
        self._running = True
        self.reload_called = 0
        self.start_called = 0
        self.stop_called_with: list[bool] = []

    @property
    def is_running(self) -> bool:
        return self._running

    def reload_config(self):
        self.reload_called += 1
        return None

    async def start(self) -> dict:
        self.start_called += 1
        self._running = True
        return {"state": "running", "started": True}

    async def stop(self, drain: bool = True) -> dict:
        self.stop_called_with.append(drain)
        self._running = False
        return {"state": "stopped", "stopped": True}

    def status(self) -> dict:
        return {
            "state": "running" if self._running else "stopped",
            "accepting": self._running,
            "queue_depth": 0,
            "processed_count": 12,
            "failed_count": 1,
            "uptime_seconds": 3.0,
            "trigger_names": ["heartbeat"],
            "disabled_trigger_names": [],
            "last_reflect_timestamp": 1700000000.0,
        }

    async def memory_usage(self) -> dict:
        return {
            "working_count": 7,
            "episodic_count": 4,
            "semantic_count": 2,
        }

    def list_triggers(self) -> list[dict]:
        return [{"name": "heartbeat", "type": "interval", "enabled": True}]

    def set_trigger_enabled(self, trigger_name: str, enabled: bool) -> dict:
        if trigger_name != "heartbeat":
            raise RuntimeError("Unknown trigger")
        return {"name": trigger_name, "enabled": enabled}

    async def trigger(self, trigger_name: str, payload: dict | None = None) -> dict:
        return {
            "trigger_name": trigger_name,
            "result_ok": True,
            "message_id": "m-1",
            "answer": f"ok:{(payload or {}).get('content', '')}",
            "error": "",
        }

    def list_reflections(self, limit: int = 20) -> list[dict]:
        _ = limit
        return [{"timestamp": 1700000000.0, "summary": "s1", "insights": ["i1", "i2"]}]


def test_vida_admin_lifecycle_and_controls(monkeypatch) -> None:
    fake_runtime = _FakeRuntimeManager()
    monkeypatch.setattr(
        "sage.studio.api.vida_admin.get_vida_runtime_manager",
        lambda: fake_runtime,
    )

    client = TestClient(app)

    start_resp = client.post("/vida/admin/start", json={"reload_config": True})
    assert start_resp.status_code == 200
    assert start_resp.json()["started"] is True
    assert fake_runtime.reload_called == 1
    assert fake_runtime.start_called == 1

    status_resp = client.get("/vida/admin/status")
    assert status_resp.status_code == 200
    status_body = status_resp.json()
    assert status_body["state"] == "running"
    assert status_body["memory_usage"]["working_count"] == 7

    trigger_list_resp = client.get("/vida/admin/triggers")
    assert trigger_list_resp.status_code == 200
    assert trigger_list_resp.json()["triggers"][0]["name"] == "heartbeat"

    toggle_resp = client.post("/vida/admin/triggers/heartbeat/toggle", json={"enabled": False})
    assert toggle_resp.status_code == 200
    assert toggle_resp.json() == {"name": "heartbeat", "enabled": False}

    fire_resp = client.post("/vida/admin/trigger/heartbeat", json={"payload": {"content": "ping"}})
    assert fire_resp.status_code == 200
    assert fire_resp.json()["result_ok"] is True
    assert fire_resp.json()["answer"] == "ok:ping"

    reflections_resp = client.get("/vida/admin/reflections", params={"limit": 5})
    assert reflections_resp.status_code == 200
    assert len(reflections_resp.json()["items"]) == 1

    stop_resp = client.post("/vida/admin/stop", json={"drain": False})
    assert stop_resp.status_code == 200
    assert stop_resp.json()["stopped"] is True
    assert fake_runtime.stop_called_with == [False]


def test_vida_admin_toggle_unknown_trigger_returns_400(monkeypatch) -> None:
    fake_runtime = _FakeRuntimeManager()
    monkeypatch.setattr(
        "sage.studio.api.vida_admin.get_vida_runtime_manager",
        lambda: fake_runtime,
    )

    client = TestClient(app)
    resp = client.post("/vida/admin/triggers/unknown/toggle", json={"enabled": True})
    assert resp.status_code == 400
    assert "Unknown trigger" in resp.json()["detail"]
