from dataclasses import dataclass


@dataclass(frozen=True)
class RefactorSuggestionReviewTask:
    project_id: int
    merge_request_iid: int
    source_ref: str
    max_files: int
    max_file_chars: int
    max_total_chars: int
