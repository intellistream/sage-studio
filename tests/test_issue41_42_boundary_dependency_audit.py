"""Guardrails for sage-studio #41/#42 boundary and dependency refactor.

Verifies:
1. No ``ray`` imports are reintroduced in Python backend source.
2. API/supervisor Python layers do not import frontend source tree.
3. CLI keeps lazy manager import strategy (no eager heavy coupling at module import time).
4. Phase-1 boundary audit document exists and contains required sections.
"""

from __future__ import annotations

import os
import pathlib

_REPO = pathlib.Path(__file__).parent.parent
_SRC = _REPO / "src" / "sage" / "studio"
_DOC = _REPO / "docs" / "boundary_phase1.md"


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _iter_py_files(root: pathlib.Path):
    for dirpath, _dirs, filenames in os.walk(root):
        for filename in filenames:
            if filename.endswith(".py"):
                yield pathlib.Path(dirpath) / filename


def test_no_ray_imports_in_backend_source():
    """No ``ray`` import should exist in ``src/sage/studio`` Python code."""
    for path in _iter_py_files(_SRC):
        content = _read(path)
        assert "import ray" not in content, f"Forbidden 'import ray' found in {path}"
        assert "from ray" not in content, f"Forbidden 'from ray ...' found in {path}"


def test_api_layer_no_frontend_imports():
    """Python API layer must not import frontend source modules."""
    api_root = _SRC / "api"
    for path in _iter_py_files(api_root):
        content = _read(path)
        banned_patterns = (
            "from sage.studio.frontend",
            "import sage.studio.frontend",
            "from ..frontend",
            "from .frontend",
        )
        for banned in banned_patterns:
            assert banned not in content, f"Unexpected frontend coupling in {path}: {banned}"


def test_supervisor_layer_no_frontend_imports():
    """Supervisor layer must stay backend-only."""
    supervisor_root = _SRC / "supervisor"
    for path in _iter_py_files(supervisor_root):
        content = _read(path)
        banned_patterns = (
            "from sage.studio.frontend",
            "import sage.studio.frontend",
            "from ..frontend",
            "from .frontend",
        )
        for banned in banned_patterns:
            assert banned not in content, f"Unexpected frontend coupling in {path}: {banned}"


def test_cli_uses_lazy_manager_import():
    """CLI must keep lazy import in ``_get_studio_manager``."""
    cli_path = _SRC / "cli.py"
    content = _read(cli_path)

    assert "studio_manager = None" in content
    assert "def _get_studio_manager" in content
    assert "from sage.studio.chat_manager import ChatModeManager" in content

    module_header = content.split("def _get_studio_manager", maxsplit=1)[0]
    assert "from sage.studio.chat_manager import ChatModeManager" not in module_header, (
        "ChatModeManager should not be imported at module top-level"
    )


def test_boundary_phase1_doc_exists_and_sections_present():
    """Boundary audit document should exist with required review sections."""
    assert _DOC.exists(), "Expected docs/boundary_phase1.md to exist"
    doc = _read(_DOC)

    for required in (
        "In-scope",
        "Out-of-scope",
        "Forbidden imports",
        "跨层调用与动态导入盘点",
        "依赖审计",
        "Phase 1 拆分计划",
    ):
        assert required in doc, f"Missing section '{required}' in boundary_phase1.md"
