"""Hashnode GraphQL API client."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from core.settings import get_settings
from tools.errors import ToolExecutionError


class HashnodeTool:
    """Publish and manage Hashnode posts."""

    GRAPHQL_URL = "https://gql.hashnode.com"

    def __init__(self) -> None:
        self.settings = get_settings()

    def _headers(self) -> dict[str, str]:
        if not self.settings.hashnode_api_key:
            raise ToolExecutionError("missing HASHNODE_API_KEY")
        return {
            "Authorization": self.settings.hashnode_api_key,
            "Content-Type": "application/json",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=1, max=8))
    def create_post(self, title: str, body: str, tags: list[str], publication_id: str | None = None) -> dict[str, Any]:
        """Create and publish a post on Hashnode."""

        pub_id = publication_id or self.settings.hashnode_publication_id
        if not pub_id:
            raise ToolExecutionError("missing HASHNODE_PUBLICATION_ID")

        mutation = """
        mutation PublishPost($input: PublishPostInput!) {
          publishPost(input: $input) {
            post {
              id
              url
            }
          }
        }
        """
        variables = {
            "input": {
                "title": title,
                "contentMarkdown": body,
                "publicationId": pub_id,
                "tags": [{"name": t} for t in tags],
            }
        }

        with httpx.Client(timeout=20.0) as client:
            resp = client.post(self.GRAPHQL_URL, headers=self._headers(), json={"query": mutation, "variables": variables})
        if resp.status_code >= 400:
            retry_after = _parse_retry_after(resp)
            raise ToolExecutionError("hashnode create_post failed", retry_after_seconds=retry_after)
        data = resp.json()
        post = data.get("data", {}).get("publishPost", {}).get("post")
        if not post:
            raise ToolExecutionError(f"hashnode create_post invalid response: {data}")
        return {"id": post["id"], "url": post["url"]}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=1, max=8))
    def update_post(self, post_id: str, body: str) -> dict[str, Any]:
        """Update existing post body."""

        mutation = """
        mutation UpdatePost($input: UpdatePostInput!) {
          updatePost(input: $input) {
            post {
              id
              url
            }
          }
        }
        """
        variables = {"input": {"id": post_id, "contentMarkdown": body}}

        with httpx.Client(timeout=20.0) as client:
            resp = client.post(self.GRAPHQL_URL, headers=self._headers(), json={"query": mutation, "variables": variables})
        if resp.status_code >= 400:
            retry_after = _parse_retry_after(resp)
            raise ToolExecutionError("hashnode update_post failed", retry_after_seconds=retry_after)

        data = resp.json()
        post = data.get("data", {}).get("updatePost", {}).get("post")
        if not post:
            raise ToolExecutionError(f"hashnode update_post invalid response: {data}")
        return {"id": post["id"], "url": post["url"]}

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=0.5, min=1, max=4))
    def get_post_analytics(self, post_id: str) -> dict[str, Any]:
        """Fetch post analytics snapshot."""

        query = """
        query Post($id: ID!) {
          post(id: $id) {
            views
            responseCount
            reactionCount
          }
        }
        """
        variables = {"id": post_id}
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(self.GRAPHQL_URL, headers=self._headers(), json={"query": query, "variables": variables})
        if resp.status_code >= 400:
            raise ToolExecutionError("hashnode get_post_analytics failed")
        data = resp.json().get("data", {}).get("post", {})
        return {
            "views": data.get("views", 0),
            "reactions": data.get("reactionCount", 0),
            "responses": data.get("responseCount", 0),
        }


def _parse_retry_after(response: httpx.Response) -> int | None:
    header = response.headers.get("Retry-After")
    if not header:
        return None
    try:
        return int(header)
    except ValueError:
        return None
