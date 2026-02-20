import threading
import time

from src.infra.queue.inprocess_queue import InProcessWorkerQueue


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
