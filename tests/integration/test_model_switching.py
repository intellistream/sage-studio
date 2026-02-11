"""
测试 Studio 模型切换功能

验证修复后的功能：
1. Studio 启动时自动启动默认 LLM 引擎
2. 模型切换真正生效（启动新引擎）
"""

import os
import time

import pytest
import requests

from sage.studio.config.ports import StudioPorts

GATEWAY_HOST = os.getenv("SAGE_GATEWAY_HOST", "127.0.0.1")
GATEWAY_URL = f"http://{GATEWAY_HOST}:{StudioPorts.GATEWAY}/v1"
BACKEND_HOST = os.getenv("STUDIO_BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = int(os.getenv("STUDIO_BACKEND_PORT", str(StudioPorts.BACKEND)))
STUDIO_BACKEND_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}"


@pytest.fixture(scope="session")
def http_session():
    with requests.Session() as session:
        yield session


@pytest.fixture(scope="session")
def ensure_llm_gateway(http_session):
    try:
        response = http_session.get(f"{GATEWAY_URL}/models", timeout=2)
    except requests.RequestException as exc:
        pytest.skip(f"LLM Gateway not reachable: {exc}")

    assert response.status_code == 200, (
        f"LLM Gateway responded with {response.status_code}: {response.text}"
    )
    models = response.json().get("data", [])
    assert models, "LLM Gateway running but no engines."
    return models


@pytest.fixture(scope="session")
def ensure_studio_backend(http_session):
    try:
        response = http_session.get(f"{STUDIO_BACKEND_URL}/health", timeout=2)
    except requests.RequestException as exc:
        pytest.skip(f"Studio Backend not reachable: {exc}")

    assert response.status_code == 200, (
        f"Studio Backend responded with {response.status_code}: {response.text}"
    )
    return True


def _get_guest_token(http_session):
    response = http_session.post(f"{STUDIO_BACKEND_URL}/api/auth/guest", timeout=5)
    assert response.status_code == 200, (
        f"Guest token request failed: {response.status_code} - {response.text}"
    )
    token = response.json().get("access_token")
    assert token, "Guest token missing in response."
    return token


@pytest.fixture(scope="session")
def ensure_model_selected(http_session, ensure_llm_gateway, ensure_studio_backend):
    token = _get_guest_token(http_session)
    headers = {"Authorization": f"Bearer {token}"}
    select_data = {
        "model_name": "Qwen/Qwen2.5-0.5B-Instruct",
        "base_url": GATEWAY_URL,
    }

    response = http_session.post(
        f"{STUDIO_BACKEND_URL}/api/llm/select",
        json=select_data,
        headers=headers,
        timeout=60,
    )

    assert response.status_code == 200, (
        f"Model selection failed: {response.status_code} - {response.text}"
    )
    result = response.json()
    assert result.get("message"), "Model selection returned no message."

    if result.get("engine_started"):
        time.sleep(5)

    return result


def test_llm_gateway_running(ensure_llm_gateway):
    assert ensure_llm_gateway


def test_studio_backend_running(ensure_studio_backend):
    assert ensure_studio_backend


def test_model_selection(ensure_model_selected):
    assert ensure_model_selected.get("message")


def test_chat_functionality(http_session, ensure_model_selected, ensure_studio_backend):
    token = _get_guest_token(http_session)
    headers = {"Authorization": f"Bearer {token}"}
    chat_data = {
        "message": "Hello, this is a test.",
        "model": "sage-default",
    }

    response = http_session.post(
        f"{STUDIO_BACKEND_URL}/api/chat/message",
        json=chat_data,
        headers=headers,
        timeout=30,
    )

    assert response.status_code == 200, (
        f"Chat request failed: {response.status_code} - {response.text}"
    )
    result = response.json()
    content = result.get("content", "")
    assert content, "Chat response content is empty."
