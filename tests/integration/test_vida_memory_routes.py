from __future__ import annotations

from fastapi.testclient import TestClient

from sage.studio.api.app import app


class _FakeRuntimeManager:
    async def recall_memory(
        self,
        *,
        query: str,
        top_k: int = 10,
        layer: str | None = None,
    ) -> dict:
        if query == "boom":
            raise RuntimeError("recall failed")
        return {
            "query": query,
            "top_k": top_k,
            "layer": layer,
            "results": [
                {
                    "layer": layer or "working",
                    "content": "hello",
                    "score": 0.9,
                }
            ],
            "total": 1,
        }

    async def list_memory(
        self,
        *,
        layer: str,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        if layer == "invalid":
            raise RuntimeError("invalid memory layer")
        return {
            "layer": layer,
            "items": [
                {
                    "content": f"item-{page}",
                    "timestamp": 1700000000.0,
                }
            ],
            "page": page,
            "page_size": page_size,
            "total": 1,
        }


def test_vida_memory_recall_and_list_routes(monkeypatch) -> None:
    fake_runtime = _FakeRuntimeManager()
    monkeypatch.setattr(
        "sage.studio.api.vida_memory.get_vida_runtime_manager",
        lambda: fake_runtime,
    )

    client = TestClient(app)

    recall_resp = client.get(
        "/vida/memory/recall",
        params={"query": "weather", "top_k": 5, "layer": "episodic"},
    )
    assert recall_resp.status_code == 200
    recall_body = recall_resp.json()
    assert recall_body["query"] == "weather"
    assert recall_body["top_k"] == 5
    assert recall_body["layer"] == "episodic"
    assert recall_body["total"] == 1

    list_resp = client.get(
        "/vida/memory/list",
        params={"layer": "working", "page": 2, "page_size": 10},
    )
    assert list_resp.status_code == 200
    list_body = list_resp.json()
    assert list_body["layer"] == "working"
    assert list_body["page"] == 2
    assert list_body["page_size"] == 10
    assert list_body["total"] == 1


def test_vida_memory_routes_return_400_on_runtime_error(monkeypatch) -> None:
    fake_runtime = _FakeRuntimeManager()
    monkeypatch.setattr(
        "sage.studio.api.vida_memory.get_vida_runtime_manager",
        lambda: fake_runtime,
    )

    client = TestClient(app)

    recall_resp = client.get("/vida/memory/recall", params={"query": "boom"})
    assert recall_resp.status_code == 400
    assert "recall failed" in recall_resp.json()["detail"]

    list_resp = client.get("/vida/memory/list", params={"layer": "invalid"})
    assert list_resp.status_code == 400
    assert "invalid memory layer" in list_resp.json()["detail"]
