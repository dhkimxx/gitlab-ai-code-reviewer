from src.domains.refactor_suggestion.service import RefactorSuggestionReviewService
from src.domains.refactor_suggestion.tasks import RefactorSuggestionReviewTask


class _FakeGitLabClient:
    def get_merge_request_changes(self, *, project_id: int, merge_request_iid: int):
        return {"changes": [{"new_path": "src/a.py", "diff": "+x"}]}

    def get_repository_file_raw(self, *, project_id: int, file_path: str, ref: str) -> str:
        return "print('hello')"

    def post_merge_request_comment(self, *, project_id: int, merge_request_iid: int, body: str):
        pass


class _FailingLLMClient:
    provider_name = "openai"
    model_name = "gpt-5-mini"

    def generate_review_content_with_stats(self, messages):
        raise RuntimeError("llm-failure")


class _FakeStateRepo:
    def __init__(self) -> None:
        self.completed = False
        self.released = False

    def mark_completed(self, project_id: int, merge_request_iid: int) -> None:
        self.completed = True

    def release_claim(self, project_id: int, merge_request_iid: int) -> None:
        self.released = True


class _FakeMonitoring:
    def __init__(self) -> None:
        self.success_calls = 0
        self.error_calls = 0

    def send_success(self, **kwargs):
        self.success_calls += 1

    def send_error(self, **kwargs):
        self.error_calls += 1


def test_refactor_suggestion_service_releases_claim_on_error() -> None:
    state_repo = _FakeStateRepo()
    monitoring = _FakeMonitoring()

    service = RefactorSuggestionReviewService(
        gitlab_client=_FakeGitLabClient(),
        llm_client=_FailingLLMClient(),
        state_repo=state_repo,
        monitoring_client=monitoring,
    )

    service.run_task(
        RefactorSuggestionReviewTask(
            project_id=1,
            merge_request_iid=2,
            source_ref="main",
            max_files=5,
            max_file_chars=500,
            max_total_chars=2000,
        )
    )

    assert state_repo.released is True
    assert monitoring.error_calls == 1
