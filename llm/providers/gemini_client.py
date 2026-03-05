"""Gemini provider adapter."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from core.settings import get_settings
from core.types import LLMResponse


class GeminiProvider:
    """Google Gemini generateContent adapter."""

    name = "gemini"

    def __init__(self) -> None:
        self.settings = get_settings()

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=0.5, min=1, max=4))
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict] | None = None,
        response_format: dict | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        """Generate response with Gemini API."""

        if not self.settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY not set")

        target_model = model or self.settings.gemini_model
        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{target_model}:generateContent"
        )
        params = {"key": self.settings.gemini_api_key}

        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": 0.3},
        }
        if response_format:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        with httpx.Client(timeout=self.settings.llm_timeout_ms / 1000) as client:
            resp = client.post(endpoint, params=params, json=payload)
            resp.raise_for_status()
            data = resp.json()

        candidates = data.get("candidates", [])
        parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
        text = "".join(p.get("text", "") for p in parts)
        usage = data.get("usageMetadata", {})
        return LLMResponse(
            text=text,
            provider=self.name,
            model=target_model,
            input_tokens=int(usage.get("promptTokenCount", 0)),
            output_tokens=int(usage.get("candidatesTokenCount", 0)),
            raw=data,
        )
