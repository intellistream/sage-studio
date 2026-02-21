"""Public Chat manager facade.

Keeps stable import path ``sage.studio.chat_manager`` while delegating
behavior to application-layer manager implementation.
"""

from __future__ import annotations

from sage.studio.application.chat_manager import ChatModeManager as _AppChatModeManager
from sage.studio.supervisor import HealthMonitor, PortResolver, ProcessSupervisor, StartupReporter


class ChatModeManager(_AppChatModeManager):
    """Facade manager exposing supervisor components for startup orchestration."""

    def __init__(self):
        super().__init__()
        self.process_supervisor = ProcessSupervisor()
        self.port_resolver = PortResolver(self.process_supervisor)
        self.health_monitor = HealthMonitor()
        self.startup_reporter = StartupReporter()


__all__ = ["ChatModeManager"]
