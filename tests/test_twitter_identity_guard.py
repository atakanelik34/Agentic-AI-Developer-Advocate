"""Tests for Twitter write-identity guard."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tools.errors import ToolExecutionError
from tools.twitter import TwitterTool


class FakeClient:
    def __init__(self, username: str) -> None:
        self._username = username
        self.create_tweet_calls = 0

    def get_me(self, user_auth: bool = True, user_fields=None):  # noqa: ANN001, ANN201, ARG002
        return SimpleNamespace(data=SimpleNamespace(username=self._username))

    def create_tweet(self, **kwargs):  # noqa: ANN003, ANN201
        self.create_tweet_calls += 1
        return SimpleNamespace(data={"id": "12345"})


def _make_tool(expected_username: str, actual_username: str) -> TwitterTool:
    tool = TwitterTool.__new__(TwitterTool)
    tool.settings = SimpleNamespace(twitter_expected_username=expected_username)
    tool.client = FakeClient(actual_username)
    tool._verified_username = None
    return tool


def test_identity_guard_blocks_mismatch() -> None:
    tool = _make_tool(expected_username="KairosAgentX", actual_username="WrongAccount")
    with pytest.raises(ToolExecutionError):
        tool._ensure_expected_identity()


def test_identity_guard_allows_expected_account_and_caches() -> None:
    tool = _make_tool(expected_username="KairosAgentX", actual_username="KairosAgentX")
    tool._ensure_expected_identity()
    assert tool._verified_username == "KairosAgentX"
    tweet_id = tool.post_tweet("hello from kairos")
    assert tweet_id == "12345"
    assert tool.client.create_tweet_calls == 1

