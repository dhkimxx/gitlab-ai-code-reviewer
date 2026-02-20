import os

import pytest

from src.domains.review.prompt import generate_review_prompt
from src.infra.clients.gitlab import GitLabClient, GitLabClientConfig


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        pytest.skip(f"{name} is not set; skipping GitLab integration tests.")
    return value


@pytest.mark.integration
def test_generate_review_prompt_with_real_gitlab() -> None:
    base_url = _require_env("GITLAB_URL")
    access_token = _require_env("GITLAB_ACCESS_TOKEN")
    project_id = int(_require_env("GITLAB_TEST_PROJECT_ID"))
    merge_request_iid = int(_require_env("GITLAB_TEST_MERGE_REQUEST_IID"))

    api_base_url = f"{base_url.rstrip('/')}/api/v4"
    client = GitLabClient(
        GitLabClientConfig(
            api_base_url=api_base_url,
            access_token=access_token,
            timeout_seconds=10.0,
        )
    )

    data = client.get_merge_request_changes(
        project_id=project_id,
        merge_request_iid=merge_request_iid,
    )

    changes = data.get("changes", [])
    messages = generate_review_prompt(changes)

    assert isinstance(messages, list)
    assert len(messages) > 0
