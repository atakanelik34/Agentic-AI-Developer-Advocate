"""Tests for LLM router health probe behavior."""

from __future__ import annotations

from core.types import LLMResponse
from llm.router import LLMRouter


class FakeStore:
    def log_provider_usage(self, **kwargs):  # noqa: ANN003, ANN201
        return None


class FailingProvider:
    def generate(self, **kwargs):  # noqa: ANN003, ANN201
        raise RuntimeError("provider down")


class OkProvider:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, **kwargs):  # noqa: ANN003, ANN201
        self.calls += 1
        return LLMResponse(text="pong", provider="openai", model="gpt-test", input_tokens=1, output_tokens=1)


def test_probe_returns_ok_and_uses_cache() -> None:
    router = LLMRouter(store=FakeStore())  # type: ignore[arg-type]
    ok = OkProvider()
    router.providers = {
        "vertex": FailingProvider(),
        "openai": ok,
        "gemini": FailingProvider(),
        "ollama": FailingProvider(),
    }

    first = router.probe(max_age_seconds=60)
    second = router.probe(max_age_seconds=60)

    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert ok.calls == 1
