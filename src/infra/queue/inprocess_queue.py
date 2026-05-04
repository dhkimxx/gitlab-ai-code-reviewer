from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable, Generic, Optional, TypeVar

from src.shared.rate_limiter import FixedIntervalRateLimiter


logger = logging.getLogger(__name__)

TTask = TypeVar("TTask")


class QueueFullError(RuntimeError):
    """Raised by `InProcessWorkerQueue.enqueue` when the hard limit is reached.

    Callers (e.g., the webhook handler) should translate this into a
    back-pressure response (HTTP 503) instead of silently accepting work
    that the workers cannot drain.
    """


class InProcessWorkerQueue(Generic[TTask]):
    """Generic in-process worker queue with global rate limiting."""

    def __init__(
        self,
        *,
        name: str,
        handler: Callable[[TTask], None],
        max_requests_per_minute: int,
        worker_concurrency: int,
        max_pending_jobs_soft_limit: Optional[int] = None,
        max_pending_jobs_hard_limit: Optional[int] = None,
    ) -> None:
        if worker_concurrency <= 0:
            raise ValueError("worker_concurrency must be positive")

        self._name = name
        self._handler = handler
        self._job_queue: queue.Queue[TTask] = queue.Queue()
        self._rate_limiter = FixedIntervalRateLimiter(max_requests_per_minute)
        self._max_pending_jobs_soft_limit = max_pending_jobs_soft_limit
        self._max_pending_jobs_hard_limit = max_pending_jobs_hard_limit

        self._enqueue_lock = threading.Lock()
        self._liveness_lock = threading.Lock()
        # worker thread ident -> monotonic timestamp at which the current
        # task started; absent entries indicate the worker is idle.
        self._active_started_at: dict[int, float] = {}

        for index in range(worker_concurrency):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"{name}-worker-{index + 1}",
                daemon=True,
            )
            worker.start()

        logger.info(
            "Initialized queue '%s': workers=%s, max_requests_per_minute=%s, "
            "max_pending_jobs_soft_limit=%s, max_pending_jobs_hard_limit=%s",
            name,
            worker_concurrency,
            max_requests_per_minute,
            max_pending_jobs_soft_limit,
            max_pending_jobs_hard_limit,
        )

    def enqueue(self, task: TTask) -> None:
        if self._max_pending_jobs_hard_limit and self._max_pending_jobs_hard_limit > 0:
            with self._enqueue_lock:
                current = self._job_queue.qsize()
                if current >= self._max_pending_jobs_hard_limit:
                    raise QueueFullError(
                        f"Queue '{self._name}' is at hard limit "
                        f"({current}/{self._max_pending_jobs_hard_limit}); rejecting enqueue"
                    )
                self._job_queue.put(task)
        else:
            self._job_queue.put(task)
        self._log_if_queue_too_long()

    def pending_jobs(self) -> int:
        return self._job_queue.qsize()

    def is_healthy(self, *, stuck_threshold_seconds: float) -> bool:
        """Return False if any worker has been processing one task longer than the threshold.

        A non-positive threshold disables the check (treated as healthy).
        """
        if stuck_threshold_seconds <= 0:
            return True
        now = time.monotonic()
        with self._liveness_lock:
            for started_at in self._active_started_at.values():
                if now - started_at > stuck_threshold_seconds:
                    return False
        return True

    def _log_if_queue_too_long(self) -> None:
        if (
            not self._max_pending_jobs_soft_limit
            or self._max_pending_jobs_soft_limit <= 0
        ):
            return

        size = self._job_queue.qsize()
        if size > self._max_pending_jobs_soft_limit:
            logger.warning(
                "Queue '%s' length %s exceeded soft limit %s",
                self._name,
                size,
                self._max_pending_jobs_soft_limit,
            )

    def _worker_loop(self) -> None:
        while True:
            task = self._job_queue.get()
            tid = threading.get_ident()
            with self._liveness_lock:
                self._active_started_at[tid] = time.monotonic()
            try:
                self._rate_limiter.acquire()
                self._handler(task)
            except Exception:  # noqa: BLE001 - workers should stay alive
                logger.exception("Unexpected error while processing queue '%s' task", self._name)
            finally:
                with self._liveness_lock:
                    self._active_started_at.pop(tid, None)
                self._job_queue.task_done()
