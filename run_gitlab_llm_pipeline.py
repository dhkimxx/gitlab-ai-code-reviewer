"""GitLab MR diff를 가져와 LLM 리뷰 파이프라인을 직접 실행하는 스크립트."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from src.app.config import AppSettings
from src.domains.review.chain import ReviewChain
from src.infra.clients.gitlab import GitLabClient, GitLabClientConfig
from src.infra.clients.llm import LLMClient, LLMClientConfig


PROJECT_ROOT = Path(__file__).resolve().parent
ENV_PATH = PROJECT_ROOT / ".env"

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH, override=False)


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        msg = f"{name} is not set; unable to run GitLab→LLM pipeline."
        raise RuntimeError(msg)
    return value


def _setup_logging() -> logging.Logger:
    log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    logging.basicConfig(level=log_level)
    logger = logging.getLogger("gitlab_llm_pipeline")

    if log_level == logging.INFO and log_level_name != "INFO":
        logger.warning("Invalid LOG_LEVEL '%s', defaulting to INFO", log_level_name)

    return logger


def main() -> None:
    logger = _setup_logging()
    settings = AppSettings.from_env(require_webhook_secret=False)

    project_id_raw = _require_env("GITLAB_TEST_PROJECT_ID")
    mr_iid_raw = _require_env("GITLAB_TEST_MERGE_REQUEST_IID")

    try:
        project_id = int(project_id_raw)
        merge_request_iid = int(mr_iid_raw)
    except ValueError as exc:  # noqa: TRY003 - env validation wrapper
        raise ValueError(
            "GITLAB_TEST_PROJECT_ID and GITLAB_TEST_MERGE_REQUEST_IID must be integers"
        ) from exc

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

    logger.info(
        "Fetching merge_request changes: base_url=%s, project_id=%s, mr_iid=%s",
        settings.gitlab_api_base_url,
        project_id,
        merge_request_iid,
    )

    mr_changes = gitlab_client.get_merge_request_changes(
        project_id=project_id,
        merge_request_iid=merge_request_iid,
    )

    changes = mr_changes.get("changes", [])
    if not changes:
        logger.warning("No changes found in target merge request; nothing to review.")
        return

    logger.info("Running review_chain with %s changes", len(changes))

    review_chain = ReviewChain(
        llm_client=llm_client,
        system_instruction=settings.review_system_prompt,
    )
    result = review_chain.invoke(changes)

    content = (result.get("content") or "").strip()

    print("\n===== LLM REVIEW START =====\n")
    if content:
        print(content)
    else:
        print("[warning] LLM returned empty content")
    print("\n===== LLM REVIEW END =====\n")

    print("[LLM metadata]")
    provider = result.get("provider")
    model = result.get("model")
    elapsed = result.get("elapsed_seconds")
    if provider is not None:
        print(f"provider={provider}")
    if model is not None:
        print(f"model={model}")
    if elapsed is not None:
        print(f"elapsed_seconds={elapsed}")

    for key in ("input_tokens", "output_tokens", "total_tokens"):
        value = result.get(key)
        if value is not None:
            print(f"{key}={value}")


if __name__ == "__main__":
    main()
