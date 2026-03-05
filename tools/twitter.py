"""X (Twitter) API v2 client."""

from __future__ import annotations

from typing import Any

import tweepy
from tenacity import retry, stop_after_attempt, wait_exponential

from core.settings import get_settings
from tools.errors import ToolExecutionError


class TwitterTool:
    """Client wrapper for X API search and posting operations."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._verified_username: str | None = None
        if not self.settings.twitter_bearer_token:
            self.client = None
            return
        self.client = tweepy.Client(
            bearer_token=self.settings.twitter_bearer_token,
            consumer_key=self.settings.twitter_api_key,
            consumer_secret=self.settings.twitter_api_secret,
            access_token=self.settings.twitter_access_token,
            access_token_secret=self.settings.twitter_access_token_secret,
            wait_on_rate_limit=False,
        )

    def _ensure_client(self) -> tweepy.Client:
        if self.client is None:
            raise ToolExecutionError("twitter client not configured")
        return self.client

    def _ensure_expected_identity(self) -> None:
        """Validate write identity against expected username before posting."""

        expected = (self.settings.twitter_expected_username or "").strip().lstrip("@")
        if not expected:
            return

        if self._verified_username is not None:
            if self._verified_username.lower() != expected.lower():
                raise ToolExecutionError(
                    f"twitter auth mismatch: expected @{expected}, got @{self._verified_username}",
                )
            return

        client = self._ensure_client()
        try:
            me = client.get_me(user_auth=True, user_fields=["username"])
        except tweepy.TooManyRequests as exc:
            retry_after = int(getattr(exc.response, "headers", {}).get("Retry-After", "0") or 0)
            raise ToolExecutionError("twitter identity check rate limit", retry_after_seconds=retry_after) from exc
        except tweepy.TweepyException as exc:
            raise ToolExecutionError(f"twitter identity check failed: {exc}") from exc

        username = ""
        if getattr(me, "data", None) is not None:
            username = str(getattr(me.data, "username", "") or "").strip()
        if not username:
            raise ToolExecutionError("twitter identity check failed: username not found")

        self._verified_username = username
        if username.lower() != expected.lower():
            raise ToolExecutionError(f"twitter auth mismatch: expected @{expected}, got @{username}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=1, max=8))
    def search_recent(self, query: str, max_results: int = 20) -> list[dict[str, Any]]:
        """Search tweets from the last 7 days."""

        client = self._ensure_client()
        try:
            response = client.search_recent_tweets(
                query=query,
                max_results=max(10, min(max_results, 100)),
                tweet_fields=["created_at", "author_id", "public_metrics"],
            )
        except tweepy.TooManyRequests as exc:
            retry_after = int(getattr(exc.response, "headers", {}).get("Retry-After", "0") or 0)
            raise ToolExecutionError("twitter rate limit", retry_after_seconds=retry_after) from exc
        except tweepy.TweepyException as exc:
            raise ToolExecutionError(f"twitter search_recent failed: {exc}") from exc

        tweets = response.data or []
        return [
            {
                "id": t.id,
                "text": t.text,
                "author_id": t.author_id,
                "metrics": t.public_metrics,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tweets
        ]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=1, max=8))
    def post_tweet(self, text: str, reply_to: str | None = None) -> str:
        """Publish single tweet and return tweet id."""

        client = self._ensure_client()
        self._ensure_expected_identity()
        kwargs: dict[str, Any] = {"text": text[:280]}
        if reply_to:
            kwargs["in_reply_to_tweet_id"] = reply_to
        try:
            response = client.create_tweet(**kwargs)
        except tweepy.TooManyRequests as exc:
            retry_after = int(getattr(exc.response, "headers", {}).get("Retry-After", "0") or 0)
            raise ToolExecutionError("twitter rate limit", retry_after_seconds=retry_after) from exc
        except tweepy.TweepyException as exc:
            raise ToolExecutionError(f"twitter post_tweet failed: {exc}") from exc

        tweet_id = response.data.get("id") if response.data else None
        if not tweet_id:
            raise ToolExecutionError("twitter post_tweet missing id")
        return str(tweet_id)

    def post_thread(self, tweets: list[str]) -> list[str]:
        """Post a thread and return ordered tweet IDs."""

        ids: list[str] = []
        reply_to: str | None = None
        for text in tweets:
            tweet_id = self.post_tweet(text=text, reply_to=reply_to)
            ids.append(tweet_id)
            reply_to = tweet_id
        return ids

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=0.5, min=1, max=4))
    def get_tweet_metrics(self, tweet_id: str) -> dict[str, Any]:
        """Get metrics for a tweet."""

        client = self._ensure_client()
        try:
            response = client.get_tweet(tweet_id, tweet_fields=["public_metrics"])
        except tweepy.TweepyException as exc:
            raise ToolExecutionError(f"twitter get_tweet_metrics failed: {exc}") from exc
        data = response.data
        if data is None:
            return {"impression": 0, "like": 0, "retweet": 0, "reply": 0}
        metrics = data.public_metrics or {}
        return {
            "impression": metrics.get("impression_count", 0),
            "like": metrics.get("like_count", 0),
            "retweet": metrics.get("retweet_count", 0),
            "reply": metrics.get("reply_count", 0),
        }
