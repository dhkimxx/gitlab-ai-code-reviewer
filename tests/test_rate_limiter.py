import threading
import time

import pytest

from src.shared.rate_limiter import FixedIntervalRateLimiter


def test_fixed_interval_rate_limiter_rejects_non_positive_values() -> None:
    with pytest.raises(ValueError):
        FixedIntervalRateLimiter(0)

    with pytest.raises(ValueError):
        FixedIntervalRateLimiter(-1)


def test_fixed_interval_rate_limiter_enforces_minimum_interval_sequential_calls() -> None:
    limiter = FixedIntervalRateLimiter(300)

    timestamps = []
    for _ in range(4):
        limiter.acquire()
        timestamps.append(time.time())

    intervals = [b - a for a, b in zip(timestamps, timestamps[1:])]
    for interval in intervals:
        assert interval >= 0.18


def test_fixed_interval_rate_limiter_enforces_interval_with_multiple_threads() -> None:
    limiter = FixedIntervalRateLimiter(300)

    timestamps = []
    lock = threading.Lock()

    def worker() -> None:
        limiter.acquire()
        with lock:
            timestamps.append(time.time())

    threads = [threading.Thread(target=worker) for _ in range(4)]

    start = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(timestamps) == 4

    timestamps.sort()
    intervals = [b - a for a, b in zip(timestamps, timestamps[1:])]

    total_duration = max(timestamps) - start
    assert total_duration < 2.0

    for interval in intervals:
        assert interval >= 0.18
