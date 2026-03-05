"""Provider-agnostic LLM router with fallback and cost tracking."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

import structlog
import yaml

from core.settings import get_settings
from core.types import LLMResponse
from llm.providers.gemini_client import GeminiProvider
from llm.providers.ollama_client import OllamaProvider
from llm.providers.openai_client import OpenAIProvider
from llm.providers.vertex_client import VertexProvider
from memory.store import MemoryStore


logger = structlog.get_logger(__name__)


class LLMRouter:
    """Route generation requests across provider chain with fallback."""

    def __init__(self, store: MemoryStore, pricing_file: str = "config/llm_pricing.yaml") -> None:
        self.settings = get_settings()
        self.store = store
        self.pricing = _load_yaml(pricing_file)
        self._vertex_flash_models = self._parse_flash_models(self.settings.vertex_flash_models)
        self._vertex_flash_index = 0
        self.providers = {
            "vertex": VertexProvider(),
            "openai": OpenAIProvider(),
            "gemini": GeminiProvider(),
            "ollama": OllamaProvider(),
        }
        self._probe_cache: dict[str, Any] | None = None
        self._probe_cached_at = 0.0

    def ordered_provider_names(self) -> list[str]:
        """Return configured provider fallback order."""

        return [
            self.settings.llm_primary_provider,
            self.settings.llm_secondary_provider,
            self.settings.llm_tertiary_provider,
        ]

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict] | None = None,
        response_format: dict | None = None,
        workload: str = "standard",
    ) -> LLMResponse:
        """Generate output from primary provider with automatic fallback."""

        request_id = str(uuid.uuid4())
        last_error: Exception | None = None

        for provider_name in self.ordered_provider_names():
            provider = self.providers.get(provider_name)
            if provider is None:
                continue
            selected_model = self._select_model_for_provider(provider_name=provider_name, workload=workload)
            start = time.perf_counter()
            try:
                response = provider.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    tools=tools,
                    response_format=response_format,
                    model=selected_model,
                )
                latency_ms = int((time.perf_counter() - start) * 1000)
                cost = self._estimate_cost(provider_name, response.model, response.input_tokens, response.output_tokens)
                self.store.log_provider_usage(
                    provider=provider_name,
                    model=response.model,
                    request_id=request_id,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    latency_ms=latency_ms,
                    success=True,
                    cost_estimate_usd=cost,
                )
                return response
            except Exception as exc:  # noqa: BLE001
                latency_ms = int((time.perf_counter() - start) * 1000)
                last_error = exc
                self.store.log_provider_usage(
                    provider=provider_name,
                    model=selected_model or getattr(self.settings, f"{provider_name}_model", "unknown"),
                    request_id=request_id,
                    input_tokens=0,
                    output_tokens=0,
                    latency_ms=latency_ms,
                    success=False,
                    cost_estimate_usd=0.0,
                    error=str(exc),
                )
                logger.warning("llm_provider_failed", provider=provider_name, error=str(exc), request_id=request_id)

        raise RuntimeError(f"all LLM providers failed, last_error={last_error}")

    def _select_model_for_provider(self, provider_name: str, workload: str) -> str | None:
        if provider_name != "vertex":
            return None

        normalized = workload.strip().lower()
        if normalized == "heavy":
            return self.settings.vertex_heavy_model
        if normalized in {"standard", "daily"}:
            return self._next_vertex_flash_model()
        return self.settings.vertex_model

    def _next_vertex_flash_model(self) -> str:
        if not self._vertex_flash_models:
            return self.settings.vertex_model
        model = self._vertex_flash_models[self._vertex_flash_index % len(self._vertex_flash_models)]
        self._vertex_flash_index += 1
        return model

    @staticmethod
    def _parse_flash_models(raw: str) -> list[str]:
        return [item.strip() for item in raw.split(",") if item.strip()]

    def _estimate_cost(self, provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate USD cost from configured pricing table."""

        provider_cfg = self.pricing.get("providers", {}).get(provider, {})
        model_cfg = provider_cfg.get(model, {})
        input_price = float(model_cfg.get("input_per_million_usd", 0.0))
        output_price = float(model_cfg.get("output_per_million_usd", 0.0))
        return (input_tokens / 1_000_000 * input_price) + (output_tokens / 1_000_000 * output_price)

    def probe(self, max_age_seconds: int = 60) -> dict[str, Any]:
        """Run lightweight live probe against configured providers (cached)."""

        now = time.time()
        if self._probe_cache and (now - self._probe_cached_at) <= max_age_seconds:
            return self._probe_cache

        last_error = "no providers configured"
        for provider_name in self.ordered_provider_names():
            provider = self.providers.get(provider_name)
            if provider is None:
                continue
            model = self._select_model_for_provider(provider_name=provider_name, workload="standard")
            started = time.perf_counter()
            try:
                response = provider.generate(
                    system_prompt="Health check. Reply with one word.",
                    user_prompt="pong",
                    model=model,
                )
                result = {
                    "status": "ok",
                    "provider": provider_name,
                    "model": response.model,
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                }
                self._probe_cache = result
                self._probe_cached_at = now
                return result
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)

        result = {"status": "fail", "error": last_error}
        self._probe_cache = result
        self._probe_cached_at = now
        return result


def _load_yaml(path: str) -> dict[str, Any]:
    config_path = Path(path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}
