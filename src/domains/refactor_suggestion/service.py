from __future__ import annotations

import logging

from src.domains.refactor_suggestion.prompt import RefactorSuggestionFile, generate_refactor_suggestion_prompt
from src.domains.refactor_suggestion.selector import collect_candidate_paths, truncate_text
from src.domains.refactor_suggestion.tasks import RefactorSuggestionReviewTask
from src.infra.clients.gitlab import GitLabClient
from src.infra.clients.llm import LLMClient
from src.infra.monitoring.llm_webhook import LLMMonitoringWebhookClient
from src.infra.repositories.refactor_suggestion_state_repo import RefactorSuggestionStateRepository
from src.shared.comment_utils import build_llm_footer


logger = logging.getLogger(__name__)


def _build_comment_header() -> str:
    return (
        "### 🌲 Refactor Suggestion Review (Open Event, One-time)\n"
        "이번 코멘트는 **diff 패치 리뷰와 별개**로, 변경된 코드 파일의 전체 본문을 기준으로\n"
        "점진적 리팩토링(리팩토링 제안) 제안을 제공합니다."
    )


def _build_no_target_files_comment() -> str:
    return (
        "### 🌲 Refactor Suggestion Review (Open Event, One-time)\n"
        "이번 MR에서는 리팩토링 제안 리뷰 대상이 되는 코드 파일을 찾지 못해 분석을 생략했습니다."
    )


class RefactorSuggestionReviewService:
    def __init__(
        self,
        *,
        gitlab_client: GitLabClient,
        llm_client: LLMClient,
        state_repo: RefactorSuggestionStateRepository,
        monitoring_client: LLMMonitoringWebhookClient,
    ) -> None:
        self._gitlab_client = gitlab_client
        self._llm_client = llm_client
        self._state_repo = state_repo
        self._monitoring_client = monitoring_client

    def run_task(self, task: RefactorSuggestionReviewTask) -> None:
        logger.info(
            "Running refactor suggestion review: project_id=%s, mr_id=%s, source_ref=%s",
            task.project_id,
            task.merge_request_iid,
            task.source_ref,
        )

        provider = self._llm_client.provider_name
        model = self._llm_client.model_name

        try:
            mr_changes = self._gitlab_client.get_merge_request_changes(
                project_id=task.project_id,
                merge_request_iid=task.merge_request_iid,
            )
            changes = mr_changes.get("changes", [])

            candidate_paths = collect_candidate_paths(changes, task.max_files)
            if not candidate_paths:
                self._gitlab_client.post_merge_request_comment(
                    project_id=task.project_id,
                    merge_request_iid=task.merge_request_iid,
                    body=_build_no_target_files_comment(),
                )
                self._state_repo.mark_completed(task.project_id, task.merge_request_iid)
                return

            files: list[RefactorSuggestionFile] = []
            consumed_chars = 0

            for path in candidate_paths:
                if consumed_chars >= task.max_total_chars:
                    break

                try:
                    raw_content = self._gitlab_client.get_repository_file_raw(
                        project_id=task.project_id,
                        file_path=path,
                        ref=task.source_ref,
                    )
                except Exception:
                    logger.exception(
                        "Failed to fetch repository file for refactor suggestion review: project_id=%s, mr_id=%s, path=%s",
                        task.project_id,
                        task.merge_request_iid,
                        path,
                    )
                    continue

                if not raw_content.strip():
                    continue

                remaining = task.max_total_chars - consumed_chars
                allowed_for_this_file = min(task.max_file_chars, remaining)
                clipped, truncated = truncate_text(raw_content, allowed_for_this_file)
                if not clipped.strip():
                    continue

                files.append(
                    {
                        "path": path,
                        "content": clipped,
                        "truncated": truncated,
                    }
                )
                consumed_chars += len(clipped)

            if not files:
                self._gitlab_client.post_merge_request_comment(
                    project_id=task.project_id,
                    merge_request_iid=task.merge_request_iid,
                    body=_build_no_target_files_comment(),
                )
                self._state_repo.mark_completed(task.project_id, task.merge_request_iid)
                return

            messages = generate_refactor_suggestion_prompt(files)
            llm_result = self._llm_client.generate_review_content_with_stats(messages)

            comment_body = (
                _build_comment_header()
                + "\n\n"
                + llm_result["content"]
                + build_llm_footer(llm_result)
            )
            self._gitlab_client.post_merge_request_comment(
                project_id=task.project_id,
                merge_request_iid=task.merge_request_iid,
                body=comment_body,
            )

            self._monitoring_client.send_success(
                review_type="refactor_suggestion_review",
                gitlab_context={
                    "project_id": task.project_id,
                    "merge_request_iid": task.merge_request_iid,
                },
                llm_result=llm_result,
            )
            self._state_repo.mark_completed(task.project_id, task.merge_request_iid)
        except Exception as error:  # noqa: BLE001 - external APIs wrapper
            logger.exception(
                "Failed to run refactor suggestion review: project_id=%s, mr_id=%s",
                task.project_id,
                task.merge_request_iid,
            )
            self._monitoring_client.send_error(
                review_type="refactor_suggestion_review",
                gitlab_context={
                    "project_id": task.project_id,
                    "merge_request_iid": task.merge_request_iid,
                },
                provider=provider,
                model=model,
                error=error,
            )
            self._state_repo.release_claim(task.project_id, task.merge_request_iid)
