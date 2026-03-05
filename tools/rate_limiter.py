"""Rate limit policy and retry delay calculator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class RetryPolicy:
    """Retry schedule controls for a platform."""

    retry_window_seconds: int
    base_delay_seconds: int
    max_delay_seconds: int


class RateLimitConfig:
    """Load platform rate limit policy from YAML."""

    def __init__(self, config_path: str | Path = "config/rate_limits.yaml") -> None:
        self.config_path = Path(config_path)
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        raw = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}

    def policy(self, platform: str) -> RetryPolicy:
        """Return retry policy for the given platform."""

        platform_cfg = self._data.get("platforms", {}).get(platform, {})
        return RetryPolicy(
            retry_window_seconds=int(platform_cfg.get("retry_window_seconds", 300)),
            base_delay_seconds=int(platform_cfg.get("base_delay_seconds", 5)),
            max_delay_seconds=int(platform_cfg.get("max_delay_seconds", 900)),
        )


def compute_next_attempt(
    platform: str,
    attempts: int,
    retry_after_seconds: int | None,
    config: RateLimitConfig,
) -> datetime:
    """Compute next attempt timestamp using Retry-After priority rules."""

    now = datetime.now(UTC)
    if retry_after_seconds and retry_after_seconds > 0:
        return now + timedelta(seconds=retry_after_seconds)

    policy = config.policy(platform)
    backoff = min(policy.base_delay_seconds * (2**max(attempts, 0)), policy.max_delay_seconds)
    fallback = max(backoff, policy.retry_window_seconds)
    return now + timedelta(seconds=fallback)
