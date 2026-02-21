from __future__ import annotations

from pathlib import Path

from sage.studio.supervisor import ProcessSupervisor


def test_read_write_clear_pid(tmp_path: Path) -> None:
    supervisor = ProcessSupervisor()
    pid_file = tmp_path / "service.pid"

    supervisor.write_pid(pid_file, 12345)
    assert supervisor.read_pid(pid_file) == 12345

    supervisor.clear_pid(pid_file)
    assert supervisor.read_pid(pid_file) is None


def test_listener_pid_invalid_port() -> None:
    supervisor = ProcessSupervisor()
    assert supervisor.listener_pid(-1) is None
