"""Tests for RevenueCatTool v2/v1 request shaping."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from tools.revenuecat import RevenueCatTool
from tools.errors import ToolExecutionError


def _make_tool() -> RevenueCatTool:
    tool = RevenueCatTool()
    tool.settings = SimpleNamespace(
        revenuecat_api_key="sk_test_key",
        revenuecat_v1_api_key="sk_v1_test_key",
        revenuecat_project_id="proj_test_123",
    )
    return tool


def test_headers_use_bearer_prefix() -> None:
    tool = _make_tool()
    headers = tool._headers()
    assert headers["Authorization"] == "Bearer sk_test_key"
    assert headers["Content-Type"] == "application/json"


def test_project_overview_uses_metrics_overview_path() -> None:
    tool = _make_tool()
    calls: dict[str, Any] = {}

    def fake_request(method: str, path: str, **kwargs):  # noqa: ANN003,ANN201
        calls["method"] = method
        calls["path"] = path
        calls["kwargs"] = kwargs
        return {"ok": True}

    tool._request_json = fake_request  # type: ignore[method-assign]
    tool.get_project_overview()

    assert calls["method"] == "GET"
    assert calls["path"].endswith("/v2/projects/proj_test_123/metrics/overview")


def test_subscriber_v1_encodes_app_user_id() -> None:
    tool = _make_tool()
    captured: dict[str, Any] = {}

    class FakeResponse:
        status_code = 200
        text = "{}"

        @staticmethod
        def json():  # noqa: ANN201
            return {"subscriber": {}}

    class FakeClient:
        def __init__(self, timeout: float):  # noqa: ARG002
            pass

        def __enter__(self):  # noqa: ANN201
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001, ANN201
            return False

        def get(self, url: str, headers: dict[str, str]):  # noqa: ANN201
            captured["url"] = url
            captured["headers"] = headers
            return FakeResponse()

    import tools.revenuecat as revenuecat_module

    original = revenuecat_module.httpx.Client
    revenuecat_module.httpx.Client = FakeClient  # type: ignore[assignment]
    try:
        tool.get_subscriber_v1("user/with space+chars")
    finally:
        revenuecat_module.httpx.Client = original  # type: ignore[assignment]

    assert captured["url"].endswith("/v1/subscribers/user%2Fwith%20space%2Bchars")
    assert captured["headers"]["Authorization"] == "Bearer sk_v1_test_key"


def test_list_v2_endpoints_has_registry_entries() -> None:
    tool = _make_tool()
    endpoints = tool.list_v2_endpoints()
    assert len(endpoints) >= 60
    assert any(item["path"] == "/projects/{project_id}/metrics/overview" for item in endpoints)


def test_request_v2_resolves_template_and_project_id() -> None:
    tool = _make_tool()
    calls: dict[str, Any] = {}

    def fake_request(method: str, path: str, **kwargs):  # noqa: ANN003,ANN201
        calls["method"] = method
        calls["path"] = path
        calls["kwargs"] = kwargs
        return {"ok": True}

    tool._request_json = fake_request  # type: ignore[method-assign]
    tool.request_v2(
        "GET",
        "/projects/{project_id}/customers/{customer_id}",
        path_params={"customer_id": "cust/with space"},
    )

    assert calls["method"] == "GET"
    assert calls["path"].endswith("/v2/projects/proj_test_123/customers/cust%2Fwith%20space")


def test_request_v2_rejects_unknown_path_template() -> None:
    tool = _make_tool()
    with pytest.raises(ToolExecutionError):
        tool.request_v2("GET", "/projects/{project_id}/overview")
