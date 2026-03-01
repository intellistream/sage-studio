from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

pytestmark = pytest.mark.integration


def _require_live_enabled() -> None:
    if os.getenv("STUDIO_LIVE_IT") != "1":
        pytest.skip("Set STUDIO_LIVE_IT=1 to run live Studio multi-turn integration test.")


def _require_real_model() -> bool:
    return os.getenv("STUDIO_LIVE_REQUIRE_REAL_MODEL") == "1"


def _resolve_live_chat_model(*, base_url: str) -> str:
    status = requests.get(f"{base_url}/api/llm/status", timeout=10)
    assert status.status_code == 200, f"llm status failed: {status.status_code}"
    payload = status.json()

    available_models = payload.get("available_models") or []
    for model in available_models:
        if model.get("engine_type") == "embedding":
            continue
        name = model.get("name")
        if isinstance(name, str) and name.strip():
            if _require_real_model() and (
                "mock" in name.lower() or name.lower().startswith("sage-default")
            ):
                continue
            return name.strip()

    model_name = payload.get("model_name")
    if isinstance(model_name, str) and model_name.strip():
        if _require_real_model() and (
            "mock" in model_name.lower() or model_name.lower().startswith("sage-default")
        ):
            raise AssertionError(
                f"real-model mode enabled but only mock-like model found: {model_name}"
            )
        return model_name.strip()

    raise AssertionError("no live chat model available from /api/llm/status")


def _stream_chat_once(*, base_url: str, session_id: str, model: str, message: str) -> str:
    _ensure_backend_healthy(base_url=base_url)
    response: requests.Response | None = None
    last_error: Exception | None = None

    for attempt in range(3):
        try:
            response = requests.post(
                f"{base_url}/api/chat/v1/chat/completions",
                json={
                    "model": model,
                    "session_id": session_id,
                    "stream": True,
                    "messages": [{"role": "user", "content": message}],
                },
                timeout=120,
            )
            break
        except requests.RequestException as exc:
            last_error = exc
            if attempt == 2:
                raise AssertionError(
                    f"chat completion request failed after retries: {exc}"
                ) from exc
            time.sleep(1.0)
            _ensure_backend_healthy(base_url=base_url)

    if response is None:
        raise AssertionError(f"chat completion request failed without response: {last_error}")
    assert response.status_code == 200, (
        f"chat completion failed: {response.status_code} - {response.text[:300]}"
    )
    text = response.text
    assert "data: [DONE]" in text, "SSE stream missing [DONE] marker"
    assert "data: {" in text, "SSE stream missing data chunk"

    if _require_real_model():
        lower_text = text.lower()
        assert '"type": "delta"' in text or '"type":"delta"' in text, (
            "real-model stream missing delta"
        )
        assert '"type": "error"' not in text and '"type":"error"' not in text, (
            "real-model stream contains error"
        )
        assert "stream_timeout_waiting_for_runtime" not in lower_text, "real-model stream timed out"
        assert "placeholder" not in lower_text, (
            "mock/placeholder response detected in real-model mode"
        )

    return text


def _ensure_backend_healthy(*, base_url: str) -> None:
    for _ in range(20):
        try:
            health = requests.get(f"{base_url}/health", timeout=3)
            if health.status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(0.5)
    raise AssertionError(f"backend not healthy: {base_url}/health")


def test_live_multiturn_chat_session() -> None:
    _require_live_enabled()

    base_url = os.getenv("STUDIO_BACKEND_URL", "http://127.0.0.1:8080")
    _ensure_backend_healthy(base_url=base_url)
    model = _resolve_live_chat_model(base_url=base_url)

    session_id = f"it-live-{uuid.uuid4().hex[:10]}"
    prompts = [
        "Hello, introduce yourself in one sentence.",
        "Now summarize your previous answer in two short bullet points.",
        "Merge those two points into one sentence.",
    ]

    for prompt in prompts:
        text = _stream_chat_once(
            base_url=base_url, session_id=session_id, model=model, message=prompt
        )
        assert "placeholder" not in text.lower(), "mock/placeholder response detected in live chat"
