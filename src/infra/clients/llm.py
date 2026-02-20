from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from time import perf_counter
from typing import List

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from src.shared.errors import LLMInvocationError
from src.shared.types import ChatMessageDict, LLMReviewResult


logger = logging.getLogger(__name__)


class LLMProvider(str, Enum):
    OPENAI = "openai"
    GEMINI = "gemini"
    OLLAMA = "ollama"
    OPENROUTER = "openrouter"


@dataclass(frozen=True)
class LLMClientConfig:
    provider: str
    model: str
    timeout_seconds: float
    max_retries: int
    openai_api_key: str | None
    google_api_key: str | None
    ollama_base_url: str
    openrouter_api_key: str | None
    openrouter_base_url: str


class LLMClient:
    def __init__(self, config: LLMClientConfig) -> None:
        try:
            provider = LLMProvider(config.provider)
        except ValueError as exc:
            raise LLMInvocationError(f"Unsupported LLM provider: {config.provider}") from exc

        self._provider = provider
        self._model = config.model
        self._timeout_seconds = config.timeout_seconds
        self._max_retries = config.max_retries
        self._openai_api_key = config.openai_api_key
        self._google_api_key = config.google_api_key
        self._ollama_base_url = config.ollama_base_url
        self._openrouter_api_key = config.openrouter_api_key
        self._openrouter_base_url = config.openrouter_base_url

    @property
    def provider_name(self) -> str:
        return self._provider.value

    @property
    def model_name(self) -> str:
        return self._model

    @staticmethod
    def _to_langchain_messages(messages: List[ChatMessageDict]) -> List[BaseMessage]:
        lc_messages: List[BaseMessage] = []
        for message in messages:
            role = message.get("role")
            content = message.get("content", "")

            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "user":
                lc_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))
            else:
                logger.warning("Unknown message role '%s', treating as user", role)
                lc_messages.append(HumanMessage(content=content))

        return lc_messages

    def _create_openai_llm(self, temperature: float) -> ChatOpenAI:
        if not self._openai_api_key:
            raise LLMInvocationError("OPENAI_API_KEY is not set")

        if self._model.startswith("gpt-5") and temperature != 1:
            logger.info(
                "Model %s only supports default temperature; ignoring explicit temperature=%s",
                self._model,
                temperature,
            )
            temperature = 1.0

        return ChatOpenAI(
            model=self._model,
            api_key=self._openai_api_key,
            temperature=temperature,
            timeout=self._timeout_seconds,
            max_retries=self._max_retries,
        )

    def _create_gemini_llm(self, temperature: float) -> ChatGoogleGenerativeAI:
        if not self._google_api_key:
            raise LLMInvocationError(
                "GOOGLE_API_KEY is not set (required when LLM_PROVIDER=gemini)"
            )

        return ChatGoogleGenerativeAI(
            model=self._model,
            api_key=self._google_api_key,
            temperature=temperature,
            max_retries=self._max_retries,
        )

    def _create_ollama_llm(self, temperature: float) -> ChatOllama:
        return ChatOllama(
            model=self._model,
            temperature=temperature,
            base_url=self._ollama_base_url,
            request_timeout=self._timeout_seconds,
            max_retries=self._max_retries,
        )

    def _create_openrouter_llm(self, temperature: float) -> ChatOpenAI:
        if not self._openrouter_api_key:
            raise LLMInvocationError(
                "OPENROUTER_API_KEY is not set (required when LLM_PROVIDER=openrouter)"
            )

        return ChatOpenAI(
            model=self._model,
            api_key=self._openrouter_api_key,
            temperature=temperature,
            timeout=self._timeout_seconds,
            base_url=self._openrouter_base_url,
            max_retries=self._max_retries,
        )

    def _create_llm(self, *, temperature: float) -> BaseChatModel:
        logger.info(
            "Creating LLM: provider=%s, model=%s",
            self._provider.value,
            self._model,
        )

        if self._provider is LLMProvider.OPENAI:
            return self._create_openai_llm(temperature)
        if self._provider is LLMProvider.GEMINI:
            return self._create_gemini_llm(temperature)
        if self._provider is LLMProvider.OPENROUTER:
            return self._create_openrouter_llm(temperature)
        if self._provider is LLMProvider.OLLAMA:
            return self._create_ollama_llm(temperature)

        raise LLMInvocationError(f"Unsupported LLM provider: {self._provider.value}")

    def generate_review_content_with_stats(
        self,
        messages: List[ChatMessageDict],
    ) -> LLMReviewResult:
        lc_messages = self._to_langchain_messages(messages)

        llm = self._create_llm(temperature=1.0)

        try:
            started_at = perf_counter()
            response = llm.invoke(lc_messages)
            elapsed = perf_counter() - started_at
        except Exception as exc:  # noqa: BLE001 - external provider wrapper
            raise LLMInvocationError("Failed to invoke LLM") from exc

        content = str(response.content).strip()
        result: LLMReviewResult = {
            "content": content,
            "provider": self._provider.value,
            "model": self._model,
            "elapsed_seconds": elapsed,
        }

        input_tokens = None
        output_tokens = None
        total_tokens = None

        usage_metadata = getattr(response, "usage_metadata", None)
        if isinstance(usage_metadata, dict):
            input_tokens = usage_metadata.get("input_tokens")
            output_tokens = usage_metadata.get("output_tokens")
            total_tokens = usage_metadata.get("total_tokens")
        else:
            response_metadata = getattr(response, "response_metadata", None)
            if isinstance(response_metadata, dict):
                token_usage = response_metadata.get("token_usage") or response_metadata.get(
                    "usage"
                )
                if isinstance(token_usage, dict):
                    input_tokens = token_usage.get("prompt_tokens") or token_usage.get(
                        "input_tokens"
                    )
                    output_tokens = token_usage.get("completion_tokens") or token_usage.get(
                        "output_tokens"
                    )
                    total_tokens = token_usage.get("total_tokens")

        if input_tokens is not None:
            result["input_tokens"] = int(input_tokens)
        if output_tokens is not None:
            result["output_tokens"] = int(output_tokens)
        if total_tokens is not None:
            result["total_tokens"] = int(total_tokens)

        return result
