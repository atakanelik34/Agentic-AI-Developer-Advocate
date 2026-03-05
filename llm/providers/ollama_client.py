"""Ollama provider adapter."""

from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from core.settings import get_settings
from core.types import LLMResponse


class OllamaProvider:
    """Local Ollama text generation adapter."""

    name = "ollama"

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
        """Generate response with local Ollama endpoint."""

        target_model = model or self.settings.ollama_model
        prompt = f"{system_prompt}\n\n{user_prompt}"
        payload = {
            "model": target_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3},
        }

        with httpx.Client(timeout=self.settings.llm_timeout_ms / 1000) as client:
            resp = client.post(f"{self.settings.ollama_base_url}/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()

        return LLMResponse(
            text=data.get("response", ""),
            provider=self.name,
            model=target_model,
            input_tokens=int(data.get("prompt_eval_count", 0)),
            output_tokens=int(data.get("eval_count", 0)),
            raw=data,
        )
