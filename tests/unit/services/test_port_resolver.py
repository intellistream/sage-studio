from __future__ import annotations

import pytest

from sage.studio.supervisor import PortConflictError, PortResolver, ProcessSupervisor


class _FakeSupervisor(ProcessSupervisor):
    def __init__(self, listener_pid: int | None):
        self._listener_pid = listener_pid

    def listener_pid(self, port: int) -> int | None:
        return self._listener_pid


def test_resolve_port_priority(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = PortResolver(_FakeSupervisor(None))

    monkeypatch.setenv("STUDIO_TEST_PORT", "39001")
    assert (
        resolver.resolve_port(requested=39002, env_var="STUDIO_TEST_PORT", default=39003) == 39002
    )
    assert resolver.resolve_port(requested=None, env_var="STUDIO_TEST_PORT", default=39003) == 39001
    monkeypatch.delenv("STUDIO_TEST_PORT")
    assert resolver.resolve_port(requested=None, env_var="STUDIO_TEST_PORT", default=39003) == 39003


def test_port_conflict_error() -> None:
    resolver = PortResolver(_FakeSupervisor(9876))
    with pytest.raises(PortConflictError) as exc:
        resolver.ensure_available(5173, "studio-frontend")
    assert exc.value.code == "PORT_CONFLICT"
    assert exc.value.details and exc.value.details["pid"] == 9876
