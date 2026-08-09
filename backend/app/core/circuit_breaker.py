from __future__ import annotations

import inspect
import time


class CircuitOpenError(RuntimeError): pass


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30):
        self.failure_threshold, self.recovery_timeout = failure_threshold, recovery_timeout
        self.failure_count = 0; self.state = "closed"; self.opened_at = 0.0; self.half_open_in_flight = False

    def allow_request(self, now: float | None = None) -> bool:
        now = now if now is not None else time.monotonic()
        if self.state == "closed": return True
        if self.state == "open" and now - self.opened_at >= self.recovery_timeout:
            self.state = "half_open"
        if self.state == "half_open" and not self.half_open_in_flight:
            self.half_open_in_flight = True; return True
        return False

    def record_success(self):
        self.state = "closed"; self.failure_count = 0; self.half_open_in_flight = False

    def record_failure(self, now: float | None = None):
        self.failure_count += 1; self.half_open_in_flight = False
        if self.state == "half_open" or self.failure_count >= self.failure_threshold:
            self.state = "open"; self.opened_at = now if now is not None else time.monotonic()

    async def call(self, function, *args, **kwargs):
        if not self.allow_request(): raise CircuitOpenError("downstream circuit is open")
        try:
            value = function(*args, **kwargs)
            value = await value if inspect.isawaitable(value) else value
        except Exception:
            self.record_failure(); raise
        self.record_success(); return value
