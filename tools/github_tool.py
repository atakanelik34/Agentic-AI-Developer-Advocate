"""GitHub REST API client."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from core.settings import get_settings
from tools.errors import ToolExecutionError


class GitHubTool:
    """Client for GitHub issue/discussion interactions and gist publishing."""

    BASE_URL = "https://api.github.com"

    def __init__(self) -> None:
        self.settings = get_settings()

    def _headers(self) -> dict[str, str]:
        if not self.settings.github_token:
            raise ToolExecutionError("missing GITHUB_TOKEN")
        return {
            "Authorization": f"Bearer {self.settings.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=1, max=8))
    def list_recent_issues(self, owner: str, repo: str, per_page: int = 20) -> list[dict[str, Any]]:
        """List recent issues for repository."""

        url = f"{self.BASE_URL}/repos/{owner}/{repo}/issues"
        params = {"state": "open", "per_page": per_page, "sort": "updated"}
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(url, headers=self._headers(), params=params)
        if resp.status_code == 403:
            retry_after = _parse_retry_after(resp)
            raise ToolExecutionError("github rate limit", retry_after_seconds=retry_after)
        if resp.status_code >= 400:
            raise ToolExecutionError(f"github list issues failed: {resp.text}")
        return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=1, max=8))
    def create_issue_comment(self, owner: str, repo: str, issue_number: int, body: str) -> dict[str, Any]:
        """Create comment in issue thread."""

        url = f"{self.BASE_URL}/repos/{owner}/{repo}/issues/{issue_number}/comments"
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(url, headers=self._headers(), json={"body": body[:500]})
        if resp.status_code == 403:
            retry_after = _parse_retry_after(resp)
            raise ToolExecutionError("github rate limit", retry_after_seconds=retry_after)
        if resp.status_code >= 400:
            raise ToolExecutionError(f"github comment failed: {resp.text}")
        return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=1, max=8))
    def create_gist(self, filename: str, content: str, description: str = "") -> dict[str, Any]:
        """Create public gist and return id/url."""

        url = f"{self.BASE_URL}/gists"
        payload = {
            "description": description,
            "public": True,
            "files": {filename: {"content": content}},
        }
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(url, headers=self._headers(), json=payload)
        if resp.status_code == 403:
            retry_after = _parse_retry_after(resp)
            raise ToolExecutionError("github rate limit", retry_after_seconds=retry_after)
        if resp.status_code >= 400:
            raise ToolExecutionError(f"github create gist failed: {resp.text}")
        data = resp.json()
        return {"id": data.get("id", ""), "url": data.get("html_url", "")}


def _parse_retry_after(response: httpx.Response) -> int | None:
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
