"""Tests for SKILL.md parser and mandatory validator integration."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from agents.community_agent import CommunityAgent
from agents.feedback_agent import FeedbackAgent
from skills.contract import SkillContractParser, SkillValidator


@dataclass(slots=True)
class _Resp:
    text: str


class FakeRouter:
    def __init__(self, text: str) -> None:
        self._text = text

    def generate(self, **kwargs):  # noqa: ANN003
        return _Resp(self._text)


class FakeStore:
    def recall(self, query: str, memory_types=None, top_k: int = 8):  # noqa: ANN001,ANN201
        return []


class FakeRevenueCatTool:
    def search_docs(self, query: str):  # noqa: ANN001,ANN201
        return [{"url": "https://docs.revenuecat.com"}]


def test_contract_parser_reads_community_and_feedback_rules() -> None:
    parser = SkillContractParser()
    markdown = """
## Skill 2: Community Response
Platform limitleri:
- X: max 123 karakter.
- GitHub: max 456 karakter.
Asla:
- Bilinmeyeni uydurma.
- 2 cumleden uzun cevap.

## Skill 3: Product Feedback
Her item formati:
- Title: max 42 karakter
- Category: `bug|feature_request|ux|docs`
- Priority: `critical|high|medium|low`
- Evidence: min 3 kaynak
"""
    contract = parser.parse_text(markdown)
    assert contract.community.max_chars_by_platform["twitter"] == 123
    assert contract.community.max_chars_by_platform["github"] == 456
    assert contract.community.max_sentences == 2
    assert "Bilinmeyeni uydurma" in contract.community.forbidden_rules
    assert contract.feedback.title_max_chars == 42
    assert contract.feedback.min_evidence_sources == 3
    assert "feature_request" in contract.feedback.categories
    assert "critical" in contract.feedback.priorities


def test_validator_sanitizes_community_reply_and_feedback_items() -> None:
    parser = SkillContractParser()
    markdown = """
## Skill 2: Community Response
Platform limitleri:
- X: max 80 karakter.
- GitHub: max 500 karakter.
Asla:
- 2 cumleden uzun cevap.

## Skill 3: Product Feedback
Her item formati:
- Title: max 20 karakter
- Category: `bug|feature_request|ux|docs`
- Priority: `critical|high|medium|low`
- Evidence: min 2 kaynak
"""
    validator = SkillValidator(parser.parse_text(markdown))

    raw_reply = "Hi. Sure. Use docs link here: https://docs.revenuecat.com. Extra sentence."
    cleaned = validator.sanitize_community_reply(platform="twitter", text=raw_reply)
    assert len(cleaned) <= 80
    assert len(_sentence_split(cleaned)) <= 2

    items = [
        {
            "title": "This title is much longer than allowed by contract rules",
            "description": "",
            "category": "invalid",
            "priority": "invalid",
            "evidence": ["https://x.com/post/1"],
        }
    ]
    normalized = validator.normalize_feedback_items(
        items,
        evidence_pool=["https://github.com/org/repo/issues/1"],
    )
    first = normalized[0]
    assert len(first["title"]) <= 20
    assert first["category"] == "feature_request"
    assert first["priority"] == "medium"
    assert len(first["evidence"]) >= 2


def test_agents_apply_skill_validator_enforcement() -> None:
    parser = SkillContractParser()
    markdown = """
## Skill 2: Community Response
Platform limitleri:
- X: max 50 karakter.
- GitHub: max 120 karakter.
Asla:
- 2 cumleden uzun cevap.

## Skill 3: Product Feedback
Her item formati:
- Title: max 15 karakter
- Category: `bug|feature_request|ux|docs`
- Priority: `critical|high|medium|low`
- Evidence: min 2 kaynak
"""
    validator = SkillValidator(parser.parse_text(markdown))

    community_agent = CommunityAgent(
        memory_store=FakeStore(),
        tools={"revenuecat": FakeRevenueCatTool()},
        skill_validator=validator,
    )
    community_agent.router = FakeRouter(
        "Hello there. First action is docs: https://docs.revenuecat.com. Third sentence.",
    )
    reply = community_agent.generate_reply(
        {
            "platform": "twitter",
            "content": "how to setup entitlement?",
            "external_id": "1",
            "author": "user1",
        }
    )
    assert len(reply) <= 50
    assert len(_sentence_split(reply)) <= 2

    feedback_agent = FeedbackAgent(
        memory_store=FakeStore(),
        tools={},
        skill_validator=validator,
    )
    raw_feedback = json.dumps(
        [
            {
                "title": "Very long feedback title that must be truncated",
                "description": "",
                "category": "nope",
                "priority": "none",
                "evidence": [],
            }
        ]
    )
    feedback_agent.router = FakeRouter(raw_feedback)
    items = feedback_agent.analyze_and_cluster(
        signals=[{"platform": "twitter", "external_id": "22", "url": "https://x.com/post/22"}],
    )
    assert len(items[0]["title"]) <= 15
    assert items[0]["category"] == "feature_request"
    assert items[0]["priority"] == "medium"
    assert len(items[0]["evidence"]) >= 2


def _sentence_split(text: str) -> list[str]:
    return [part.strip() for part in re.findall(r"[^.!?]+(?:[.!?]+|$)", text) if part.strip()]
