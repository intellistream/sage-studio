"""
Unit test configuration for services.

Inserts MagicMock stubs for ``sage.middleware``, which is an optional higher-layer
dependency not installed in the lightweight unit-test environment. Without these
stubs, modules such as ``node_registry.py`` would fail to import during test
collection.

Only ``sage.middleware`` is stubbed here. Other missing higher-layer packages
(``sage_libs.sage_agentic.intent``, ``sage_libs.sage_finetune``) are intentionally
left untouched.
"""

import sys
from unittest.mock import MagicMock


def _stub(path: str) -> MagicMock:
    """Register a MagicMock module stub at path if not already in sys.modules."""
    if path not in sys.modules:
        mock = MagicMock(name=f"<stub:{path}>")
        mock.__name__ = path
        mock.__package__ = path
        mock.__path__ = []
        mock.__file__ = None
        sys.modules[path] = mock
    return sys.modules[path]


# ---------------------------------------------------------------------------
# sage.middleware subtree (not installed; needed by service modules that import
# runtime operators directly during test collection)
# ---------------------------------------------------------------------------
_stub("sage.middleware")
_stub("sage.middleware.components")
_stub("sage.middleware.components.sage_refiner")
_stub("sage.middleware.components.sage_refiner.python")
_stub("sage.middleware.components.sage_refiner.python.service")
_stub("sage.middleware.operators")
_stub("sage.middleware.operators.filters")
_stub("sage.middleware.operators.rag")
_stub("sage.middleware.operators.rag.chunk")

# Configure RefinerService so that refine() returns non-interfering results:
# empty documents list → researcher.py falls back to original search results.
_refiner_instance = MagicMock(name="RefinerServiceInstance")
_refiner_instance.refine.return_value = MagicMock(documents=[])
sys.modules["sage.middleware.components.sage_refiner.python.service"].RefinerService = MagicMock(
    name="RefinerService", return_value=_refiner_instance
)
