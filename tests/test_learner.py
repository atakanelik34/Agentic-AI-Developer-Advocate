"""Tests for memory learner helpers."""

from __future__ import annotations

from memory.learner import Learner


class FakeStore:
    def __init__(self) -> None:
        self.items: list[tuple[str, str, int]] = []

    def remember(self, content: str, memory_type: str, importance: int = 5):  # noqa: ANN001,ANN201
        self.items.append((memory_type, content, importance))
        return None


def test_learner_records_negative_pattern_for_low_publish() -> None:
    """Low-performing publish should write both PERFORMANCE and NEGATIVE memories."""

    store = FakeStore()
    learner = Learner(store=store)  # type: ignore[arg-type]
    learner.learn_from_publish(
        content_type="tutorial",
        topic="paywall copy",
        engagement_rate=0.01,
        impressions=100,
        baseline_engagement=0.20,
        published_at="2026-03-05T00:00:00Z",
    )
    types = [t for t, _, _ in store.items]
    assert "PERFORMANCE" in types
    assert "NEGATIVE" in types


def test_learner_repeated_community_pattern_threshold() -> None:
    """Community learn should persist only when frequency is >= 3."""

    store = FakeStore()
    learner = Learner(store=store)  # type: ignore[arg-type]
    learner.learn_from_community(question_pattern="pricing API", frequency=2)
    assert len(store.items) == 0
    learner.learn_from_community(question_pattern="pricing API", frequency=4)
    assert len(store.items) == 1
    assert store.items[0][0] == "COMMUNITY"

