"""SKILL.md contract parsing and runtime validation helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any


_SKILL_MD_PATH = Path(__file__).resolve().parent.parent / "SKILL.md"


@dataclass(slots=True)
class CommunitySkillRules:
    """Parsed rules for community responses."""

    max_chars_by_platform: dict[str, int] = field(
        default_factory=lambda: {"twitter": 240, "github": 500}
    )
    max_sentences: int = 3
    forbidden_rules: list[str] = field(default_factory=list)

    def max_chars_for(self, platform: str) -> int:
        normalized = _normalize_platform(platform)
        return self.max_chars_by_platform.get(normalized, 500)


@dataclass(slots=True)
class FeedbackSkillRules:
    """Parsed rules for structured product feedback."""

    title_max_chars: int = 60
    categories: set[str] = field(default_factory=lambda: {"bug", "feature_request", "ux", "docs"})
    priorities: set[str] = field(
        default_factory=lambda: {"critical", "high", "medium", "low"}
    )
    min_evidence_sources: int = 2


@dataclass(slots=True)
class SkillContract:
    """Resolved SKILL.md contract used at runtime."""

    community: CommunitySkillRules = field(default_factory=CommunitySkillRules)
    feedback: FeedbackSkillRules = field(default_factory=FeedbackSkillRules)


class SkillContractParser:
    """Parse a markdown skill contract file into typed runtime rules."""

    def __init__(self, skill_md_path: Path | None = None) -> None:
        self.skill_md_path = skill_md_path or _SKILL_MD_PATH

    def parse(self) -> SkillContract:
        text = self.skill_md_path.read_text(encoding="utf-8")
        return self.parse_text(text)

    def parse_text(self, markdown: str) -> SkillContract:
        contract = SkillContract()

        community = _extract_skill_section(markdown, 2)
        if community:
            contract.community = self._parse_community_rules(community)

        feedback = _extract_skill_section(markdown, 3)
        if feedback:
            contract.feedback = self._parse_feedback_rules(feedback)

        return contract

    def _parse_community_rules(self, section: str) -> CommunitySkillRules:
        rules = CommunitySkillRules()
        for platform, chars in re.findall(
            r"-\s*([A-Za-z]+)\s*:\s*max\s*(\d+)\s*karakter",
            section,
            flags=re.IGNORECASE,
        ):
            rules.max_chars_by_platform[_normalize_platform(platform)] = int(chars)

        match = re.search(r"-\s*(\d+)\s*cumleden\s+uzun\s+cevap", section, flags=re.IGNORECASE)
        if match:
            rules.max_sentences = int(match.group(1))

        asla_block = _extract_block_after_heading(section, "Asla:")
        if asla_block:
            rules.forbidden_rules = _extract_list_items(asla_block)

        return rules

    def _parse_feedback_rules(self, section: str) -> FeedbackSkillRules:
        rules = FeedbackSkillRules()

        title_match = re.search(r"Title:\s*max\s*(\d+)\s*karakter", section, flags=re.IGNORECASE)
        if title_match:
            rules.title_max_chars = int(title_match.group(1))

        category_match = re.search(r"Category:\s*`([^`]+)`", section, flags=re.IGNORECASE)
        if category_match:
            parsed = {value.strip() for value in category_match.group(1).split("|") if value.strip()}
            if parsed:
                rules.categories = parsed

        priority_match = re.search(r"Priority:\s*`([^`]+)`", section, flags=re.IGNORECASE)
        if priority_match:
            parsed = {value.strip() for value in priority_match.group(1).split("|") if value.strip()}
            if parsed:
                rules.priorities = parsed

        evidence_match = re.search(r"Evidence:\s*min\s*(\d+)\s*kaynak", section, flags=re.IGNORECASE)
        if evidence_match:
            rules.min_evidence_sources = int(evidence_match.group(1))

        return rules


class SkillValidator:
    """Mandatory runtime validator for skill-constrained outputs."""

    def __init__(self, contract: SkillContract) -> None:
        self.contract = contract

    def sanitize_community_reply(self, platform: str, text: str) -> str:
        """Enforce sentence and character limits for community replies."""

        cleaned = _normalize_whitespace(text)
        cleaned = _drop_empty_opening_sentence(cleaned)
        cleaned = _limit_sentence_count(cleaned, self.contract.community.max_sentences)

        char_limit = self.contract.community.max_chars_for(platform)
        if len(cleaned) > char_limit:
            cleaned = cleaned[:char_limit].rstrip()
        return cleaned

    def normalize_feedback_items(
        self,
        items: list[dict[str, Any]],
        evidence_pool: list[str],
    ) -> list[dict[str, Any]]:
        """Normalize feedback payloads into strict contract shape."""

        normalized: list[dict[str, Any]] = []
        unique_pool = _unique_non_empty_strings(evidence_pool)
        for raw in items:
            if not isinstance(raw, dict):
                continue

            title = str(raw.get("title") or "Untitled feedback").strip()
            if not title:
                title = "Untitled feedback"
            title = title[: self.contract.feedback.title_max_chars].strip()

            description = str(raw.get("description") or "").strip()
            if not description:
                description = f"Observed repeated signal around: {title}."

            category = str(raw.get("category") or "feature_request").strip().lower()
            if category not in self.contract.feedback.categories:
                category = "feature_request"

            priority = str(raw.get("priority") or "medium").strip().lower()
            if priority not in self.contract.feedback.priorities:
                priority = "medium"

            evidence = _normalize_evidence(raw.get("evidence"))
            evidence = _unique_non_empty_strings(evidence)
            evidence = _fill_evidence(
                evidence=evidence,
                evidence_pool=unique_pool,
                minimum=self.contract.feedback.min_evidence_sources,
            )

            normalized.append(
                {
                    "title": title,
                    "description": description,
                    "category": category,
                    "priority": priority,
                    "evidence": evidence,
                }
            )

            if len(normalized) >= 5:
                break

        if not normalized:
            fallback_evidence = _fill_evidence(
                evidence=[],
                evidence_pool=unique_pool,
                minimum=self.contract.feedback.min_evidence_sources,
            )
            normalized.append(
                {
                    "title": "Docs clarity around agent workflows",
                    "description": "Users ask for clearer examples for agentic app monetization setup.",
                    "category": "docs",
                    "priority": "medium",
                    "evidence": fallback_evidence,
                }
            )

        return normalized


@lru_cache(maxsize=1)
def load_skill_contract() -> SkillContract:
    """Parse and cache the default SKILL.md contract."""

    return SkillContractParser().parse()


def load_skill_validator() -> SkillValidator:
    """Build a validator bound to the cached default contract."""

    return SkillValidator(contract=load_skill_contract())


def build_signal_evidence_pool(signals: list[dict[str, Any]]) -> list[str]:
    """Extract evidence candidates from raw community signals."""

    values: list[str] = []
    for signal in signals:
        url = str(signal.get("url") or "").strip()
        if url:
            values.append(url)
            continue

        platform = str(signal.get("platform") or "signal").strip().lower()
        external_id = str(signal.get("external_id") or "").strip()
        if external_id:
            values.append(f"{platform}:{external_id}")
    return _unique_non_empty_strings(values)


def _extract_skill_section(markdown: str, skill_index: int) -> str:
    marker = f"## Skill {skill_index}:"
    start = markdown.find(marker)
    if start < 0:
        return ""

    end = markdown.find("\n## Skill ", start + len(marker))
    if end < 0:
        return markdown[start:].strip()
    return markdown[start:end].strip()


def _extract_block_after_heading(section: str, heading: str) -> str:
    start = section.find(heading)
    if start < 0:
        return ""

    after = section[start + len(heading) :]
    lines: list[str] = []
    for line in after.splitlines():
        stripped = line.strip()
        if not stripped:
            if lines:
                break
            continue
        if stripped.startswith("## "):
            break
        lines.append(line)
    return "\n".join(lines)


def _extract_list_items(block: str) -> list[str]:
    items: list[str] = []
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:].strip().rstrip("."))
    return items


def _normalize_platform(platform: str) -> str:
    value = platform.strip().lower()
    if value in {"x", "twitter"}:
        return "twitter"
    return value


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _split_sentences(text: str) -> list[str]:
    parts = re.findall(r"[^.!?]+(?:[.!?]+|$)", text)
    return [part.strip() for part in parts if part.strip()]


def _drop_empty_opening_sentence(text: str) -> str:
    sentences = _split_sentences(text)
    if not sentences:
        return ""
    first = sentences[0].lower()
    short_and_empty = len(first.split()) <= 3 and "http" not in first and len(first) <= 18
    if short_and_empty and len(sentences) > 1:
        sentences = sentences[1:]
    return " ".join(sentences)


def _limit_sentence_count(text: str, max_sentences: int) -> str:
    sentences = _split_sentences(text)
    if len(sentences) <= max_sentences:
        return text.strip()
    return " ".join(sentences[:max_sentences]).strip()


def _normalize_evidence(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _unique_non_empty_strings(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _fill_evidence(evidence: list[str], evidence_pool: list[str], minimum: int) -> list[str]:
    result = list(evidence)
    seen = set(result)

    for candidate in evidence_pool:
        if len(result) >= minimum:
            break
        if candidate in seen:
            continue
        result.append(candidate)
        seen.add(candidate)

    while len(result) < minimum:
        result.append(f"internal:signal:{len(result) + 1}")

    return result
