"""#44 – start/stop/status/logs 链路端到端回归测试

Tests the key lifecycle command contracts for ``sage studio`` *without*
depending on sage-cli being installed.  All tests import the studio Typer
app directly and patch the module-level ``studio_manager`` global.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from sage.studio.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fake manager – covers every method called by cli.py commands
# ---------------------------------------------------------------------------


class FakeStudioManager:
    """Minimal stub for StudioManager / ChatModeManager used in CLI tests."""

    def __init__(self) -> None:
        self._running: bool = False
        self._config: dict = {"host": "127.0.0.1", "port": 7788}
        # Capture last call kwargs for assertion
        self.last_start_kwargs: dict = {}
        self.last_stop_kwargs: dict = {}
        self.last_logs_kwargs: dict = {}

    # -- state helpers -------------------------------------------------------

    def is_running(self):
        return self._config["port"] if self._running else None

    def load_config(self) -> dict:
        return dict(self._config)

    # -- lifecycle -----------------------------------------------------------

    def start(self, **kwargs) -> bool:
        self.last_start_kwargs = kwargs
        if kwargs.get("frontend_port"):
            self._config["port"] = kwargs["frontend_port"]
        if kwargs.get("host"):
            self._config["host"] = kwargs["host"]
        self._running = True
        return True

    def stop(self, stop_gateway: bool = False, stop_llm: bool = False) -> bool:
        self.last_stop_kwargs = {"stop_gateway": stop_gateway, "stop_llm": stop_llm}
        was_running = self._running
        self._running = False
        return was_running

    def status(self):
        return {"running": self._running, "config": self._config}

    def logs(self, **kwargs) -> list:
        self.last_logs_kwargs = kwargs
        return []

    # -- other commands called by cli.py -------------------------------------

    def install(self) -> bool:
        return True

    def build(self) -> bool:
        return True

    def clean(self) -> bool:
        return True

    def open(self) -> bool:
        return True

    def run_npm_command(self, args: list[str]) -> bool:
        self._last_npm = args
        return True


@pytest.fixture()
def fake_manager() -> FakeStudioManager:
    return FakeStudioManager()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def invoke(fake: FakeStudioManager, *args: str):
    """Invoke CLI with studio_manager patched to *fake*."""
    with patch("sage.studio.cli.studio_manager", fake):
        return runner.invoke(app, list(args))


# ---------------------------------------------------------------------------
# Help / discovery
# ---------------------------------------------------------------------------


def test_help_lists_commands():
    """``sage studio --help`` exits 0 and lists core subcommands."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("start", "stop", "status", "logs", "restart"):
        assert cmd in result.stdout, f"Expected '{cmd}' in help output"


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------


def test_start_happy_path(fake_manager):
    """``start`` exits 0 and marks manager as running."""
    result = invoke(fake_manager, "start")
    assert result.exit_code == 0, result.stdout
    assert fake_manager._running is True


def test_start_forwards_port(fake_manager):
    """``start --port 9001`` passes frontend_port=9001 to manager."""
    result = invoke(fake_manager, "start", "--port", "9001")
    assert result.exit_code == 0, result.stdout
    assert fake_manager._config["port"] == 9001


def test_start_forwards_host(fake_manager):
    """``start --host 127.0.0.1`` passes host to manager."""
    result = invoke(fake_manager, "start", "--host", "127.0.0.1")
    assert result.exit_code == 0, result.stdout
    assert fake_manager.last_start_kwargs.get("host") == "127.0.0.1"


def test_start_skip_confirm_flag(fake_manager):
    """``start --yes`` passes skip_confirm=True to manager."""
    result = invoke(fake_manager, "start", "--yes")
    assert result.exit_code == 0, result.stdout
    assert fake_manager.last_start_kwargs.get("skip_confirm") is True


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------


def test_stop_running_service(fake_manager):
    """``stop`` exits 0 when studio is running."""
    fake_manager._running = True
    result = invoke(fake_manager, "stop")
    assert result.exit_code == 0, result.stdout
    assert fake_manager._running is False


def test_stop_not_running(fake_manager):
    """``stop`` exits 0 even when studio is not running (idempotent)."""
    fake_manager._running = False
    result = invoke(fake_manager, "stop")
    assert result.exit_code == 0, result.stdout


