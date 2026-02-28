"""Tests for chat pipeline integration.

Covers:
1. ``pipeline_result_to_openai_sse`` — SSE chunking helper (no network)
2. ``ChatPipelineService`` — lifecycle with mocked PipelineBridge
3. ``/api/chat/v1/chat/completions`` endpoint — SSE format via mocked pipeline
"""

from __future__ import annotations

import json

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
    async for chunk in pipeline_result_to_openai_sse(result, msg_id="test-id-42", model="my-model"):
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
