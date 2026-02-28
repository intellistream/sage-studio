from __future__ import annotations

from sage.studio.api import llm


def test_pick_active_chat_model_prefers_selected_when_available() -> None:
    llm._selected.clear()
    llm._selected["model_name"] = "Qwen/Qwen2.5-0.5B-Instruct"

    picked = llm._pick_active_chat_model(
        [
            "Qwen/Qwen2.5-1.5B-Instruct",
            "Qwen/Qwen2.5-0.5B-Instruct",
        ]
    )

    assert picked == "Qwen/Qwen2.5-0.5B-Instruct"


def test_pick_active_chat_model_prefers_1_5b_default() -> None:
    llm._selected.clear()

    picked = llm._pick_active_chat_model(
        [
            "Qwen/Qwen2.5-0.5B-Instruct",
            "Qwen/Qwen2.5-1.5B-Instruct",
        ]
    )

    assert picked == "Qwen/Qwen2.5-1.5B-Instruct"


def test_pick_active_chat_model_honors_env_default(monkeypatch) -> None:
    llm._selected.clear()
    monkeypatch.setenv("SAGE_DEFAULT_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")

    picked = llm._pick_active_chat_model(
        [
            "Qwen/Qwen2.5-1.5B-Instruct",
            "Qwen/Qwen2.5-0.5B-Instruct",
        ]
    )

    assert picked == "Qwen/Qwen2.5-0.5B-Instruct"
