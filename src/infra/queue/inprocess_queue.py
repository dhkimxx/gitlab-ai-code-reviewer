from __future__ import annotations

import logging
import queue
import threading
from typing import Callable, Generic, Optional, TypeVar

from src.shared.rate_limiter import FixedIntervalRateLimiter


logger = logging.getLogger(__name__)

TTask = TypeVar("TTask")


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
    ) -> None:
        if worker_concurrency <= 0:
            raise ValueError("worker_concurrency must be positive")

        self._name = name
        self._handler = handler
        self._job_queue: queue.Queue[TTask] = queue.Queue()
        self._rate_limiter = FixedIntervalRateLimiter(max_requests_per_minute)
        self._max_pending_jobs_soft_limit = max_pending_jobs_soft_limit

        for index in range(worker_concurrency):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"{name}-worker-{index + 1}",
                daemon=True,
            )
            worker.start()

        logger.info(
            "Initialized queue '%s': workers=%s, max_requests_per_minute=%s, max_pending_jobs_soft_limit=%s",
            name,
            worker_concurrency,
            max_requests_per_minute,
            max_pending_jobs_soft_limit,
        )

    def enqueue(self, task: TTask) -> None:
        self._job_queue.put(task)
        self._log_if_queue_too_long()

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
            try:
                self._rate_limiter.acquire()
                self._handler(task)
            except Exception:  # noqa: BLE001 - workers should stay alive
                logger.exception("Unexpected error while processing queue '%s' task", self._name)
            finally:
                self._job_queue.task_done()
