"""Tests for semantic memory behavior and interaction dedupe."""

from __future__ import annotations

from dataclasses import dataclass

from memory.embeddings import EmbeddingService


@dataclass
class InMemoryInteractions:
    seen: set[tuple[str, str]]

    def insert(self, platform: str, external_id: str) -> bool:
        key = (platform, external_id)
        if key in self.seen:
            return False
        self.seen.add(key)
        return True


def test_semantic_search_returns_relevant() -> None:
    """Cosine similarity should rank semantically close vectors higher."""

    svc = EmbeddingService()
    a = svc.embed("How to reduce churn with RevenueCat cohorts")
    b = svc.embed("RevenueCat cohorts can help reduce subscription churn")
    c = svc.embed("Best pasta recipe with tomato sauce")

    sim_ab = svc.cosine_similarity(a, b)
    sim_ac = svc.cosine_similarity(a, c)
    assert sim_ab > sim_ac


def test_no_duplicate_interaction() -> None:
    """Duplicate platform/external_id insertions should be prevented."""

    table = InMemoryInteractions(seen=set())
    assert table.insert("twitter", "123") is True
    assert table.insert("twitter", "123") is False
