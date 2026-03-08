"""Guardrails for the slimmed Studio backend surface.

Verifies:
1. Deprecated port aliases do not exist.
2. Public package surfaces no longer expose removed chat and vida helpers.
3. Service re-exports match the remaining Studio scope.
4. ``studio_manager.py`` uses named port constants.
"""

from __future__ import annotations

import os
import pathlib

_SRC = pathlib.Path(__file__).parent.parent / "src" / "sage" / "studio"


def _read(*parts: str) -> str:
    return (_SRC / pathlib.Path(*parts)).read_text()


def test_no_deprecated_port_aliases():
    """Removed port aliases must not be defined in ``ports.py``."""
    src = _read("config", "ports.py")
    for banned in ("BENCHMARK_LLM", "BENCHMARK_EMBEDDING", "LLM_WSL_FALLBACK"):
        assert banned not in src, f"Deprecated port alias '{banned}' still present in ports.py"


def test_no_deprecated_port_alias_references():
    """No Studio source file should reference removed port aliases."""
    for dirpath, _dirs, filenames in os.walk(_SRC):
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            path = pathlib.Path(dirpath) / fname
            content = path.read_text()
            for banned in ("BENCHMARK_LLM", "BENCHMARK_EMBEDDING", "LLM_WSL_FALLBACK"):
                assert banned not in content, f"Deprecated alias '{banned}' referenced in {path}"


def test_package_root_no_chat_manager_alias():
    """Public package root must not retain removed chat manager aliases."""
    src = _read("__init__.py")
    assert "ChatModeManager" not in src
    assert "chat_manager" not in src


def test_config_module_no_vida_reexport():
    """Studio config package must not re-export removed vida config helpers."""
    src = _read("config", "__init__.py")
    assert "VidaRuntimeConfig" not in src
    assert "load_vida_runtime_config" not in src
    assert ".vida" not in src


def test_services_module_no_removed_reexports():
    """Studio services package must not re-export removed chat and vida helpers."""
    src = _read("services", "__init__.py")
    for banned in (
        "document_loader",
        "memory_integration",
        "stream_handler",
        "vector_store",
        "get_memory_service",
        "get_stream_handler",
        "create_vector_store",
    ):
        assert banned not in src, f"Removed service symbol still re-exported: {banned}"


def test_studio_manager_uses_named_port_constants():
    """``studio_manager.py`` must use named port constants only."""
    src = _read("application", "studio_manager.py")
    assert "BENCHMARK_LLM" not in src
    assert "StudioPorts.LLM_DEFAULT" in src
    assert "StudioPorts.SAGELLM_SERVE_PORT" in src
