from __future__ import annotations

from sage.studio.runtime.adapters.inference import request_chat_completion
from sage.studio.runtime.endpoints.router import ResolvedEndpoint


class _DummyResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": "hello"
                    }
                }
            ]
        }


class _DummyClient:
    def __init__(self, *, timeout: float):
        self.timeout = timeout
        self.captured_json = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url: str, headers: dict, json: dict):
        self.captured_json = json
        return _DummyResponse()


def test_request_chat_completion_uses_bounded_max_tokens_and_timeout(monkeypatch):
    monkeypatch.setenv("STUDIO_CHAT_MAX_TOKENS", "64")
    monkeypatch.setenv("STUDIO_CHAT_PROVIDER_TIMEOUT_S", "45")

    holder = {}

    def _client_factory(timeout: float):
        client = _DummyClient(timeout=timeout)
        holder["client"] = client
        return client

    monkeypatch.setattr("sage.studio.runtime.adapters.inference.httpx.Client", _client_factory)

    endpoint = ResolvedEndpoint(
        endpoint_id="ep-local",
        provider="openai_compatible",
        base_url="http://127.0.0.1:8901/v1",
        model_id="Qwen/Qwen2.5-0.5B-Instruct",
        matched_model=True,
        api_key="sk-local",
        extra_headers=(),
    )

    text = request_chat_completion(endpoint=endpoint, message="hi", timeout_s=30.0)

    assert text == "hello"
    client = holder["client"]
    assert client.timeout == 45.0
    assert client.captured_json["max_tokens"] == 64
    assert client.captured_json["stream"] is False
