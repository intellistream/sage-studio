from __future__ import annotations

import os

from .errors import PortConflictError
from .process_supervisor import ProcessSupervisor


class PortResolver:
    """Resolve and validate service ports with env override support."""

    def __init__(self, process_supervisor: ProcessSupervisor | None = None):
        self._process_supervisor = process_supervisor or ProcessSupervisor()

    def resolve_port(self, *, requested: int | None, env_var: str, default: int) -> int:
        if requested is not None:
            return requested
        env_val = os.getenv(env_var)
        if env_val:
            return int(env_val)
        return default

    def ensure_available(self, port: int, service_name: str) -> None:
        occupied_pid = self._process_supervisor.listener_pid(port)
        if occupied_pid is None:
            return
        raise PortConflictError(
            code="PORT_CONFLICT",
            message=f"{service_name} 端口 {port} 已被占用",
            details={"port": port, "pid": occupied_pid, "service": service_name},
        )