def test_stop_all_flag(fake_manager):
    """``stop --all`` passes stop_gateway=True and stop_llm=True."""
    result = invoke(fake_manager, "stop", "--all")
    assert result.exit_code == 0, result.stdout
    assert fake_manager.last_stop_kwargs == {"stop_gateway": True, "stop_llm": True}


def test_stop_gateway_flag(fake_manager):
    """``stop --stop-gateway`` passes stop_gateway=True, stop_llm=False."""
    result = invoke(fake_manager, "stop", "--stop-gateway")
    assert result.exit_code == 0, result.stdout
    assert fake_manager.last_stop_kwargs == {"stop_gateway": True, "stop_llm": False}


def test_stop_llm_flag(fake_manager):
    """``stop --stop-llm`` passes stop_llm=True, stop_gateway=False."""
    result = invoke(fake_manager, "stop", "--stop-llm")
    assert result.exit_code == 0, result.stdout
    assert fake_manager.last_stop_kwargs == {"stop_gateway": False, "stop_llm": True}


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def test_status_exits_zero(fake_manager):
    """``status`` exits 0 when studio is running."""
    fake_manager._running = True
    result = invoke(fake_manager, "status")
    assert result.exit_code == 0, result.stdout


def test_status_exits_zero_when_not_running(fake_manager):
    """``status`` exits 0 when studio is not running (shows stopped state)."""
    fake_manager._running = False
    result = invoke(fake_manager, "status")
    assert result.exit_code == 0, result.stdout


def test_status_swallows_exception():
    """``status`` exits 0 even when manager.status() raises an exception."""
    bad_manager = FakeStudioManager()

    def _boom():
        raise RuntimeError("status probe failed")

    bad_manager.status = _boom  # type: ignore[method-assign]

    with patch("sage.studio.cli.studio_manager", bad_manager):
        result = runner.invoke(app, ["status"])

    # CLI wraps exception – must not propagate to exit code != 0
    assert result.exit_code == 0, result.stdout


# ---------------------------------------------------------------------------
# logs
# ---------------------------------------------------------------------------


def test_logs_exit_zero(fake_manager):
    """``logs`` exits 0."""
    result = invoke(fake_manager, "logs")
    assert result.exit_code == 0, result.stdout


def test_logs_backend_flag(fake_manager):
    """``logs --backend`` passes backend=True to manager.logs()."""
    result = invoke(fake_manager, "logs", "--backend")
    assert result.exit_code == 0, result.stdout
    assert fake_manager.last_logs_kwargs.get("backend") is True


def test_logs_follow_flag(fake_manager):
    """``logs --follow`` passes follow=True to manager.logs()."""
    result = invoke(fake_manager, "logs", "--follow")
    assert result.exit_code == 0, result.stdout
    assert fake_manager.last_logs_kwargs.get("follow") is True


def test_logs_lines_option(fake_manager):
    """``logs --lines 100`` passes lines=100 to manager.logs()."""
    result = invoke(fake_manager, "logs", "--lines", "100")
    assert result.exit_code == 0, result.stdout
    assert fake_manager.last_logs_kwargs.get("lines") == 100


def test_logs_gateway_flag(fake_manager):
    """``logs --gateway`` passes gateway=True to manager.logs()."""
    result = invoke(fake_manager, "logs", "--gateway")
    assert result.exit_code == 0, result.stdout
    assert fake_manager.last_logs_kwargs.get("gateway") is True


# ---------------------------------------------------------------------------
# restart
# ---------------------------------------------------------------------------


def test_restart_calls_stop_then_start(fake_manager):
    """``restart`` stops then starts the manager."""
    fake_manager._running = True
    result = invoke(fake_manager, "restart")
    assert result.exit_code == 0, result.stdout
    # After restart, manager should be running again
    assert fake_manager._running is True


def test_restart_stop_preserves_llm(fake_manager):
    """``restart`` calls stop(stop_llm=True) per CLI implementation."""
    fake_manager._running = True
    result = invoke(fake_manager, "restart")
    assert result.exit_code == 0, result.stdout
    # cli.py restart calls manager.stop(stop_gateway=False, stop_llm=True)
    assert fake_manager.last_stop_kwargs.get("stop_llm") is True
    assert fake_manager.last_stop_kwargs.get("stop_gateway") is False
