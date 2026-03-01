"""Tests for sage-studio#43: runtime compat branch and ray remnant cleanup.

Verifies:
1. No deprecated port aliases (BENCHMARK_LLM, BENCHMARK_EMBEDDING, LLM_WSL_FALLBACK)
2. No NeuroMem in-memory fallback branches
3. No OriginalArxivTool import / HAS_ORIGINAL_IMPL fallback in arxiv_search.py
4. LegacyModelNode raises ValueError (no silent return None)
5. studio_manager.py uses named port constants (no bare 8901 comment reference)
"""

from __future__ import annotations

import os
import pathlib

# Source root for direct file reads (avoids importing transitive heavy deps)
_SRC = pathlib.Path(__file__).parent.parent / "src" / "sage" / "studio"


def _read(*parts: str) -> str:
    return (_SRC / pathlib.Path(*parts)).read_text()


# ---------------------------------------------------------------------------
# 1. Deprecated port aliases must not exist
# ---------------------------------------------------------------------------


def test_no_deprecated_port_aliases():
    """BENCHMARK_LLM, BENCHMARK_EMBEDDING, LLM_WSL_FALLBACK must not be defined."""
    src = _read("config", "ports.py")
    for banned in ("BENCHMARK_LLM", "BENCHMARK_EMBEDDING", "LLM_WSL_FALLBACK"):
        assert banned not in src, f"Deprecated port alias '{banned}' still present in ports.py"


def test_no_deprecated_port_alias_references():
    """No call sites should reference the removed deprecated aliases."""
    for dirpath, _dirs, filenames in os.walk(_SRC):
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            path = pathlib.Path(dirpath) / fname
            content = path.read_text()
            for banned in ("BENCHMARK_LLM", "BENCHMARK_EMBEDDING", "LLM_WSL_FALLBACK"):
                assert banned not in content, f"Deprecated alias '{banned}' referenced in {path}"


# ---------------------------------------------------------------------------
# 2. NeuroMem fallback must not exist
# ---------------------------------------------------------------------------


def test_memory_integration_no_available_flag():
    """_available attribute and fallback_memory list must not exist."""
    src = _read("services", "memory_integration.py")
    assert "_available" not in src, "_available flag still present in memory_integration.py"
    assert "_fallback_memory" not in src, "_fallback_memory still present in memory_integration.py"


def test_memory_integration_no_import_error_catch():
    """ImportError catch-and-fallback must be removed from memory init."""
    src = _read("services", "memory_integration.py")
    assert "using in-memory fallback" not in src
    assert "using fallback" not in src


def test_memory_integration_no_availability_conditional():
    """'if self._available' must not appear anywhere."""
    src = _read("services", "memory_integration.py")
    assert "if self._available" not in src


# ---------------------------------------------------------------------------
# 3. arxiv_search.py must not have OriginalArxivTool fallback
# ---------------------------------------------------------------------------


def test_arxiv_no_original_impl():
    """HAS_ORIGINAL_IMPL and OriginalArxivTool must be removed."""
    src = _read("tools", "arxiv_search.py")
    assert "HAS_ORIGINAL_IMPL" not in src
    assert "OriginalArxivTool" not in src
    assert "_run_original_impl" not in src


def test_arxiv_no_examples_import():
    """Conditional import of examples.tutorials must be removed."""
    src = _read("tools", "arxiv_search.py")
    assert "examples.tutorials" not in src


def test_arxiv_no_thread_pool_executor():
    """ThreadPoolExecutor import must be removed (was used only by _run_original_impl)."""
    src = _read("tools", "arxiv_search.py")
    assert "ThreadPoolExecutor" not in src


def test_arxiv_no_init_method():
    """ArxivSearchTool should no longer define __init__."""
    src = _read("tools", "arxiv_search.py")
    assert "def __init__" not in src, (
        "ArxivSearchTool should not define __init__ after fallback removal"
    )


# ---------------------------------------------------------------------------
# 4. SageLLMNode must raise ValueError (renamed from LegacyModelNode)
# ---------------------------------------------------------------------------


def test_legacy_model_node_raises_not_returns_none():
    """The SageLLMNode branch must raise ValueError, not silently return None."""
    src = _read("services", "playground_executor.py")
    assert "SageLLMNode" in src
    # Old silent warning pattern gone
    assert 'logger.warning("SageLLMNode' not in src
    # Fail-fast pattern present
    assert "raise ValueError" in src
    # Verify the raise is adjacent to SageLLMNode
    idx = src.index("SageLLMNode")
    nearby = src[idx : idx + 200]
    assert "raise ValueError" in nearby, "ValueError not raised in the SageLLMNode branch"


# ---------------------------------------------------------------------------
# 5. studio_manager.py uses named constants (no BENCHMARK_LLM comment ref)
# ---------------------------------------------------------------------------


def test_studio_manager_uses_named_port_constants():
    """studio_manager.py must use StudioPorts.LLM_DEFAULT and SAGELLM_SERVE_PORT."""
    src = _read("application", "studio_manager.py")
    assert "BENCHMARK_LLM" not in src, (
        "Comment reference to BENCHMARK_LLM still in studio_manager.py"
    )
    assert "StudioPorts.LLM_DEFAULT" in src
    assert "StudioPorts.SAGELLM_SERVE_PORT" in src
