from __future__ import annotations

from typing import List

from src.domains.review.prompt import generate_review_prompt
from src.infra.clients.llm import LLMClient
from src.shared.types import GitDiffChange, LLMReviewResult


class ReviewChain:
    """Prompt -> LLM pipeline wrapper."""

    def __init__(self, *, llm_client: LLMClient, system_instruction: str | None) -> None:
        self._llm_client = llm_client
        self._system_instruction = system_instruction

    def invoke(self, changes: List[GitDiffChange]) -> LLMReviewResult:
        messages = generate_review_prompt(
            changes,
            system_instruction=self._system_instruction,
        )
        return self._llm_client.generate_review_content_with_stats(messages)
