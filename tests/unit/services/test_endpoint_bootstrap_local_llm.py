from __future__ import annotations

from sage.studio.runtime.endpoints.bootstrap import (
    bootstrap_local_llm_endpoint_from_env,
    reset_endpoint_bootstrap_state,
)
from sage.studio.runtime.endpoints.registry import get_endpoint_registry, reset_endpoint_registry
from sage.studio.runtime.endpoints.router import resolve_endpoint_for_model


class _DummyResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_bootstrap_local_llm_endpoint_registers_on_healthy_engine(monkeypatch):
    reset_endpoint_registry()
    reset_endpoint_bootstrap_state()

    monkeypatch.setenv("SAGE_LLM_HOST", "127.0.0.1")
    monkeypatch.setenv("SAGE_LLM_PORT", "8901")
    monkeypatch.setenv("SAGE_STUDIO_LLM_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")

    monkeypatch.setattr(
        "sage.studio.runtime.endpoints.bootstrap.urllib.request.urlopen",
        lambda req, timeout=2: _DummyResponse(),
    )

    bootstrap_local_llm_endpoint_from_env()

    endpoint = get_endpoint_registry().get_endpoint("ep-local-llm-engine")
    assert endpoint is not None
    assert endpoint.base_url == "http://127.0.0.1:8901/v1"
    assert "Qwen/Qwen2.5-0.5B-Instruct" in endpoint.model_ids


def test_resolve_prefers_local_engine_endpoint_when_model_matches(monkeypatch):
    reset_endpoint_registry()
    reset_endpoint_bootstrap_state()

    monkeypatch.setenv("SAGE_LLM_HOST", "127.0.0.1")
    monkeypatch.setenv("SAGE_LLM_PORT", "8901")
    monkeypatch.setenv("SAGE_STUDIO_LLM_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
    monkeypatch.setenv("SAGE_GATEWAY_HOST", "127.0.0.1")
    monkeypatch.setenv("SAGE_GATEWAY_PORT", "8889")

    def _fake_urlopen(req, timeout=2):
        url = getattr(req, "full_url", "")
        if url.endswith("/health"):
            return _DummyResponse()
        if url.endswith("/v1/models"):
            raise OSError("gateway unavailable in test")
        raise OSError("unexpected url")

    monkeypatch.setattr(
        "sage.studio.runtime.endpoints.bootstrap.urllib.request.urlopen",
        _fake_urlopen,
    )

    resolved = resolve_endpoint_for_model("Qwen/Qwen2.5-0.5B-Instruct")
    assert resolved is not None
    assert resolved.endpoint_id == "ep-local-llm-engine"
    assert resolved.base_url == "http://127.0.0.1:8901/v1"
