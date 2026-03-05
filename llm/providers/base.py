"""Provider interfaces."""

from __future__ import annotations

from typing import Protocol

from core.types import LLMResponse


class LLMProvider(Protocol):
    """Contract implemented by each model provider adapter."""

    name: str

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict] | None = None,
        response_format: dict | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        """Generate assistant output with unified schema."""
