import pytest

from src.app.config import AppSettings
from src.shared.errors import ConfigurationError


_MIN_ENV = {
    "GITLAB_ACCESS_TOKEN": "token",
    "GITLAB_URL": "https://gitlab.example.com",
    "GITLAB_WEBHOOK_SECRET_TOKEN": "secret",
    "LLM_PROVIDER": "openai",
    "OPENAI_API_KEY": "openai-key",
}


def _set_min_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _MIN_ENV.items():
        monkeypatch.setenv(key, value)


def test_app_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_min_env(monkeypatch)

    settings = AppSettings.from_env()

    assert settings.llm_provider == "openai"
    assert settings.llm_model == "gpt-5-mini"
    assert settings.review_max_requests_per_minute == 2
    assert settings.refactor_suggestion_max_files == 20


def test_app_settings_missing_required_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITLAB_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("GITLAB_URL", "https://gitlab.example.com")
    monkeypatch.setenv("GITLAB_WEBHOOK_SECRET_TOKEN", "secret")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    with pytest.raises(ConfigurationError):
        AppSettings.from_env()


def test_app_settings_provider_key_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_min_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with pytest.raises(ConfigurationError):
        AppSettings.from_env()
