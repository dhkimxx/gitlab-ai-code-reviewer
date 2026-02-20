from __future__ import annotations

import logging

from src.domains.review.chain import ReviewChain
from src.domains.review.tasks import MergeRequestReviewTask, PushReviewTask
from src.infra.clients.gitlab import GitLabClient
from src.infra.clients.llm import LLMClient
from src.infra.monitoring.llm_webhook import LLMMonitoringWebhookClient
from src.infra.repositories.review_cache_repo import ReviewCacheRepository
from src.shared.comment_utils import build_ai_error_comment, build_llm_footer
from src.shared.types import GitDiffChange, LLMReviewResult


logger = logging.getLogger(__name__)

ReviewTask = MergeRequestReviewTask | PushReviewTask


class ReviewService:
    def __init__(
        self,
        *,
        gitlab_client: GitLabClient,
        llm_client: LLMClient,
        review_cache_repo: ReviewCacheRepository,
        monitoring_client: LLMMonitoringWebhookClient,
        review_system_prompt: str | None,
    ) -> None:
        self._gitlab_client = gitlab_client
        self._llm_client = llm_client
        self._review_cache_repo = review_cache_repo
        self._monitoring_client = monitoring_client
        self._review_chain = ReviewChain(
            llm_client=llm_client,
            system_instruction=review_system_prompt,
        )

    def run_task(self, task: ReviewTask) -> None:
        if isinstance(task, MergeRequestReviewTask):
            self.run_merge_request_review(task)
            return
        if isinstance(task, PushReviewTask):
            self.run_push_review(task)
            return
        raise TypeError(f"Unknown review task type: {type(task)}")

    def run_merge_request_review(self, task: MergeRequestReviewTask) -> None:
        logger.info(
            "Running merge_request review: project_id=%s, mr_id=%s",
            task.project_id,
            task.merge_request_iid,
        )

        provider = self._llm_client.provider_name
        model = self._llm_client.model_name

        try:
            mr_changes = self._gitlab_client.get_merge_request_changes(
                project_id=task.project_id,
                merge_request_iid=task.merge_request_iid,
            )
            changes: list[GitDiffChange] = mr_changes.get("changes", [])

            llm_result = self._get_or_create_review(provider, model, changes)

            self._monitoring_client.send_success(
                review_type="merge_request_review",
                gitlab_context={
                    "project_id": task.project_id,
                    "merge_request_iid": task.merge_request_iid,
                },
                llm_result=llm_result,
            )

            answer = llm_result["content"] + build_llm_footer(llm_result)
            self._gitlab_client.post_merge_request_comment(
                project_id=task.project_id,
                merge_request_iid=task.merge_request_iid,
                body=answer,
            )
        except Exception as error:  # noqa: BLE001 - external APIs wrapper
            logger.exception(
                "Failed to generate review for merge_request: project_id=%s, mr_id=%s",
                task.project_id,
                task.merge_request_iid,
            )
            self._monitoring_client.send_error(
                review_type="merge_request_review",
                gitlab_context={
                    "project_id": task.project_id,
                    "merge_request_iid": task.merge_request_iid,
                },
                provider=provider,
                model=model,
                error=error,
            )
            error_comment = build_ai_error_comment(
                "AI 코드 리뷰 생성에 실패했습니다. 사람이 직접 리뷰해야 합니다.",
                error,
            )
            try:
                self._gitlab_client.post_merge_request_comment(
                    project_id=task.project_id,
                    merge_request_iid=task.merge_request_iid,
                    body=error_comment,
                )
            except Exception:  # noqa: BLE001 - best effort
                logger.exception(
                    "Failed to post AI error comment for merge_request: project_id=%s, mr_id=%s",
                    task.project_id,
                    task.merge_request_iid,
                )

    def run_push_review(self, task: PushReviewTask) -> None:
        logger.info(
            "Running push review: project_id=%s, commit_id=%s",
            task.project_id,
            task.commit_id,
        )

        provider = self._llm_client.provider_name
        model = self._llm_client.model_name

        try:
            changes = self._gitlab_client.get_commit_diff(
                project_id=task.project_id,
                commit_id=task.commit_id,
            )
            llm_result = self._get_or_create_review(provider, model, changes)

            self._monitoring_client.send_success(
                review_type="push_review",
                gitlab_context={
                    "project_id": task.project_id,
                    "commit_id": task.commit_id,
                },
                llm_result=llm_result,
            )

            answer = llm_result["content"] + build_llm_footer(llm_result)
            self._gitlab_client.post_commit_comment(
                project_id=task.project_id,
                commit_id=task.commit_id,
                note=answer,
            )
        except Exception as error:  # noqa: BLE001 - external APIs wrapper
            logger.exception(
                "Failed to generate review for commit: project_id=%s, commit_id=%s",
                task.project_id,
                task.commit_id,
            )
            self._monitoring_client.send_error(
                review_type="push_review",
                gitlab_context={
                    "project_id": task.project_id,
                    "commit_id": task.commit_id,
                },
                provider=provider,
                model=model,
                error=error,
            )
            error_comment = build_ai_error_comment(
                "AI 코드 리뷰 생성에 실패했습니다. 사람이 직접 리뷰해야 합니다.",
                error,
            )
            try:
                self._gitlab_client.post_commit_comment(
                    project_id=task.project_id,
                    commit_id=task.commit_id,
                    note=error_comment,
                )
            except Exception:  # noqa: BLE001 - best effort
                logger.exception(
                    "Failed to post AI error comment for commit: project_id=%s, commit_id=%s",
                    task.project_id,
                    task.commit_id,
                )

    def _get_or_create_review(
        self,
        provider: str,
        model: str,
        changes: list[GitDiffChange],
    ) -> LLMReviewResult:
        cached = self._review_cache_repo.get(
            provider=provider,
            model=model,
            changes=changes,
        )
        if cached is not None:
            logger.info("Using cached LLM review result")
            return cached

        llm_result = self._review_chain.invoke(changes)
        self._review_cache_repo.put(
            provider=provider,
            model=model,
            changes=changes,
            result=llm_result,
        )
        return llm_result
