import threading
import time


class FixedIntervalRateLimiter:
    """Fixed-interval limiter shared by queue workers."""

    def __init__(self, max_requests_per_minute: int) -> None:
        if max_requests_per_minute <= 0:
            raise ValueError("max_requests_per_minute must be positive")

        self._interval_seconds = 60.0 / float(max_requests_per_minute)
        self._lock = threading.Lock()
        self._next_available_time = 0.0

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.time()
                wait = max(0.0, self._next_available_time - now)
                if wait <= 0.0:
                    start_time = max(now, self._next_available_time)
                    self._next_available_time = start_time + self._interval_seconds
                    return
            time.sleep(wait)
