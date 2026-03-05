"""RevenueCat API and docs helpers."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from core.settings import get_settings
from tools.errors import ToolExecutionError


class RevenueCatTool:
    """Client for RevenueCat Charts API and docs pages."""

    BASE_URL = "https://api.revenuecat.com/v1"

    def __init__(self) -> None:
        self.settings = get_settings()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=1, max=8))
    def get_app_overview(self, api_key: str | None = None) -> dict[str, Any]:
        """Return app overview metrics from RevenueCat API."""

        key = api_key or self.settings.revenuecat_api_key
        if not key:
            raise ToolExecutionError("missing RevenueCat API key")

        headers = {"Authorization": f"Bearer {key}"}
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(f"{self.BASE_URL}/subscribers", headers=headers)
        if resp.status_code >= 400:
            raise ToolExecutionError(f"RevenueCat app overview failed: {resp.text}")
        return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=1, max=8))
    def get_subscriber_metrics(self, api_key: str | None = None, period: str = "7d") -> dict[str, Any]:
        """Return subscriber trend metrics."""

        key = api_key or self.settings.revenuecat_api_key
        if not key:
            raise ToolExecutionError("missing RevenueCat API key")

        headers = {"Authorization": f"Bearer {key}"}
        params = {"period": period}
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(f"{self.BASE_URL}/metrics/subscribers", headers=headers, params=params)
        if resp.status_code >= 400:
            raise ToolExecutionError(f"RevenueCat subscriber metrics failed: {resp.text}")
        return resp.json()

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=0.5, min=1, max=4))
    def fetch_docs_page(self, path: str) -> str:
        """Fetch docs.revenuecat.com page contents as HTML string."""

        url = f"https://docs.revenuecat.com/{path.lstrip('/')}"
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(url)
        if resp.status_code >= 400:
            raise ToolExecutionError(f"fetch_docs_page failed: {resp.status_code}")
        return resp.text

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=0.5, min=1, max=4))
    def fetch_changelog(self) -> list[dict[str, Any]]:
        """Fetch latest changelog snippets from RevenueCat site."""

        url = "https://www.revenuecat.com/changelog/"
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(url)
        if resp.status_code >= 400:
            raise ToolExecutionError("fetch_changelog failed")
        return [{"source": url, "html": resp.text[:10000]}]

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=0.5, min=1, max=4))
    def search_docs(self, query: str) -> list[dict[str, Any]]:
        """Simple docs search using site search endpoint fallback."""

        url = "https://docs.revenuecat.com/search"
        params = {"q": query}
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(url, params=params)
        if resp.status_code >= 400:
            raise ToolExecutionError("search_docs failed")
        return [{"query": query, "html": resp.text[:10000]}]
