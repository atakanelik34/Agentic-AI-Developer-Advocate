"""Quality checking pipeline for generated content."""

from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from core.settings import get_settings
from core.types import QualityCheckResult, QualityFlag
from quality.moderation import ModerationService


CODE_BLOCK_RE = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)
URL_RE = re.compile(r"https?://[^\s)]+")


@dataclass(slots=True)
class ContentDraft:
    """Input payload for quality checks."""

    title: str
    body_markdown: str
    content_type: str
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class QualityChecker:
    """Evaluate generated content against quality and safety gates."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.moderation = ModerationService()

    def evaluate(self, content: ContentDraft) -> QualityCheckResult:
        """Run all quality checks and produce pass/fail decision."""

        flags: list[QualityFlag] = []
        checks: dict[str, Any] = {}
        score = 100.0

        code_blocks = self._extract_code_blocks(content.body_markdown)
        needs_code = content.content_type in {"tutorial", "code", "blog"}
        checks["code_block_count"] = len(code_blocks)
        if needs_code and not code_blocks:
            flags.append(QualityFlag("missing_code_block", "high", "At least one code block is required."))
            score -= 35

        code_check = self._validate_code_blocks(code_blocks)
        checks["code_validation"] = code_check
        score -= code_check.get("penalty", 0)
        for err in code_check.get("flags", []):
            flags.append(QualityFlag(err["code"], err["severity"], err["message"]))

        link_check = self._validate_links(content)
        checks["link_validation"] = link_check
        score -= link_check.get("penalty", 0)
        for err in link_check.get("flags", []):
            flags.append(QualityFlag(err["code"], err["severity"], err["message"]))

        similarity = float(content.metadata.get("similarity_score", 0.0))
        checks["similarity_score"] = similarity
        if similarity >= float(self.settings.quality_similarity_threshold):
            flags.append(
                QualityFlag(
                    "duplicate_similarity",
                    "high",
                    f"Similarity {similarity:.3f} exceeds duplicate threshold.",
                )
            )
            score -= 50

        moderation_result = self.moderation.check(content.body_markdown)
        checks["moderation"] = {
            "flagged": moderation_result.flagged,
            "categories": moderation_result.categories,
            "degraded": moderation_result.degraded,
        }
        if moderation_result.flagged:
            flags.append(QualityFlag("moderation_flagged", "high", ", ".join(moderation_result.categories)))
            score -= 30
        if moderation_result.degraded:
            flags.append(
                QualityFlag(
                    "moderation_degraded",
                    "medium",
                    "Moderation API unavailable; regex fallback applied.",
                )
            )
            score -= 5

        high_flags = [f for f in flags if f.severity == "high"]
        score = max(score, 0.0)
        passed = score >= float(self.settings.quality_min_score) and not high_flags

        return QualityCheckResult(passed=passed, score=score, flags=flags, checks=checks)

    def _extract_code_blocks(self, markdown: str) -> list[tuple[str, str]]:
        """Extract fenced code blocks from markdown."""

        found: list[tuple[str, str]] = []
        for match in CODE_BLOCK_RE.finditer(markdown):
            lang = (match.group(1) or "").strip().lower()
            code = match.group(2)
            found.append((lang, code))
        return found

    def _validate_code_blocks(self, blocks: list[tuple[str, str]]) -> dict[str, Any]:
        """Run language-aware validation for code snippets."""

        flags: list[dict[str, str]] = []
        penalty = 0

        for lang, code in blocks:
            if lang in {"python", "py"}:
                ok, msg = self._validate_python(code)
                if not ok:
                    flags.append({"code": "python_snippet_invalid", "severity": "medium", "message": msg})
                    penalty += 10
            if lang in {"javascript", "js", "typescript", "ts"}:
                ok, msg = self._validate_js(code)
                if not ok:
                    flags.append({"code": "js_snippet_invalid", "severity": "medium", "message": msg})
                    penalty += 10

        return {"penalty": penalty, "flags": flags}

    def _validate_python(self, code: str) -> tuple[bool, str]:
        """Validate Python snippets using py_compile and ruff."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "snippet.py"
            file_path.write_text(code, encoding="utf-8")

            compile_cmd = ["python", "-m", "py_compile", str(file_path)]
            comp = subprocess.run(compile_cmd, capture_output=True, text=True, check=False)
            if comp.returncode != 0:
                return False, f"py_compile failed: {comp.stderr.strip()}"

            ruff_cmd = ["ruff", "check", str(file_path)]
            ruff_run = subprocess.run(ruff_cmd, capture_output=True, text=True, check=False)
            if ruff_run.returncode != 0:
                return False, f"ruff failed: {ruff_run.stdout.strip() or ruff_run.stderr.strip()}"

        return True, "ok"

    def _validate_js(self, code: str) -> tuple[bool, str]:
        """Validate JS/TS snippets with node --check."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "snippet.js"
            file_path.write_text(code, encoding="utf-8")
            cmd = ["node", "--check", str(file_path)]
            run = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if run.returncode != 0:
                return False, f"node --check failed: {run.stderr.strip()}"
        return True, "ok"

    def _validate_links(self, content: ContentDraft) -> dict[str, Any]:
        """Validate source links and enforce RevenueCat official source presence."""

        flags: list[dict[str, str]] = []
        penalty = 0

        links = URL_RE.findall(content.body_markdown)
        requires_source = content.content_type in {"blog", "tutorial"}
        revenuecat_links = [link for link in links if "revenuecat.com" in link]

        if requires_source and not revenuecat_links:
            flags.append(
                {
                    "code": "missing_revenuecat_source",
                    "severity": "high",
                    "message": "At least one official RevenueCat link is required.",
                }
            )
            penalty += 25

        invalid_links = 0
        for link in links:
            if not self._check_url(link):
                invalid_links += 1

        if invalid_links > 0:
            flags.append(
                {
                    "code": "invalid_links",
                    "severity": "medium",
                    "message": f"{invalid_links} links failed verification.",
                }
            )
            penalty += min(15, invalid_links * 3)

        return {
            "total_links": len(links),
            "revenuecat_links": len(revenuecat_links),
            "invalid_links": invalid_links,
            "penalty": penalty,
            "flags": flags,
        }

    def _check_url(self, url: str) -> bool:
        """Verify link is reachable with lightweight HTTP request."""

        try:
            with httpx.Client(timeout=4.0, follow_redirects=True) as client:
                response = client.head(url)
                if response.status_code in {405, 501}:
                    response = client.get(url)
                return response.status_code < 400
        except Exception:  # noqa: BLE001
            return False
