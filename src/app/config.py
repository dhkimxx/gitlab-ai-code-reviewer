from __future__ import annotations

import os
from dataclasses import dataclass

from src.shared.errors import ConfigurationError


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _get_optional_str(name: str) -> str | None:
    return _clean_optional(os.environ.get(name))


def _get_required_str(name: str, *, required: bool = True) -> str:
    value = _clean_optional(os.environ.get(name))
    if value is None:
        if required:
            raise ConfigurationError(f"Missing required environment variable: {name}")
        return ""
    return value


def _get_bool(name: str, default: bool) -> bool:
    raw = _clean_optional(os.environ.get(name))
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def _get_int(name: str, default: int, *, min_value: int | None = None) -> int:
    raw = _clean_optional(os.environ.get(name))
    if raw is None:
        value = default
    else:
        try:
            value = int(raw)
        except ValueError as exc:
            raise ConfigurationError(f"Invalid integer for {name}: {raw}") from exc

    if min_value is not None and value < min_value:
        raise ConfigurationError(f"{name} must be >= {min_value}")
    return value


def _get_float(name: str, default: float, *, min_value: float | None = None) -> float:
    raw = _clean_optional(os.environ.get(name))
    if raw is None:
        value = default
    else:
        try:
            value = float(raw)
        except ValueError as exc:
            raise ConfigurationError(f"Invalid float for {name}: {raw}") from exc

    if min_value is not None and value < min_value:
        raise ConfigurationError(f"{name} must be >= {min_value}")
    return value


