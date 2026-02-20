from flask import Flask

from src.app.config import AppSettings
from src.app.webhook import register_webhook_routes


class _DummyOrchestrator:
    def __init__(self) -> None:
        self.merge_called = False
        self.push_called = False

    def handle_merge_request_event(self, payload):
        self.merge_called = True
        return "MR", 200

    def handle_push_event(self, payload):
        self.push_called = True
        return "PUSH", 200


def _settings() -> AppSettings:
    return AppSettings(
        log_level="INFO",
        gitlab_access_token="token",
        gitlab_url="https://gitlab.example.com",
        gitlab_webhook_secret_token="secret",
        gitlab_request_timeout_seconds=10.0,
        enable_merge_request_review=True,
        enable_push_review=True,
        enable_refactor_suggestion_review=True,
        review_max_requests_per_minute=2,
        review_worker_concurrency=1,
        review_max_pending_jobs=100,
        refactor_suggestion_max_requests_per_minute=1,
        refactor_suggestion_worker_concurrency=1,
        refactor_suggestion_max_pending_jobs=50,
        refactor_suggestion_max_files=20,
        refactor_suggestion_max_file_chars=12000,
        refactor_suggestion_max_total_chars=60000,
        llm_provider="openai",
        llm_model="gpt-5-mini",
        llm_timeout_seconds=300.0,
        llm_max_retries=0,
        openai_api_key="key",
        google_api_key=None,
        ollama_base_url="http://localhost:11434",
        openrouter_api_key=None,
        openrouter_base_url="https://openrouter.ai/api/v1",
        review_system_prompt=None,
        review_cache_db_path="data/review_cache.db",
        refactor_suggestion_state_db_path="data/refactor_suggestion_state.db",
        llm_monitoring_webhook_url=None,
        llm_monitoring_timeout_seconds=3.0,
    )


def _client():
    app = Flask(__name__)
    orchestrator = _DummyOrchestrator()
    register_webhook_routes(app, settings=_settings(), orchestrator=orchestrator)
    return app.test_client(), orchestrator


def test_webhook_rejects_invalid_token() -> None:
    client, orchestrator = _client()
    resp = client.post("/webhook", json={"object_kind": "push"})
    assert resp.status_code == 403
    assert orchestrator.push_called is False


def test_webhook_routes_merge_request() -> None:
    client, orchestrator = _client()
    resp = client.post(
        "/webhook",
        headers={"X-Gitlab-Token": "secret"},
        json={"object_kind": "merge_request", "object_attributes": {"action": "open"}},
    )
    assert resp.status_code == 200
    assert orchestrator.merge_called is True


def test_webhook_routes_push() -> None:
    client, orchestrator = _client()
    resp = client.post(
        "/webhook",
        headers={"X-Gitlab-Token": "secret"},
        json={"object_kind": "push"},
    )
    assert resp.status_code == 200
    assert orchestrator.push_called is True
