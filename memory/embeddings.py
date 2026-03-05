"""Embedding generation utilities."""

from __future__ import annotations

import hashlib
import math
from typing import Any

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from core.settings import get_settings


logger = structlog.get_logger(__name__)
EMBEDDING_DIM = 1536


class EmbeddingService:
    """Create embeddings using OpenAI API with deterministic fallback."""

    def __init__(self) -> None:
        self.settings = get_settings()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=1, max=8))
    def embed(self, text: str) -> list[float]:
        """Return a 1536-dimensional embedding for text."""

        if self.settings.openai_api_key:
            try:
                return self._embed_openai(text)
            except Exception as exc:  # noqa: BLE001
                logger.warning("openai_embedding_failed", error=str(exc))

        return self._embed_deterministic(text)

    def cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""

        dot = sum(x * y for x, y in zip(a, b, strict=False))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _embed_openai(self, text: str) -> list[float]:
        """Call OpenAI embeddings endpoint."""

        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": "text-embedding-3-small",
            "input": text,
        }

        with httpx.Client(timeout=12.0) as client:
            response = client.post("https://api.openai.com/v1/embeddings", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        return data["data"][0]["embedding"]

    def _embed_deterministic(self, text: str) -> list[float]:
        """Generate deterministic pseudo-embedding when external API is unavailable."""

        digest = hashlib.sha256(text.encode("utf-8")).digest()
        floats: list[float] = []
        for i in range(EMBEDDING_DIM):
            byte = digest[i % len(digest)]
            floats.append((byte / 255.0) * 2.0 - 1.0)

        norm = math.sqrt(sum(v * v for v in floats))
        if norm == 0:
            return [0.0] * EMBEDDING_DIM
        return [v / norm for v in floats]
