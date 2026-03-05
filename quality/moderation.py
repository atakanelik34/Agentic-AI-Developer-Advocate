"""Independent moderation service for content safety checks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from core.settings import get_settings


logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class ModerationResult:
    """Normalized moderation output."""

    flagged: bool
    categories: list[str]
    degraded: bool = False


class ModerationService:
    """Moderation provider separated from LLM routing."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def check(self, text: str) -> ModerationResult:
        """Run moderation primary path with regex fallback."""

        provider = self.settings.moderation_provider.lower()
        if provider == "openai":
            try:
                return self._check_openai(text)
            except Exception as exc:  # noqa: BLE001
                logger.warning("moderation_primary_failed", error=str(exc))
                fallback = self._regex_fallback(text)
                fallback.degraded = True
                return fallback

        fallback = self._regex_fallback(text)
        fallback.degraded = True
        return fallback

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=0.5, min=1, max=3))
    def _check_openai(self, text: str) -> ModerationResult:
        """Call OpenAI Moderation API."""

        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY missing for moderation")

        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.settings.openai_moderation_model,
            "input": text,
        }

        with httpx.Client(timeout=self.settings.moderation_timeout_ms / 1000) as client:
            resp = client.post("https://api.openai.com/v1/moderations", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        result = data.get("results", [{}])[0]
        categories_map = result.get("categories", {})
        categories = [k for k, v in categories_map.items() if v]
        return ModerationResult(flagged=bool(result.get("flagged", False)), categories=categories)

    def _regex_fallback(self, text: str) -> ModerationResult:
        """Fallback moderation when API is unavailable."""

        patterns = {
            "hate": r"\b(hate|racist|ethnic cleansing)\b",
            "self_harm": r"\b(kill myself|self harm|suicide)\b",
            "sexual_violence": r"\b(rape|sexual assault)\b",
            "violent_threat": r"\b(i will kill|bomb you|shoot you)\b",
        }
        found: list[str] = []
        lowered = text.lower()
        for name, pattern in patterns.items():
            if re.search(pattern, lowered):
                found.append(name)

        return ModerationResult(flagged=bool(found), categories=found)
