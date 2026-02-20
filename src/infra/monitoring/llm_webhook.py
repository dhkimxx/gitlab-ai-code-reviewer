from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

import requests

from src.shared.types import LLMReviewResult


logger = logging.getLogger(__name__)


class LLMMonitoringWebhookClient:
    def __init__(self, *, webhook_url: str | None, timeout_seconds: float) -> None:
        self._webhook_url = webhook_url.strip() if webhook_url else None
        self._timeout_seconds = timeout_seconds

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _build_llm_section_from_result(result: LLMReviewResult) -> Dict[str, Any]:
        return {
            "provider": result.get("provider"),
            "model": result.get("model"),
            "elapsed_seconds": result.get("elapsed_seconds"),
            "input_tokens": result.get("input_tokens"),
            "output_tokens": result.get("output_tokens"),
            "total_tokens": result.get("total_tokens"),
        }

    def _post_payload(self, payload: Dict[str, Any]) -> None:
        if self._webhook_url is None:
            return

        try:
            response = requests.post(
                self._webhook_url,
                json=payload,
                timeout=self._timeout_seconds,
            )
            if response.status_code >= 400:
                logger.warning(
                    "LLM monitoring webhook returned status_code=%s", response.status_code
                )
        except Exception:  # noqa: BLE001 - non-blocking monitoring
            logger.exception("Failed to send LLM monitoring webhook")

    def send_success(
        self,
        *,
        review_type: str,
        gitlab_context: Dict[str, Any],
        llm_result: LLMReviewResult,
    ) -> None:
        if self._webhook_url is None:
            return

        content = (llm_result.get("content") or "").strip()
        payload: Dict[str, Any] = {
            "status": "success",
            "event": review_type,
            "source": "gitlab-ai-code-reviewer",
            "timestamp": self._now_iso(),
            "gitlab": gitlab_context,
            "llm": self._build_llm_section_from_result(llm_result),
            "review": {
                "content": content,
                "length": len(content),
            },
        }
        self._post_payload(payload)

    def send_error(
        self,
        *,
        review_type: str,
        gitlab_context: Dict[str, Any],
        provider: str,
        model: str,
        error: Exception,
    ) -> None:
        if self._webhook_url is None:
            return

        payload: Dict[str, Any] = {
            "status": "error",
            "event": review_type,
            "source": "gitlab-ai-code-reviewer",
            "timestamp": self._now_iso(),
            "gitlab": gitlab_context,
            "llm": {
                "provider": provider,
                "model": model,
            },
            "error": {
                "type": type(error).__name__,
                "message": str(error),
                "detail": repr(error),
            },
        }
        self._post_payload(payload)
