from __future__ import annotations

import logging

from flask import Flask

from src.app.config import AppSettings
from src.app.orchestrator import WebhookOrchestrator
from src.app.webhook import register_webhook_routes
from src.domains.refactor_suggestion.service import RefactorSuggestionReviewService
from src.domains.review.service import ReviewService
from src.domains.review.tasks import MergeRequestReviewTask, PushReviewTask
from src.domains.refactor_suggestion.tasks import RefactorSuggestionReviewTask
from src.infra.clients.gitlab import GitLabClient, GitLabClientConfig
from src.infra.clients.llm import LLMClient, LLMClientConfig
from src.infra.monitoring.llm_webhook import LLMMonitoringWebhookClient
from src.infra.queue.inprocess_queue import InProcessWorkerQueue
from src.infra.repositories.refactor_suggestion_state_repo import RefactorSuggestionStateRepository
from src.infra.repositories.review_cache_repo import ReviewCacheRepository


def _setup_logging(log_level_name: str) -> None:
    level = getattr(logging, log_level_name.upper(), None)
    if not isinstance(level, int):
        level = logging.INFO
        logging.basicConfig(level=level)
        logging.getLogger(__name__).warning(
            "Invalid LOG_LEVEL '%s', defaulting to INFO",
            log_level_name,
        )
        return

    logging.basicConfig(level=level)


def create_app() -> Flask:
    settings = AppSettings.from_env()
    _setup_logging(settings.log_level)

    gitlab_client = GitLabClient(
        GitLabClientConfig(
            api_base_url=settings.gitlab_api_base_url,
            access_token=settings.gitlab_access_token,
            timeout_seconds=settings.gitlab_request_timeout_seconds,
        )
    )

    llm_client = LLMClient(
        LLMClientConfig(
            provider=settings.llm_provider,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
            openai_api_key=settings.openai_api_key,
            google_api_key=settings.google_api_key,
            ollama_base_url=settings.ollama_base_url,
            openrouter_api_key=settings.openrouter_api_key,
            openrouter_base_url=settings.openrouter_base_url,
        )
    )

    monitoring_client = LLMMonitoringWebhookClient(
        webhook_url=settings.llm_monitoring_webhook_url,
        timeout_seconds=settings.llm_monitoring_timeout_seconds,
    )
    review_cache_repo = ReviewCacheRepository(settings.review_cache_db_path)
    refactor_suggestion_state_repo = RefactorSuggestionStateRepository(settings.refactor_suggestion_state_db_path)

    review_service = ReviewService(
        gitlab_client=gitlab_client,
        llm_client=llm_client,
        review_cache_repo=review_cache_repo,
        monitoring_client=monitoring_client,
        review_system_prompt=settings.review_system_prompt,
    )
    refactor_suggestion_service = RefactorSuggestionReviewService(
        gitlab_client=gitlab_client,
        llm_client=llm_client,
        state_repo=refactor_suggestion_state_repo,
        monitoring_client=monitoring_client,
    )

    review_queue: InProcessWorkerQueue[MergeRequestReviewTask | PushReviewTask] | None = None
    if settings.enable_merge_request_review or settings.enable_push_review:
        review_queue = InProcessWorkerQueue(
            name="review",
            handler=review_service.run_task,
            max_requests_per_minute=settings.review_max_requests_per_minute,
            worker_concurrency=settings.review_worker_concurrency,
            max_pending_jobs_soft_limit=settings.review_max_pending_jobs,
        )

    refactor_suggestion_queue: InProcessWorkerQueue[RefactorSuggestionReviewTask] | None = None
    if settings.enable_refactor_suggestion_review:
        refactor_suggestion_queue = InProcessWorkerQueue(
            name="refactor-suggestion",
            handler=refactor_suggestion_service.run_task,
            max_requests_per_minute=settings.refactor_suggestion_max_requests_per_minute,
            worker_concurrency=settings.refactor_suggestion_worker_concurrency,
            max_pending_jobs_soft_limit=settings.refactor_suggestion_max_pending_jobs,
        )

    orchestrator = WebhookOrchestrator(
        settings=settings,
        gitlab_client=gitlab_client,
        review_queue=review_queue,
        refactor_suggestion_queue=refactor_suggestion_queue,
        refactor_suggestion_state_repo=refactor_suggestion_state_repo,
    )

    app = Flask(__name__)
    register_webhook_routes(app, settings=settings, orchestrator=orchestrator)
    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9655)
