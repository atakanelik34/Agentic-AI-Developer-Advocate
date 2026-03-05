"""Shared datatypes used across modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class LLMResponse:
    """Unified result schema for LLM providers."""

    text: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolResult:
    """Standardized tool execution output."""

    ok: bool
    data: Any
    error: str | None = None


@dataclass(slots=True)
class QualityFlag:
    """Issue detected by the quality pipeline."""

    code: str
    severity: str
    message: str


@dataclass(slots=True)
class QualityCheckResult:
    """Quality checker output."""

    passed: bool
    score: float
    flags: list[QualityFlag]
    checks: dict[str, Any]
