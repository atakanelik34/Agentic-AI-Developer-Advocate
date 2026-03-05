"""Tests for AGENT/SKILL-aware context assembly."""

from __future__ import annotations

from memory.context_builder import ContextBuilder


class FakeStore:
    def recall(self, query: str, memory_types=None, top_k: int = 8):  # noqa: ANN001,ANN201
        return [
            {"memory_type": "PERFORMANCE", "content": "tutorial format performed well"},
            {"memory_type": "NEGATIVE", "content": "avoid duplicate headlines"},
        ]


def test_context_builder_injects_identity_and_skill() -> None:
    """Context should include AGENT identity and the skill section for task type."""

    builder = ContextBuilder(store=FakeStore())  # type: ignore[arg-type]
    prompt = builder.build(task_type="content", task_description="write tutorial")
    assert "Agent Identity" in prompt
    assert "Skill 1: Technical Content Writing" in prompt


def test_context_builder_injects_memories() -> None:
    """Relevant memories should be appended to final prompt."""

    builder = ContextBuilder(store=FakeStore())  # type: ignore[arg-type]
    prompt = builder.build(task_type="community", task_description="reply mention")
    assert "Relevant Learned Signals" in prompt
    assert "tutorial format performed well" in prompt

