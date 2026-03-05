"""Simple HTTP scraper with JS-compatible fallback placeholders."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from tools.errors import ToolExecutionError


class ScraperTool:
    """Fetch remote pages for context extraction."""

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=1, max=8))
    def fetch(self, url: str) -> dict[str, Any]:
        """Fetch URL content and return basic metadata."""

        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            resp = client.get(url)
        if resp.status_code >= 400:
            raise ToolExecutionError(f"scraper fetch failed: {resp.status_code}")
        return {
            "url": str(resp.url),
            "status": resp.status_code,
            "content_type": resp.headers.get("content-type", ""),
            "text": resp.text[:100000],
        }
