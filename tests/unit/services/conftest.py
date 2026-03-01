"""
Unit test configuration for services.

Inserts MagicMock stubs for sage.middleware, which is an optional L4 dependency
not installed in the CI/dev unit-test environment. Without these stubs, modules
modified by issue #43 (researcher.py, node_registry.py) would fail to import at
test time, breaking tests that were passing before Wave D.

Only sage.middleware is stubbed here. Other missing L3/L4 packages
(sage_libs.sage_agentic.intent, sage_libs.sage_finetune) have pre-existing
collection errors in HEAD and are intentionally left as is.
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
# sage.middleware subtree  (not installed; needed by researcher.py and
# node_registry.py after Wave-D #43 removed graceful try/except fallbacks)
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
