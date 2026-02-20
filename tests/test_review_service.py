from src.domains.review.service import ReviewService
from src.domains.review.tasks import MergeRequestReviewTask


class _FakeGitLabClient:
    def __init__(self) -> None:
        self.posted_body = None

    def get_merge_request_changes(self, *, project_id: int, merge_request_iid: int):
        return {"changes": [{"new_path": "a.py", "diff": "+print(1)"}]}

    def post_merge_request_comment(self, *, project_id: int, merge_request_iid: int, body: str):
        self.posted_body = body

    def post_commit_comment(self, *, project_id: int, commit_id: str, note: str):
        self.posted_body = note

    def get_commit_diff(self, *, project_id: int, commit_id: str):
        return [{"new_path": "a.py", "diff": "+print(1)"}]


class _FakeLLMClient:
    def __init__(self, *, should_raise: bool = False) -> None:
        self.should_raise = should_raise
        self.provider_name = "openai"
        self.model_name = "gpt-5-mini"
        self.called = False

    def generate_review_content_with_stats(self, messages):
        self.called = True
        if self.should_raise:
            raise RuntimeError("llm-error")
        return {
            "content": "review-result",
            "provider": self.provider_name,
            "model": self.model_name,
            "elapsed_seconds": 1.23,
        }


class _FakeCacheRepo:
    def __init__(self, *, cached=None) -> None:
        self._cached = cached
        self.put_called = False

    def get(self, *, provider: str, model: str, changes):
        return self._cached

    def put(self, *, provider: str, model: str, changes, result):
        self.put_called = True


class _FakeMonitoring:
    def __init__(self) -> None:
        self.success_calls = 0
        self.error_calls = 0

    def send_success(self, **kwargs):
        self.success_calls += 1

    def send_error(self, **kwargs):
        self.error_calls += 1


def test_review_service_uses_cache_when_available() -> None:
    gitlab = _FakeGitLabClient()
    llm = _FakeLLMClient()
    cache = _FakeCacheRepo(
        cached={
            "content": "cached-review",
            "provider": "openai",
            "model": "gpt-5-mini",
            "elapsed_seconds": 0.5,
        }
    )
    monitoring = _FakeMonitoring()

    service = ReviewService(
        gitlab_client=gitlab,
        llm_client=llm,
        review_cache_repo=cache,
        monitoring_client=monitoring,
        review_system_prompt=None,
    )

    service.run_merge_request_review(MergeRequestReviewTask(project_id=1, merge_request_iid=2))

    assert llm.called is False
    assert monitoring.success_calls == 1
    assert "cached-review" in str(gitlab.posted_body)


def test_review_service_writes_cache_on_miss() -> None:
    gitlab = _FakeGitLabClient()
    llm = _FakeLLMClient()
    cache = _FakeCacheRepo(cached=None)
    monitoring = _FakeMonitoring()

    service = ReviewService(
        gitlab_client=gitlab,
        llm_client=llm,
        review_cache_repo=cache,
        monitoring_client=monitoring,
        review_system_prompt=None,
    )

    service.run_merge_request_review(MergeRequestReviewTask(project_id=1, merge_request_iid=2))

    assert llm.called is True
    assert cache.put_called is True
    assert monitoring.success_calls == 1
