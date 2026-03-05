"""Tests for retry-delay and runtime config helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ops.system_config import SystemConfigService
from tools.rate_limiter import RateLimitConfig, compute_next_attempt


class FakeStore:
    def __init__(self):
        self.value = "AUTO_LOW_RISK"

    def get_system_config(self, key: str) -> str | None:  # noqa: ARG002
        return self.value

    def set_system_config(self, key: str, value: str, updated_by: str) -> None:  # noqa: ARG002
        self.value = value


class FakeSettings:
    def __init__(self, force_auto_mode=None):
        self.force_auto_mode = force_auto_mode


def test_retry_after_priority() -> None:
    """Retry-After should override default retry window."""

    config = RateLimitConfig(config_path=Path("config/rate_limits.yaml"))
    now = datetime.now(UTC)
    next_attempt = compute_next_attempt("twitter", attempts=0, retry_after_seconds=120, config=config)
    assert int((next_attempt - now).total_seconds()) >= 119


def test_yaml_retry_window_fallback() -> None:
    """Missing Retry-After should use YAML retry_window_seconds."""

    config = RateLimitConfig(config_path=Path("config/rate_limits.yaml"))
    now = datetime.now(UTC)
    next_attempt = compute_next_attempt("github", attempts=0, retry_after_seconds=None, config=config)
    assert int((next_attempt - now).total_seconds()) >= 3599


def test_system_config_auto_mode() -> None:
    """SystemConfigService should persist DB-backed auto mode."""

    store = FakeStore()
    settings = FakeSettings(force_auto_mode=None)
    svc = SystemConfigService(store=store, settings=settings)

    mode = svc.set_auto_mode("DRY_RUN", updated_by="test")
    assert mode == "DRY_RUN"
    assert svc.get_auto_mode() == "DRY_RUN"
