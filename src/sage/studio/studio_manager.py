"""Public Studio manager facade.

This module keeps stable import path ``sage.studio.studio_manager`` while
delegating behavior to application-layer implementation modules.
"""

from __future__ import annotations

from sage.studio.application.studio_manager import StudioManager as _AppStudioManager
from sage.studio.supervisor import HealthMonitor, PortResolver, ProcessSupervisor, StartupReporter


class StudioManager(_AppStudioManager):
    """Facade manager exposing supervisor components for orchestration."""

    def __init__(self):
        super().__init__()
        self.process_supervisor = ProcessSupervisor()
        self.port_resolver = PortResolver(self.process_supervisor)
        self.health_monitor = HealthMonitor()
        self.startup_reporter = StartupReporter()


__all__ = ["StudioManager"]
