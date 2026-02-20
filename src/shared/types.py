from typing import List, NotRequired, TypedDict


class GitDiffChange(TypedDict, total=False):
    """GitLab diff entry fields used by this project."""

    old_path: str
    new_path: str
    new_file: bool
    deleted_file: bool
    renamed_file: bool
    diff: str


class MergeRequestChangesResponse(TypedDict, total=False):
    """Subset of MR changes response used by this project."""

    changes: List[GitDiffChange]


class ChatMessageDict(TypedDict):
    """Single chat message payload."""

    role: str
    content: str


class LLMReviewResult(TypedDict, total=False):
    """LLM response content plus metadata."""

    content: str
    provider: str
    model: str
    elapsed_seconds: float
    input_tokens: NotRequired[int]
    output_tokens: NotRequired[int]
    total_tokens: NotRequired[int]
