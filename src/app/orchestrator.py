from __future__ import annotations

import logging
from typing import Any

from src.app.config import AppSettings
from src.domains.refactor_suggestion.tasks import RefactorSuggestionReviewTask
from src.domains.review.tasks import MergeRequestReviewTask, PushReviewTask
from src.infra.clients.gitlab import GitLabClient
from src.infra.queue.inprocess_queue import InProcessWorkerQueue, QueueFullError
from src.infra.repositories.refactor_suggestion_state_repo import RefactorSuggestionStateRepository


logger = logging.getLogger(__name__)

AI_PROGRESS_MESSAGE = (
    "AI가 코드를 검토 중입니다. 잠시만 기다려 주세요.\n"
    "\n"
    "이 코멘트는 자동으로 생성되었습니다."
)
SUPPORTED_MERGE_REQUEST_ACTIONS = {"open", "update", "reopen"}


class WebhookOrchestrator:
    def __init__(
        self,
        *,
        settings: AppSettings,
        gitlab_client: GitLabClient,
        review_queue: InProcessWorkerQueue[MergeRequestReviewTask | PushReviewTask] | None,
        refactor_suggestion_queue: InProcessWorkerQueue[RefactorSuggestionReviewTask] | None,
        refactor_suggestion_state_repo: RefactorSuggestionStateRepository,
        worker_stuck_threshold_seconds: float = 0.0,
    ) -> None:
        self._settings = settings
        self._gitlab_client = gitlab_client
        self._review_queue = review_queue
        self._refactor_suggestion_queue = refactor_suggestion_queue
        self._refactor_suggestion_state_repo = refactor_suggestion_state_repo
        self._worker_stuck_threshold_seconds = worker_stuck_threshold_seconds

    @staticmethod
    def _extract_mr_source_ref(payload: dict[str, Any]) -> str | None:
        object_attributes = payload.get("object_attributes", {})
        last_commit = object_attributes.get("last_commit", {})
        commit_id = last_commit.get("id")
        if commit_id:
            return str(commit_id)

        source_branch = object_attributes.get("source_branch")
        if source_branch:
            return str(source_branch)

        return None

    def _queue_can_accept(
        self,
        queue: InProcessWorkerQueue[Any],
        *,
        queue_label: str,
    ) -> str | None:
        """Return None if the queue can accept work, else a reason string for the 503 body."""
        if not queue.is_healthy(
            stuck_threshold_seconds=self._worker_stuck_threshold_seconds
        ):
            logger.warning(
                "%s queue unhealthy (worker stuck > %ss); rejecting webhook",
                queue_label,
                self._worker_stuck_threshold_seconds,
            )
            return f"{queue_label} worker stuck"
        return None

    def handle_merge_request_event(self, payload: dict[str, Any]) -> tuple[str, int]:
        action = payload["object_attributes"]["action"]
        if action not in SUPPORTED_MERGE_REQUEST_ACTIONS:
            return "Unsupported merge_request action", 200

        project_id = int(payload["project"]["id"])
        mr_id = int(payload["object_attributes"]["iid"])
        logger.info(
            "Handling merge_request: project_id=%s, mr_id=%s, action=%s",
            project_id,
            mr_id,
            action,
        )

        rejections: list[str] = []

        if self._settings.enable_merge_request_review and self._review_queue is not None:
            reason = self._queue_can_accept(self._review_queue, queue_label="review")
            if reason is not None:
                rejections.append(reason)
            else:
                enqueue_error = self._enqueue_merge_request_review(project_id, mr_id)
                if enqueue_error is not None:
                    rejections.append(enqueue_error)

        if (
            action == "open"
            and self._settings.enable_refactor_suggestion_review
            and self._refactor_suggestion_queue is not None
        ):
            reason = self._queue_can_accept(
                self._refactor_suggestion_queue, queue_label="refactor-suggestion"
            )
            if reason is not None:
                rejections.append(reason)
            else:
                enqueue_error = self._enqueue_refactor_suggestion(project_id, mr_id, payload)
                if enqueue_error is not None:
                    rejections.append(enqueue_error)

        if rejections:
            return f"Service Unavailable: {'; '.join(rejections)}", 503
        return "OK", 200

    def _enqueue_merge_request_review(self, project_id: int, mr_id: int) -> str | None:
        """Try to enqueue the MR review task. Posts the progress comment only on success."""
        assert self._review_queue is not None
        try:
            self._review_queue.enqueue(
                MergeRequestReviewTask(project_id=project_id, merge_request_iid=mr_id)
            )
        except QueueFullError as exc:
            logger.warning(
                "Rejecting merge_request review: project_id=%s, mr_id=%s — %s",
                project_id,
                mr_id,
                exc,
            )
            return "review queue full"
        except Exception:
            logger.exception(
                "Failed to enqueue merge_request review task: project_id=%s, mr_id=%s",
                project_id,
                mr_id,
            )
            return "failed to enqueue review task"

        # Only signal "in progress" to the user once the work is actually queued.
        try:
            self._gitlab_client.post_merge_request_comment(
                project_id=project_id,
                merge_request_iid=mr_id,
                body=AI_PROGRESS_MESSAGE,
            )
        except Exception:
            logger.exception(
                "Failed to post AI progress comment for merge_request: project_id=%s, mr_id=%s",
                project_id,
                mr_id,
            )
        return None

    def _enqueue_refactor_suggestion(
        self, project_id: int, mr_id: int, payload: dict[str, Any]
    ) -> str | None:
        assert self._refactor_suggestion_queue is not None
        if not self._refactor_suggestion_state_repo.try_claim(project_id, mr_id):
            logger.info(
                "Skipping refactor suggestion review enqueue (already queued/completed): "
                "project_id=%s, mr_id=%s",
                project_id,
                mr_id,
            )
            return None

        source_ref = self._extract_mr_source_ref(payload)
        if not source_ref:
            logger.warning(
                "Skipping refactor suggestion review enqueue due to missing source ref: "
                "project_id=%s, mr_id=%s",
                project_id,
                mr_id,
            )
            self._refactor_suggestion_state_repo.release_claim(project_id, mr_id)
            return None

        try:
            self._refactor_suggestion_queue.enqueue(
                RefactorSuggestionReviewTask(
                    project_id=project_id,
                    merge_request_iid=mr_id,
                    source_ref=source_ref,
                    max_files=self._settings.refactor_suggestion_max_files,
                    max_file_chars=self._settings.refactor_suggestion_max_file_chars,
                    max_total_chars=self._settings.refactor_suggestion_max_total_chars,
                )
            )
        except QueueFullError as exc:
            logger.warning(
                "Rejecting refactor suggestion review: project_id=%s, mr_id=%s — %s",
                project_id,
                mr_id,
                exc,
            )
            self._refactor_suggestion_state_repo.release_claim(project_id, mr_id)
            return "refactor-suggestion queue full"
        except Exception:
            logger.exception(
                "Failed to enqueue refactor suggestion review task: project_id=%s, mr_id=%s",
                project_id,
                mr_id,
            )
            self._refactor_suggestion_state_repo.release_claim(project_id, mr_id)
            return "failed to enqueue refactor-suggestion task"
        return None

    def handle_push_event(self, payload: dict[str, Any]) -> tuple[str, int]:
        project_id = int(payload["project_id"])
        commit_id = str(payload["after"])

        logger.info(
            "Handling push event: project_id=%s, commit_id=%s",
            project_id,
            commit_id,
        )

        if self._settings.enable_push_review and self._review_queue is not None:
            reason = self._queue_can_accept(self._review_queue, queue_label="review")
            if reason is not None:
                return f"Service Unavailable: {reason}", 503

            try:
                self._review_queue.enqueue(
                    PushReviewTask(project_id=project_id, commit_id=commit_id)
                )
            except QueueFullError as exc:
                logger.warning(
                    "Rejecting push review: project_id=%s, commit_id=%s — %s",
                    project_id,
                    commit_id,
                    exc,
                )
                return "Service Unavailable: review queue full", 503
            except Exception:
                logger.exception(
                    "Failed to enqueue push review task: project_id=%s, commit_id=%s",
                    project_id,
                    commit_id,
                )
                return "Service Unavailable: failed to enqueue push review task", 503

            try:
                self._gitlab_client.post_commit_comment(
                    project_id=project_id,
                    commit_id=commit_id,
                    note=AI_PROGRESS_MESSAGE,
                )
            except Exception:
                logger.exception(
                    "Failed to post AI progress comment for commit: project_id=%s, commit_id=%s",
                    project_id,
                    commit_id,
                )

        return "OK", 200
