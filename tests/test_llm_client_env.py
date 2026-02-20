from typing import Any

import pytest

from src.infra.clients import llm as llm_client
from src.infra.clients.llm import LLMClient, LLMClientConfig


class _DummyResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _DummyChatModel:
    last_init_kwargs: dict[str, Any] | None = None
    last_invoked_messages: list[Any] | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        _DummyChatModel.last_init_kwargs = kwargs

    def invoke(self, messages: list[Any]) -> _DummyResponse:
        _DummyChatModel.last_invoked_messages = messages
        return _DummyResponse("dummy-response")


def _base_config(provider: str) -> LLMClientConfig:
    return LLMClientConfig(
        provider=provider,
        model="dummy-model",
        timeout_seconds=300.0,
        max_retries=0,
        openai_api_key="test-key",
        google_api_key="test-key",
        ollama_base_url="http://localhost:11434",
        openrouter_api_key="test-key",
        openrouter_base_url="https://openrouter.ai/api/v1",
    )


def test_create_llm_openai_uses_chatopenai(monkeypatch: pytest.MonkeyPatch) -> None:
    _DummyChatModel.last_init_kwargs = None
    monkeypatch.setattr(llm_client, "ChatOpenAI", _DummyChatModel)

    cfg = _base_config("openai")
    client = LLMClient(cfg)
    llm = client._create_llm(temperature=0.5)

    assert isinstance(llm, _DummyChatModel)
    assert _DummyChatModel.last_init_kwargs is not None
    assert _DummyChatModel.last_init_kwargs["model"] == "dummy-model"
    assert _DummyChatModel.last_init_kwargs["api_key"] == "test-key"


def test_create_llm_gemini_uses_chatgoogle(monkeypatch: pytest.MonkeyPatch) -> None:
    _DummyChatModel.last_init_kwargs = None
    monkeypatch.setattr(llm_client, "ChatGoogleGenerativeAI", _DummyChatModel)

    cfg = _base_config("gemini")
    client = LLMClient(cfg)
    llm = client._create_llm(temperature=0.3)

    assert isinstance(llm, _DummyChatModel)
    assert _DummyChatModel.last_init_kwargs is not None
    assert _DummyChatModel.last_init_kwargs["model"] == "dummy-model"
    assert _DummyChatModel.last_init_kwargs["api_key"] == "test-key"


def test_create_llm_ollama_uses_chatollama(monkeypatch: pytest.MonkeyPatch) -> None:
    _DummyChatModel.last_init_kwargs = None
    monkeypatch.setattr(llm_client, "ChatOllama", _DummyChatModel)

    cfg = _base_config("ollama")
    client = LLMClient(cfg)
    llm = client._create_llm(temperature=0.7)

    assert isinstance(llm, _DummyChatModel)
    assert _DummyChatModel.last_init_kwargs is not None
    assert _DummyChatModel.last_init_kwargs["model"] == "dummy-model"
    assert _DummyChatModel.last_init_kwargs["base_url"] == "http://localhost:11434"
    assert "request_timeout" in _DummyChatModel.last_init_kwargs


def test_create_llm_openrouter_uses_chatopenai_with_openrouter_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _DummyChatModel.last_init_kwargs = None
    monkeypatch.setattr(llm_client, "ChatOpenAI", _DummyChatModel)

    cfg = _base_config("openrouter")
    client = LLMClient(cfg)
    llm = client._create_llm(temperature=0.9)

    assert isinstance(llm, _DummyChatModel)
    assert _DummyChatModel.last_init_kwargs is not None
    assert _DummyChatModel.last_init_kwargs["model"] == "dummy-model"
    assert _DummyChatModel.last_init_kwargs["api_key"] == "test-key"
    assert _DummyChatModel.last_init_kwargs["base_url"] == "https://openrouter.ai/api/v1"


def test_create_llm_invalid_provider_raises() -> None:
    cfg = _base_config("unknown-provider")
    with pytest.raises(Exception):
        LLMClient(cfg)
