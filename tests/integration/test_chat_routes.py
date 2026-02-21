from fastapi.testclient import TestClient

from sage.studio.api.app import app


def test_chat_run_create_forwards_payload(monkeypatch):
    captured: dict = {}

    def _fake_submit_chat_service_request(
        *,
        request_id: str,
        run_id: str,
        session_id: str,
        model: str,
        message: str,
        ordered_event_backpressure: str = "drop_old",
    ) -> str:
        captured.update(
            {
                "request_id": request_id,
                "run_id": run_id,
                "session_id": session_id,
                "model": model,
                "message": message,
                "ordered_event_backpressure": ordered_event_backpressure,
            }
        )
        return "runtime-req-1"

    monkeypatch.setattr(
        "sage.studio.runtime.chat.submit_chat_service_request",
        _fake_submit_chat_service_request,
    )

    client = TestClient(app)
    payload = {
        "model": "Qwen/Qwen2.5-0.5B-Instruct",
        "session_id": "sess-1",
        "message": "q1",
    }

    resp = client.post("/api/chat/v1/runs", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["runtime_request_id"] == "runtime-req-1"
    assert body["run"]["kind"] == "chat"
    assert body["run"]["run_id"] == captured["run_id"]

    assert captured["session_id"] == "sess-1"
    assert captured["model"] == "Qwen/Qwen2.5-0.5B-Instruct"
    assert captured["message"] == "q1"
