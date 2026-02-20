from dataclasses import dataclass


@dataclass(frozen=True)
class MergeRequestReviewTask:
    project_id: int
    merge_request_iid: int


@dataclass(frozen=True)
class PushReviewTask:
    project_id: int
    commit_id: str