@dataclass(frozen=True)
class AppSettings:
    log_level: str

    gitlab_access_token: str
    gitlab_url: str
    gitlab_webhook_secret_token: str
    gitlab_request_timeout_seconds: float

    enable_merge_request_review: bool
    enable_push_review: bool
    enable_refactor_suggestion_review: bool

    review_max_requests_per_minute: int
    review_worker_concurrency: int
    review_max_pending_jobs: int

    refactor_suggestion_max_requests_per_minute: int
    refactor_suggestion_worker_concurrency: int
    refactor_suggestion_max_pending_jobs: int
    refactor_suggestion_max_files: int
    refactor_suggestion_max_file_chars: int
    refactor_suggestion_max_total_chars: int

    llm_provider: str
    llm_model: str
    llm_timeout_seconds: float
    llm_max_retries: int
    openai_api_key: str | None
    google_api_key: str | None
    ollama_base_url: str
    openrouter_api_key: str | None
    openrouter_base_url: str

    review_system_prompt: str | None

    review_cache_db_path: str
    refactor_suggestion_state_db_path: str

    llm_monitoring_webhook_url: str | None
    llm_monitoring_timeout_seconds: float

    @property
    def gitlab_api_base_url(self) -> str:
        return f"{self.gitlab_url.rstrip('/')}/api/v4"

    @classmethod
    def from_env(cls, *, require_webhook_secret: bool = True) -> "AppSettings":
        provider = (_get_optional_str("LLM_PROVIDER") or "openai").lower()
        if provider not in {"openai", "gemini", "ollama", "openrouter"}:
            raise ConfigurationError(f"Unsupported LLM_PROVIDER: {provider}")

        llm_model = _get_optional_str("LLM_MODEL") or "gpt-5-mini"

        settings = cls(
            log_level=(_get_optional_str("LOG_LEVEL") or "INFO").upper(),
            gitlab_access_token=_get_required_str("GITLAB_ACCESS_TOKEN"),
            gitlab_url=_get_required_str("GITLAB_URL"),
            gitlab_webhook_secret_token=_get_required_str(
                "GITLAB_WEBHOOK_SECRET_TOKEN", required=require_webhook_secret
            ),
            gitlab_request_timeout_seconds=_get_float(
                "GITLAB_REQUEST_TIMEOUT_SECONDS", 10.0, min_value=0.001
            ),
            enable_merge_request_review=_get_bool("ENABLE_MERGE_REQUEST_REVIEW", True),
            enable_push_review=_get_bool("ENABLE_PUSH_REVIEW", True),
            enable_refactor_suggestion_review=_get_bool("ENABLE_REFACTOR_SUGGESTION_REVIEW", True),
            review_max_requests_per_minute=_get_int(
                "REVIEW_MAX_REQUESTS_PER_MINUTE", 2, min_value=1
            ),
            review_worker_concurrency=_get_int(
                "REVIEW_WORKER_CONCURRENCY", 1, min_value=1
            ),
            review_max_pending_jobs=_get_int("REVIEW_MAX_PENDING_JOBS", 100, min_value=1),
            refactor_suggestion_max_requests_per_minute=_get_int(
                "REFACTOR_SUGGESTION_MAX_REQUESTS_PER_MINUTE", 1, min_value=1
            ),
            refactor_suggestion_worker_concurrency=_get_int(
                "REFACTOR_SUGGESTION_WORKER_CONCURRENCY", 1, min_value=1
            ),
            refactor_suggestion_max_pending_jobs=_get_int(
                "REFACTOR_SUGGESTION_MAX_PENDING_JOBS", 50, min_value=1
            ),
            refactor_suggestion_max_files=_get_int("REFACTOR_SUGGESTION_MAX_FILES", 20, min_value=1),
            refactor_suggestion_max_file_chars=_get_int(
                "REFACTOR_SUGGESTION_MAX_FILE_CHARS", 12000, min_value=1
            ),
            refactor_suggestion_max_total_chars=_get_int(
                "REFACTOR_SUGGESTION_MAX_TOTAL_CHARS", 60000, min_value=1
            ),
            llm_provider=provider,
            llm_model=llm_model,
            llm_timeout_seconds=_get_float("LLM_TIMEOUT_SECONDS", 300.0, min_value=0.001),
            llm_max_retries=_get_int("LLM_MAX_RETRIES", 0, min_value=0),
            openai_api_key=_get_optional_str("OPENAI_API_KEY"),
            google_api_key=_get_optional_str("GOOGLE_API_KEY"),
            ollama_base_url=_get_optional_str("OLLAMA_BASE_URL")
            or "http://localhost:11434",
            openrouter_api_key=_get_optional_str("OPENROUTER_API_KEY"),
            openrouter_base_url=_get_optional_str("OPENROUTER_BASE_URL")
            or "https://openrouter.ai/api/v1",
            review_system_prompt=_get_optional_str("REVIEW_SYSTEM_PROMPT"),
            review_cache_db_path=_get_optional_str("REVIEW_CACHE_DB_PATH")
            or "data/review_cache.db",
            refactor_suggestion_state_db_path=_get_optional_str("REFACTOR_SUGGESTION_STATE_DB_PATH")
            or "data/refactor_suggestion_state.db",
            llm_monitoring_webhook_url=_get_optional_str("LLM_MONITORING_WEBHOOK_URL"),
            llm_monitoring_timeout_seconds=_get_float(
                "LLM_MONITORING_TIMEOUT_SECONDS", 3.0, min_value=0.001
            ),
        )

        if (
            not settings.enable_merge_request_review
            and not settings.enable_push_review
            and not settings.enable_refactor_suggestion_review
        ):
            raise ConfigurationError(
                "At least one of ENABLE_MERGE_REQUEST_REVIEW, ENABLE_PUSH_REVIEW, ENABLE_REFACTOR_SUGGESTION_REVIEW must be true"
            )

        if settings.llm_provider == "openai" and not settings.openai_api_key:
            raise ConfigurationError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        if settings.llm_provider == "gemini" and not settings.google_api_key:
            raise ConfigurationError("GOOGLE_API_KEY is required when LLM_PROVIDER=gemini")
        if settings.llm_provider == "openrouter" and not settings.openrouter_api_key:
            raise ConfigurationError(
                "OPENROUTER_API_KEY is required when LLM_PROVIDER=openrouter"
            )

        return settings
