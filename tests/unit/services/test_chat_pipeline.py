"""Tests for chat pipeline integration.

Covers:
1. ``pipeline_result_to_openai_sse`` — SSE chunking helper (no network)
2. ``ChatPipelineService`` — lifecycle with mocked PipelineBridge
3. ``/api/chat/v1/chat/completions`` endpoint — SSE format via mocked pipeline
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1. pipeline_result_to_openai_sse — unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sse_helper_empty_text():
    """Empty pipeline result should yield only finish+DONE."""
    from sage.studio.services.stream_handler import pipeline_result_to_openai_sse

    chunks: list[str] = []
    async for chunk in pipeline_result_to_openai_sse({"text": "", "meta": {}}):
        chunks.append(chunk)

    # Should have finish chunk + [DONE]
    assert len(chunks) == 2
    assert '"finish_reason": "stop"' in chunks[0]
    assert chunks[1] == "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_sse_helper_content_chunking():
    """Content text should be split into word-based SSE deltas."""
    from sage.studio.services.stream_handler import pipeline_result_to_openai_sse

    text = "Hello world from SAGE pipeline"
    result = {"text": text, "meta": {}}
    chunks: list[str] = []
    async for chunk in pipeline_result_to_openai_sse(result, chunk_size=2):
        chunks.append(chunk)

    # With 5 words and chunk_size=2 → 3 content chunks + finish + DONE = 5
    assert len(chunks) == 5

    # Verify all content chunks are valid OpenAI format
    content_pieces: list[str] = []
    for c in chunks[:-2]:  # skip finish + DONE
        assert c.startswith("data: ")
        payload = json.loads(c.removeprefix("data: ").strip())
        assert payload["object"] == "chat.completion.chunk"
        assert payload["choices"][0]["finish_reason"] is None
        content_pieces.append(payload["choices"][0]["delta"]["content"])

    # Reassembled content should match original text
    reassembled = "".join(content_pieces)
    assert reassembled.strip() == text


@pytest.mark.asyncio
async def test_sse_helper_meta_chunk():
    """When meta is present, the first chunk should carry pipeline_meta."""
    from sage.studio.services.stream_handler import pipeline_result_to_openai_sse

    meta = {"intent": "general", "route": "general", "confidence": 0.9}
    result = {"text": "Hi", "meta": meta}
    chunks: list[str] = []
    async for chunk in pipeline_result_to_openai_sse(result, chunk_size=10):
        chunks.append(chunk)

    # meta chunk + 1 content chunk + finish + DONE = 4
    assert len(chunks) == 4

    meta_payload = json.loads(chunks[0].removeprefix("data: ").strip())
    delta = meta_payload["choices"][0]["delta"]
    assert "pipeline_meta" in delta
    assert delta["pipeline_meta"]["intent"] == "general"


@pytest.mark.asyncio
async def test_sse_helper_model_and_id():
    """msg_id and model should propagate to every chunk."""
    from sage.studio.services.stream_handler import pipeline_result_to_openai_sse

    result = {"text": "ok", "meta": {}}
    chunks: list[str] = []
    async for chunk in pipeline_result_to_openai_sse(
        result, msg_id="test-id-42", model="my-model"
    ):
        chunks.append(chunk)

    for c in chunks:
        if c.startswith("data: {"):
            payload = json.loads(c.removeprefix("data: ").strip())
            assert payload["id"] == "test-id-42"
            assert payload["model"] == "my-model"


@pytest.mark.asyncio
async def test_sse_helper_done_sentinel():
    """Last frame must be ``data: [DONE]``."""
    from sage.studio.services.stream_handler import pipeline_result_to_openai_sse

    chunks: list[str] = []
    async for chunk in pipeline_result_to_openai_sse({"text": "x", "meta": {}}):
        chunks.append(chunk)

    assert chunks[-1] == "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_sse_helper_finish_reason_stop():
    """Penultimate frame must have finish_reason=stop and empty delta."""
    from sage.studio.services.stream_handler import pipeline_result_to_openai_sse

    chunks: list[str] = []
    async for chunk in pipeline_result_to_openai_sse({"text": "x", "meta": {}}):
        chunks.append(chunk)

    finish = json.loads(chunks[-2].removeprefix("data: ").strip())
    assert finish["choices"][0]["finish_reason"] == "stop"
    assert finish["choices"][0]["delta"] == {}


# ---------------------------------------------------------------------------
# 2. ChatPipelineService — unit tests with mocked bridge
# ---------------------------------------------------------------------------


class TestChatPipelineServiceLifecycle:
    """Test ChatPipelineService start/stop/run without real SAGE environment."""

    def _make_service(self):
        from sage.studio.services.chat_pipeline import ChatPipelineService

        svc = ChatPipelineService(request_timeout=5.0)
        return svc

    def test_run_before_start_raises(self):
        svc = self._make_service()
        with pytest.raises(RuntimeError, match="not running"):
            svc.run({"query": "hi"})

    @patch("sage.studio.services.chat_pipeline.LocalEnvironment")
    @patch("sage.studio.services.chat_pipeline.PipelineBridge")
    def test_start_stop_idempotent(self, mock_bridge_cls, mock_env_cls):
        """start() twice is safe; stop() twice is safe."""
        mock_bridge = MagicMock()
        mock_bridge_cls.return_value = mock_bridge

        mock_env = MagicMock()
        mock_env_cls.return_value = mock_env
        # Make from_source return a chainable mock
        chain = MagicMock()
        mock_env.from_source.return_value = chain
        chain.map.return_value = chain
        chain.sink.return_value = chain

        svc = self._make_service()
        svc.start()
        svc.start()  # idempotent — should not raise

        svc.stop()
        svc.stop()  # idempotent — should not raise

    @patch("sage.studio.services.chat_pipeline.LocalEnvironment")
    @patch("sage.studio.services.chat_pipeline.PipelineBridge")
    def test_run_returns_pipeline_result(self, mock_bridge_cls, mock_env_cls):
        """run() should submit to bridge and return the result."""
        import queue

        # Set up bridge mock
        mock_bridge = MagicMock()
        mock_bridge_cls.return_value = mock_bridge

        response_q = queue.Queue()
        expected_result = {"text": "hello", "meta": {"intent": "general"}}
        response_q.put(expected_result)
        mock_bridge.submit.return_value = response_q

        # Set up env mock
        mock_env = MagicMock()
        mock_env_cls.return_value = mock_env
        chain = MagicMock()
        mock_env.from_source.return_value = chain
        chain.map.return_value = chain
        chain.sink.return_value = chain

        svc = self._make_service()
        svc.start()


        result = svc.run({"query": "test question", "session_id": "s1"})

        assert result == expected_result
        mock_bridge.submit.assert_called_once()
        submitted = mock_bridge.submit.call_args[0][0]
        assert submitted["query"] == "test question"


# ---------------------------------------------------------------------------
# 3. /api/chat/v1/chat/completions endpoint — integration test
# ---------------------------------------------------------------------------


class TestChatCompletionsEndpoint:
    """Test the SSE endpoint with a mocked ChatPipelineService."""

    def _get_client_and_patch(self, monkeypatch):
        """Return a TestClient with the pipeline service mocked."""
        import sage.studio.config.backend.api as api
        from fastapi.testclient import TestClient

        # We need to mock get_chat_pipeline_service so it returns a stub
        # that produces a known result.
        pipeline_result = {
            "text": "Pipeline says hello.",
            "meta": {
                "intent": "general",
                "route": "general",
                "confidence": 0.85,
                "matched_keywords": [],
                "retrieval_count": 0,
                "query": "hi",
                "model": "test-model",
            },
        }

        mock_svc = MagicMock()
        mock_svc.run.return_value = pipeline_result

        # Patch at the module where it's imported in api.py (lazy import)
        monkeypatch.setattr(
            "sage.studio.services.chat_pipeline.get_chat_pipeline_service",
            lambda **kwargs: mock_svc,
        )

        # Also need to bypass auth — provide a fake current_user
        async def fake_current_user():
            return SimpleNamespace(id=1, username="test", role="admin")

        from sage.studio.services.auth_service import User

        api.app.dependency_overrides[api.get_current_user] = fake_current_user

        client = TestClient(api.app)
        return client, mock_svc, pipeline_result

    def test_sse_stream_format(self, monkeypatch, tmp_path):
        """Endpoint should return valid SSE with content chunks."""
        # Point session storage to tmp dir
        monkeypatch.setattr(
            "sage.studio.config.backend.api.get_user_sessions_dir",
            lambda uid: tmp_path,
        )

        client, mock_svc, pipeline_result = self._get_client_and_patch(monkeypatch)

        resp = client.post(
            "/api/chat/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": "hi"}],
                "session_id": "test-session-1",
                "stream": True,
            },
        )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

        # Parse SSE frames
        body = resp.text
        frames = [
            line.removeprefix("data: ").strip()
            for line in body.split("\n")
            if line.startswith("data:")
        ]

        assert len(frames) >= 3  # at least: meta + content + finish + [DONE]
        assert frames[-1] == "[DONE]"

        # Check that content can be reassembled
        content_pieces: list[str] = []
        for f in frames:
            if f == "[DONE]":
                continue
            parsed = json.loads(f)
            delta_content = parsed.get("choices", [{}])[0].get("delta", {}).get("content")
            if delta_content:
                content_pieces.append(delta_content)

        reassembled = "".join(content_pieces).strip()
        assert reassembled == pipeline_result["text"]

    def test_sse_no_user_message_returns_400(self, monkeypatch, tmp_path):
        """Missing user message should return 400."""
        monkeypatch.setattr(
            "sage.studio.config.backend.api.get_user_sessions_dir",
            lambda uid: tmp_path,
        )

        client, _, _ = self._get_client_and_patch(monkeypatch)

        resp = client.post(
            "/api/chat/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [],
                "session_id": "test-session-2",
            },
        )

        assert resp.status_code == 400

    def test_session_persisted_after_stream(self, monkeypatch, tmp_path):
        """After streaming, session file should contain both user and assistant messages."""
        monkeypatch.setattr(
            "sage.studio.config.backend.api.get_user_sessions_dir",
            lambda uid: tmp_path,
        )

        client, _, pipeline_result = self._get_client_and_patch(monkeypatch)

        session_id = "persist-test-session"
        resp = client.post(
            "/api/chat/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": "hello"}],
                "session_id": session_id,
                "stream": True,
            },
        )
        assert resp.status_code == 200
        # Consume the stream fully
        _ = resp.text

        # Check session file
        session_file = tmp_path / f"{session_id}.json"
        assert session_file.exists()

        session_data = json.loads(session_file.read_text())
        assert len(session_data["messages"]) == 2
        assert session_data["messages"][0]["role"] == "user"
        assert session_data["messages"][0]["content"] == "hello"
        assert session_data["messages"][1]["role"] == "assistant"
        assert session_data["messages"][1]["content"] == pipeline_result["text"]

    def teardown_method(self):
        """Clean up dependency overrides."""
        import sage.studio.config.backend.api as api

        api.app.dependency_overrides.clear()
