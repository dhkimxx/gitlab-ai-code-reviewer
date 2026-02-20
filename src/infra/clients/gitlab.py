from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List
from urllib.parse import quote

import requests

from src.shared.errors import GitLabAPIError
from src.shared.types import GitDiffChange, MergeRequestChangesResponse


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GitLabClientConfig:
    api_base_url: str
    access_token: str
    timeout_seconds: float


class GitLabClient:
    def __init__(self, config: GitLabClientConfig) -> None:
        self._api_base_url = config.api_base_url
        self._access_token = config.access_token
        self._timeout_seconds = config.timeout_seconds

    def _headers(self) -> Dict[str, str]:
        return {"Private-Token": self._access_token}

    def _request_json(
        self,
        *,
        method: str,
        url: str,
        params: Dict[str, Any] | None = None,
        json_payload: Dict[str, Any] | None = None,
    ) -> Any:
        try:
            response = requests.request(
                method,
                url,
                headers=self._headers(),
                params=params,
                json=json_payload,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else "unknown"
            raise GitLabAPIError(
                f"GitLab API request failed: {method} {url} status={status_code}"
            ) from exc
        except requests.RequestException as exc:
            raise GitLabAPIError(f"GitLab API request failed: {method} {url}") from exc
        except ValueError as exc:
            raise GitLabAPIError(
                f"GitLab API returned invalid JSON: {method} {url}"
            ) from exc

    def _request_text(
        self,
        *,
        method: str,
        url: str,
        params: Dict[str, Any] | None = None,
    ) -> str:
        try:
            response = requests.request(
                method,
                url,
                headers=self._headers(),
                params=params,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            return response.text
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else "unknown"
            raise GitLabAPIError(
                f"GitLab API request failed: {method} {url} status={status_code}"
            ) from exc
        except requests.RequestException as exc:
            raise GitLabAPIError(f"GitLab API request failed: {method} {url}") from exc

    def get_merge_request_changes(
        self,
        *,
        project_id: int,
        merge_request_iid: int,
    ) -> MergeRequestChangesResponse:
        url = (
            f"{self._api_base_url}/projects/{project_id}/merge_requests/{merge_request_iid}/changes"
        )
        data = self._request_json(method="GET", url=url)
        logger.info(
            "Fetched merge_request changes: project_id=%s, mr_id=%s",
            project_id,
            merge_request_iid,
        )

        if not isinstance(data, dict) or "changes" not in data:
            raise GitLabAPIError(
                "Invalid merge request changes response: missing 'changes' field"
            )
        if not isinstance(data.get("changes"), list):
            raise GitLabAPIError(
                "Invalid merge request changes response: 'changes' must be a list"
            )
        return data  # type: ignore[return-value]

    def post_merge_request_comment(
        self,
        *,
        project_id: int,
        merge_request_iid: int,
        body: str,
    ) -> None:
        url = (
            f"{self._api_base_url}/projects/{project_id}/merge_requests/{merge_request_iid}/notes"
        )
        _ = self._request_json(method="POST", url=url, json_payload={"body": body})
        logger.info(
            "Posted merge_request review comment: project_id=%s, mr_id=%s",
            project_id,
            merge_request_iid,
        )

    def get_commit_diff(self, *, project_id: int, commit_id: str) -> List[GitDiffChange]:
        url = f"{self._api_base_url}/projects/{project_id}/repository/commits/{commit_id}/diff"
        data = self._request_json(method="GET", url=url)
        logger.info("Fetched commit diff: project_id=%s, commit_id=%s", project_id, commit_id)

        if not isinstance(data, list):
            raise GitLabAPIError("Invalid commit diff response: expected list")
        return data  # type: ignore[return-value]

    def post_commit_comment(
        self,
        *,
        project_id: int,
        commit_id: str,
        note: str,
    ) -> None:
        url = f"{self._api_base_url}/projects/{project_id}/repository/commits/{commit_id}/comments"
        _ = self._request_json(method="POST", url=url, json_payload={"note": note})
        logger.info(
            "Posted commit review comment: project_id=%s, commit_id=%s",
            project_id,
            commit_id,
        )

    def get_repository_file_raw(
        self,
        *,
        project_id: int,
        file_path: str,
        ref: str,
    ) -> str:
        encoded_path = quote(file_path, safe="")
        url = (
            f"{self._api_base_url}/projects/{project_id}/repository/files/{encoded_path}/raw"
        )
        text = self._request_text(method="GET", url=url, params={"ref": ref})
        logger.info(
            "Fetched repository file raw: project_id=%s, ref=%s, path=%s",
            project_id,
            ref,
            file_path,
        )
        return text
