from __future__ import annotations

from sage.studio.supervisor import HealthMonitor


class _FakeMonitor(HealthMonitor):
    def __init__(self, passes_after: int):
        self.calls = 0
        self.passes_after = passes_after

    def probe(self, url: str, timeout: float = 2.0) -> bool:
        self.calls += 1
        return self.calls >= self.passes_after


def test_wait_ready_succeeds() -> None:
    monitor = _FakeMonitor(passes_after=3)
    assert monitor.wait_ready(url="http://unused", attempts=5, interval_seconds=0) is True


def test_wait_ready_timeout() -> None:
    monitor = _FakeMonitor(passes_after=10)
    assert monitor.wait_ready(url="http://unused", attempts=3, interval_seconds=0) is False
