from __future__ import annotations

import signal
from pathlib import Path

import psutil


class ProcessSupervisor:
    """Process lifecycle helper for Studio runtime services."""

    def read_pid(self, pid_file: Path) -> int | None:
        if not pid_file.exists():
            return None
        try:
            return int(pid_file.read_text().strip())
        except (OSError, ValueError):
            return None

    def write_pid(self, pid_file: Path, pid: int) -> None:
        pid_file.write_text(str(pid))

    def clear_pid(self, pid_file: Path) -> None:
        if pid_file.exists():
            pid_file.unlink(missing_ok=True)

    def is_pid_alive(self, pid: int) -> bool:
        return psutil.pid_exists(pid)

    def listener_pid(self, port: int) -> int | None:
        try:
            for conn in psutil.net_connections(kind="inet"):
                if not hasattr(conn, "laddr") or not conn.laddr:
                    continue
                if conn.laddr.port == port and conn.status == psutil.CONN_LISTEN and conn.pid:
                    return conn.pid
        except Exception:
            return None
        return None

    def terminate(self, pid: int, timeout: float = 5.0) -> bool:
        if not self.is_pid_alive(pid):
            return True
        try:
            process = psutil.Process(pid)
            process.terminate()
            process.wait(timeout=timeout)
            return True
        except (psutil.TimeoutExpired, psutil.NoSuchProcess):
            return True
        except psutil.AccessDenied:
            try:
                process = psutil.Process(pid)
                process.send_signal(signal.SIGKILL)
                return True
            except Exception:
                return False
