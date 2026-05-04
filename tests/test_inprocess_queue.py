import threading
import time

import pytest

from src.infra.queue.inprocess_queue import InProcessWorkerQueue, QueueFullError


def test_inprocess_queue_processes_tasks() -> None:
    done = threading.Event()
    seen: list[int] = []

    def handler(value: int) -> None:
        seen.append(value)
        done.set()

    q = InProcessWorkerQueue[int](
        name="test",
        handler=handler,
        max_requests_per_minute=600,
        worker_concurrency=1,
        max_pending_jobs_soft_limit=10,
    )

    q.enqueue(1)
    assert done.wait(timeout=2)
    assert seen == [1]


def test_inprocess_queue_worker_survives_handler_exceptions() -> None:
    done = threading.Event()
    count = {"value": 0}

    def handler(value: int) -> None:
        count["value"] += 1
        if value == 1:
            raise RuntimeError("boom")
        done.set()

    q = InProcessWorkerQueue[int](
        name="test-survive",
        handler=handler,
        max_requests_per_minute=600,
        worker_concurrency=1,
        max_pending_jobs_soft_limit=10,
    )

    q.enqueue(1)
    q.enqueue(2)

    assert done.wait(timeout=2)
    assert count["value"] >= 2

    # allow background queue thread to settle for deterministic behavior
    time.sleep(0.05)


def test_enqueue_raises_queue_full_error_when_hard_limit_reached() -> None:
    """Hard limit must surface as `QueueFullError` so callers can apply back-pressure."""
    block = threading.Event()
    started = threading.Event()

    def handler(_value: int) -> None:
        started.set()
        # Park the single worker so the queue stays full for the duration of the test.
        block.wait(timeout=5)

    q = InProcessWorkerQueue[int](
        name="test-hard-limit",
        handler=handler,
        max_requests_per_minute=600,
        worker_concurrency=1,
        max_pending_jobs_soft_limit=1,
        max_pending_jobs_hard_limit=2,
    )

    q.enqueue(1)  # picked up by worker, blocks inside handler
    assert started.wait(timeout=2), "worker did not start processing"

    q.enqueue(2)  # sits in the queue (size=1)
    q.enqueue(3)  # sits in the queue (size=2 == hard limit)

    with pytest.raises(QueueFullError):
        q.enqueue(4)

    block.set()


def test_is_healthy_flips_to_false_when_worker_exceeds_threshold() -> None:
    block = threading.Event()
    started = threading.Event()

    def handler(_value: int) -> None:
        started.set()
        block.wait(timeout=5)

    q = InProcessWorkerQueue[int](
        name="test-health",
        handler=handler,
        max_requests_per_minute=600,
        worker_concurrency=1,
    )

    # Idle queue is healthy at any threshold.
    assert q.is_healthy(stuck_threshold_seconds=0.05) is True

    q.enqueue(1)
    assert started.wait(timeout=2), "worker did not start processing"

    # Wait long enough for the worker to be considered stuck.
    time.sleep(0.15)
    assert q.is_healthy(stuck_threshold_seconds=0.05) is False
    # A non-positive threshold disables the check.
    assert q.is_healthy(stuck_threshold_seconds=0) is True

    block.set()
    # After completion the queue should report healthy again.
    for _ in range(50):
        if q.is_healthy(stuck_threshold_seconds=0.05):
            break
        time.sleep(0.02)
    assert q.is_healthy(stuck_threshold_seconds=0.05) is True
