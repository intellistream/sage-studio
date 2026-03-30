from __future__ import annotations

import time

import requests


class HealthMonitor:
    """HTTP health probe helper for service startup lifecycle."""

    def probe(self, url: str, timeout: float = 2.0) -> bool:
        try:
            response = requests.get(url, timeout=timeout)
            return 200 <= response.status_code < 300
        except Exception:
            return False

    def wait_ready(
        self,
        *,
        url: str,
        attempts: int = 30,
        interval_seconds: float = 1.0,
        timeout: float = 2.0,
    ) -> bool:
        for _ in range(attempts):
            if self.probe(url, timeout=timeout):
                return True
            time.sleep(interval_seconds)
        return False
