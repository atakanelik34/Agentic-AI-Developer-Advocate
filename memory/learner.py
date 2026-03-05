"""Learning helpers that write reusable knowledge into semantic memory."""

from __future__ import annotations

import structlog

from memory.store import MemoryStore


logger = structlog.get_logger(__name__)


class Learner:
    """Persist structured learnings after pipeline outcomes."""

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def learn_from_publish(
        self,
        *,
        content_type: str,
        topic: str,
        engagement_rate: float,
        impressions: int,
        baseline_engagement: float,
        published_at: str,
    ) -> None:
        """Store post-publication performance signal."""

        is_high = engagement_rate > baseline_engagement * 1.5 if baseline_engagement > 0 else impressions > 0
        is_low = engagement_rate < baseline_engagement * 0.5 if baseline_engagement > 0 else impressions == 0

        status = "HIGH" if is_high else "LOW" if is_low else "NORMAL"
        summary = (
            f"type={content_type} topic={topic} published_at={published_at} "
            f"engagement={engagement_rate:.4f} baseline={baseline_engagement:.4f} "
            f"impressions={impressions} result={status}"
        )
        importance = 8 if (is_high or is_low) else 5
        self.store.remember(summary, memory_type="PERFORMANCE", importance=importance)

        if is_low:
            self.store.remember(
                f"avoid_pattern content_type={content_type} topic={topic}",
                memory_type="NEGATIVE",
                importance=9,
            )
            logger.info("learned_negative_publish_pattern", content_type=content_type, topic=topic)

    def learn_from_community(self, *, question_pattern: str, frequency: int) -> None:
        """Persist repeated community questions."""

        if frequency < 3:
            return
        self.store.remember(
            f"repeated_question pattern={question_pattern} count={frequency}",
            memory_type="COMMUNITY",
            importance=7,
        )

    def learn_from_experiment(self, *, hypothesis: str, method: str, success: bool, notes: str) -> None:
        """Persist experiment outcomes."""

        verdict = "SUCCESS" if success else "FAIL"
        self.store.remember(
            f"experiment_result verdict={verdict} method={method} hypothesis={hypothesis[:180]} notes={notes[:180]}",
            memory_type="EXPERIMENT",
            importance=8,
        )

    def learn_factual(self, *, fact: str, source: str = "") -> None:
        """Persist source-grounded factual knowledge."""

        payload = fact if not source else f"{fact} (source={source})"
        self.store.remember(payload, memory_type="FACTUAL", importance=6)

