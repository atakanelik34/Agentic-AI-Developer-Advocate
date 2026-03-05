"""Vertex AI Gemini provider adapter using VM service-account auth."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from core.settings import get_settings
from core.types import LLMResponse

class VertexProvider:
    """Vertex AI generateContent adapter with metadata-server token auth."""

    name = "vertex"

    def __init__(self) -> None:
        self.settings = get_settings()
        self._cached_token: str | None = None
        self._token_expires_at: datetime | None = None

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=0.5, min=1, max=4))
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict] | None = None,
        response_format: dict | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        """Generate response with Vertex AI Gemini."""

        project_id = self.settings.vertex_project_id
        location = self.settings.vertex_location
        target_model = model or self.settings.vertex_model

        if not project_id:
            raise RuntimeError("VERTEX_PROJECT_ID not set")

        data = self._call_generate(
            project_id=project_id,
            location=location,
            model=target_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format=response_format,
        )

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

    def _call_generate(
        self,
        project_id: str,
        location: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_format: dict | None = None,
    ) -> dict[str, Any]:
        endpoint = (
            f"https://{location}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/"
            f"{location}/publishers/google/models/{model}:generateContent"
        )
        token = self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": 0.3},
        }
        if response_format:
            payload["generationConfig"]["responseMimeType"] = "application/json"
        with httpx.Client(timeout=self.settings.llm_timeout_ms / 1000) as client:
            resp = client.post(endpoint, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()

    def _get_access_token(self) -> str:
        if self.settings.vertex_access_token:
            return self.settings.vertex_access_token

        now = datetime.now(UTC)
        if self._cached_token and self._token_expires_at and now < self._token_expires_at:
            return self._cached_token

        metadata_url = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
        headers = {"Metadata-Flavor": "Google"}

        with httpx.Client(timeout=4.0) as client:
            resp = client.get(metadata_url, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        token = data.get("access_token")
        expires_in = int(data.get("expires_in", 300))
        if not token:
            raise RuntimeError("failed to fetch access token from metadata server")

        # Refresh one minute early to avoid edge-expiry.
        self._cached_token = token
        self._token_expires_at = now + timedelta(seconds=max(60, expires_in - 60))
        return token
