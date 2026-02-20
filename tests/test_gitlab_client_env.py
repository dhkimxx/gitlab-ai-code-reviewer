import os

import pytest

from src.infra.clients.gitlab import GitLabClient, GitLabClientConfig


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        pytest.skip(f"{name} is not set; skipping GitLab integration tests.")
    return value


@pytest.mark.integration
def test_get_merge_request_changes_with_real_gitlab() -> None:
    base_url = _require_env("GITLAB_URL")
    access_token = _require_env("GITLAB_ACCESS_TOKEN")
    project_id = int(_require_env("GITLAB_TEST_PROJECT_ID"))
    merge_request_iid = int(_require_env("GITLAB_TEST_MERGE_REQUEST_IID"))

    client = GitLabClient(
        GitLabClientConfig(
            api_base_url=f"{base_url.rstrip('/')}/api/v4",
            access_token=access_token,
            timeout_seconds=10.0,
        )
    )

    data = client.get_merge_request_changes(
        project_id=project_id,
        merge_request_iid=merge_request_iid,
    )

    assert isinstance(data, dict)
    assert "changes" in data


@pytest.mark.integration
def test_get_commit_diff_with_real_gitlab() -> None:
    base_url = _require_env("GITLAB_URL")
    access_token = _require_env("GITLAB_ACCESS_TOKEN")
    project_id = int(_require_env("GITLAB_TEST_PROJECT_ID"))
    commit_id = _require_env("GITLAB_TEST_COMMIT_ID")

    client = GitLabClient(
        GitLabClientConfig(
            api_base_url=f"{base_url.rstrip('/')}/api/v4",
            access_token=access_token,
            timeout_seconds=10.0,
        )
    )

    diffs = client.get_commit_diff(
        project_id=project_id,
        commit_id=commit_id,
    )

    assert isinstance(diffs, list)
