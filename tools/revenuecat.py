"""RevenueCat API and docs helpers."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from core.settings import get_settings
from tools.errors import ToolExecutionError


class RevenueCatTool:
    """Client for RevenueCat REST API v2 plus v1 compatibility endpoints."""

    V1_BASE_URL = "https://api.revenuecat.com/v1"
    V2_BASE_URL = "https://api.revenuecat.com/v2"
    V2_ENDPOINT_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "config" / "revenuecat_v2_endpoints.json"

    def __init__(self) -> None:
        self.settings = get_settings()
        self._v2_endpoint_registry = _load_v2_endpoint_registry(self.V2_ENDPOINT_REGISTRY_PATH)

    def _headers(self, api_key: str | None = None) -> dict[str, str]:
        key = api_key or self.settings.revenuecat_api_key
        if not key:
            raise ToolExecutionError("missing REVENUECAT_API_KEY")
        return {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    def _project_id(self, project_id: str | None = None) -> str:
        value = project_id or self.settings.revenuecat_project_id
        if not value:
            raise ToolExecutionError("missing REVENUECAT_PROJECT_ID")
        return value

    @staticmethod
    def _normalize_v2_template(path_template: str) -> str:
        raw = path_template.strip()
        if raw.startswith("https://api.revenuecat.com/v2"):
            raw = raw[len("https://api.revenuecat.com/v2") :]
        if raw.startswith("/v2/"):
            raw = raw[len("/v2") :]
        if not raw.startswith("/"):
            raw = "/" + raw
        return raw

    def _validate_v2_endpoint(self, method: str, path_template: str) -> None:
        allowed_methods = self._v2_endpoint_registry.get(path_template)
        if allowed_methods is None:
            raise ToolExecutionError(f"unsupported v2 path template: {path_template}")
        normalized_method = method.upper().strip()
        if normalized_method not in allowed_methods:
            methods = ",".join(allowed_methods)
            raise ToolExecutionError(
                f"unsupported v2 method '{normalized_method}' for {path_template}; allowed={methods}",
            )

    @staticmethod
    def _resolve_path_template(path_template: str, path_params: dict[str, Any]) -> str:
        path = path_template
        for key, value in path_params.items():
            path = path.replace("{" + key + "}", quote(str(value), safe=""))
        if "{" in path or "}" in path:
            raise ToolExecutionError(f"unresolved path placeholders in template: {path_template}")
        return path

    def _v1_headers(self, api_key: str | None = None) -> dict[str, str]:
        key = api_key or self.settings.revenuecat_v1_api_key or self.settings.revenuecat_api_key
        if not key:
            raise ToolExecutionError("missing REVENUECAT_V1_API_KEY or REVENUECAT_API_KEY")
        return {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=1, max=8))
    def _request_json(
        self,
        method: str,
        path: str,
        *,
        api_key: str | None = None,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{path}" if path.startswith("http") else f"https://api.revenuecat.com{path}"
        with httpx.Client(timeout=20.0) as client:
            resp = client.request(
                method=method.upper(),
                url=url,
                headers=self._headers(api_key),
                params=params,
                json=json,
            )
        if resp.status_code == 429:
            raise ToolExecutionError(
                "revenuecat rate limit",
                retry_after_seconds=_parse_retry_after(resp),
            )
        if resp.status_code >= 400:
            raise ToolExecutionError(f"revenuecat request failed [{resp.status_code}]: {resp.text}")
        return resp.json()

    @staticmethod
    def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
        items = payload.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
        data = payload.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def list_v2_endpoints(self) -> list[dict[str, Any]]:
        """Return all v2 endpoint templates and allowed methods from registry."""

        return [{"path": path, "methods": methods} for path, methods in self._v2_endpoint_registry.items()]

    def request_v2(
        self,
        method: str,
        path_template: str,
        *,
        project_id: str | None = None,
        path_params: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        api_key: str | None = None,
        validate: bool = True,
    ) -> dict[str, Any]:
        """Call any RevenueCat v2 endpoint by template path with placeholder substitution."""

        template = self._normalize_v2_template(path_template)
        if validate:
            self._validate_v2_endpoint(method, template)

        replacements = dict(path_params or {})
        if "{project_id}" in template and "project_id" not in replacements:
            replacements["project_id"] = self._project_id(project_id)
        resolved_path = self._resolve_path_template(template, replacements)
        return self._request_json(
            method=method,
            path=f"{self.V2_BASE_URL}{resolved_path}",
            api_key=api_key,
            params=params,
            json=payload,
        )

    # --- V2: project-level operations ---

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=1, max=8))
    def get_projects(self, api_key: str | None = None) -> list[dict[str, Any]]:
        """List projects available to this API key."""

        payload = self._request_json("GET", f"{self.V2_BASE_URL}/projects", api_key=api_key)
        return self._extract_items(payload)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=1, max=8))
    def get_project_overview(
        self,
        project_id: str | None = None,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """Fetch v2 project overview metrics (/metrics/overview)."""

        pid = self._project_id(project_id)
        return self._request_json("GET", f"{self.V2_BASE_URL}/projects/{pid}/metrics/overview", api_key=api_key)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=1, max=8))
    def get_customer_v2(
        self,
        customer_id: str,
        project_id: str | None = None,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """Fetch customer object from v2."""

        pid = self._project_id(project_id)
        cid = quote(customer_id, safe="")
        return self._request_json(
            "GET",
            f"{self.V2_BASE_URL}/projects/{pid}/customers/{cid}",
            api_key=api_key,
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=1, max=8))
    def get_customer_subscriptions(
        self,
        customer_id: str,
        project_id: str | None = None,
        api_key: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch customer subscriptions list from v2."""

        pid = self._project_id(project_id)
        cid = quote(customer_id, safe="")
        payload = self._request_json(
            "GET",
            f"{self.V2_BASE_URL}/projects/{pid}/customers/{cid}/subscriptions",
            api_key=api_key,
        )
        return self._extract_items(payload)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=1, max=8))
    def get_customer_active_entitlements(
        self,
        customer_id: str,
        project_id: str | None = None,
        api_key: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch active entitlements list for customer from v2."""

        pid = self._project_id(project_id)
        cid = quote(customer_id, safe="")
        payload = self._request_json(
            "GET",
            f"{self.V2_BASE_URL}/projects/{pid}/customers/{cid}/active_entitlements",
            api_key=api_key,
        )
        return self._extract_items(payload)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=1, max=8))
    def list_products(
        self,
        project_id: str | None = None,
        api_key: str | None = None,
    ) -> list[dict[str, Any]]:
        """List products for a project from v2."""

        pid = self._project_id(project_id)
        payload = self._request_json("GET", f"{self.V2_BASE_URL}/projects/{pid}/products", api_key=api_key)
        return self._extract_items(payload)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=1, max=8))
    def list_offerings(
        self,
        project_id: str | None = None,
        api_key: str | None = None,
    ) -> list[dict[str, Any]]:
        """List offerings for a project from v2."""

        pid = self._project_id(project_id)
        payload = self._request_json("GET", f"{self.V2_BASE_URL}/projects/{pid}/offerings", api_key=api_key)
        return self._extract_items(payload)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=1, max=8))
    def list_entitlements(
        self,
        project_id: str | None = None,
        api_key: str | None = None,
    ) -> list[dict[str, Any]]:
        """List entitlements for a project from v2."""

        pid = self._project_id(project_id)
        payload = self._request_json("GET", f"{self.V2_BASE_URL}/projects/{pid}/entitlements", api_key=api_key)
        return self._extract_items(payload)

    # --- v1 compatibility ---

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=1, max=8))
    def get_subscriber_v1(
        self,
        app_user_id: str,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """Fetch subscriber object from v1 (/v1/subscribers/{app_user_id})."""

        uid = quote(app_user_id, safe="")
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(
                f"{self.V1_BASE_URL}/subscribers/{uid}",
                headers=self._v1_headers(api_key),
            )
        if resp.status_code == 429:
            raise ToolExecutionError(
                "revenuecat v1 rate limit",
                retry_after_seconds=_parse_retry_after(resp),
            )
        if resp.status_code >= 400:
            raise ToolExecutionError(f"revenuecat v1 subscriber failed [{resp.status_code}]: {resp.text}")
        return resp.json()

    # --- backward-compatible aliases ---

    def get_app_overview(self, api_key: str | None = None) -> dict[str, Any]:
        """Backward-compatible alias for v2 project overview metrics."""

        return self.get_project_overview(api_key=api_key)

    def get_subscriber_metrics(self, api_key: str | None = None, period: str = "7d") -> dict[str, Any]:
        """Backward-compatible alias kept for older callers."""

        _ = period
        return self.get_project_overview(api_key=api_key)

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


def _parse_retry_after(response: httpx.Response) -> int | None:
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _load_v2_endpoint_registry(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}

    raw = json.loads(path.read_text(encoding="utf-8"))
    paths = raw.get("paths", {})
    if not isinstance(paths, dict):
        return {}

    registry: dict[str, list[str]] = {}
    for path_template, methods in paths.items():
        if not isinstance(path_template, str):
            continue
        if not isinstance(methods, list):
            continue
        cleaned = [str(method).upper().strip() for method in methods if str(method).strip()]
        registry[path_template] = cleaned
    return registry
