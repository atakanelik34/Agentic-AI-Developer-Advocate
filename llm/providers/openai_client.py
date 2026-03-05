"""OpenAI provider adapter."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from core.settings import get_settings
from core.types import LLMResponse


class OpenAIProvider:
    """OpenAI chat completions client."""

    name = "openai"

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
        """Generate response with OpenAI API."""

        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY not set")

        payload: dict[str, Any] = {
            "model": model or self.settings.openai_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
        }
        if tools:
            payload["tools"] = tools
        if response_format:
            payload["response_format"] = response_format

        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=self.settings.llm_timeout_ms / 1000) as client:
            resp = client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return LLMResponse(
            text=text,
            provider=self.name,
            model=model or self.settings.openai_model,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            raw=data,
        )
