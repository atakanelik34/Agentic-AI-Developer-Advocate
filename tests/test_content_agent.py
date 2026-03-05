"""Tests for content agent pipeline behavior."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from agents.content_agent import ContentAgent
from core.types import QualityCheckResult


@dataclass(slots=True)
class _Resp:
    text: str


class FakeRouter:
    def __init__(self, text: str) -> None:
        self._text = text

    def generate(self, **kwargs):  # noqa: ANN003
        return _Resp(self._text)


class FakeEmbeddings:
    def embed(self, text: str) -> list[float]:
        return [0.1] * 1536


class FakeStore:
    def __init__(self) -> None:
        self.drafts: list[dict] = []
        self.outbox: list[dict] = []

    def get_recent_publications(self, days: int = 7):
        return [{"title": "Same Title", "url": "https://example.com"}]

    def get_recent_memories(self, limit: int = 20):
        return []

    def recall(self, query: str, memory_types=None, top_k: int = 5):  # noqa: ANN001,ANN201
        return []

    def remember(self, content: str, memory_type: str, importance: int = 5):  # noqa: ANN001,ANN201
        return None

    def create_content_draft(self, **kwargs):
        draft = {"id": uuid4(), **kwargs}
        self.drafts.append(draft)
        return {"id": draft["id"], "status": "draft", "title": kwargs["title"], "published_at": None}

    def find_similar_content(self, embedding, days=90, limit=1):  # noqa: ANN001,ANN201
        return []

    def mark_quality_result(self, **kwargs):  # noqa: ANN003
        return None

    def create_outbox_event(self, **kwargs):
        eid = uuid4()
        self.outbox.append({"id": eid, **kwargs})
        return eid

    def link_content_outbox(self, content_id, outbox_event_id):  # noqa: ANN001
        return None


class FakeRevenueCatTool:
    def fetch_changelog(self):
        return [{"title": "c1"}]

    def search_docs(self, query: str):
        return [{"url": "https://docs.revenuecat.com"}]


class FakeTwitterTool:
    def search_recent(self, query: str, max_results: int = 20):
        return [{"id": "1", "text": "Ask about RevenueCat", "author_id": "42"}]


def _make_agent(router_text: str) -> ContentAgent:
    store = FakeStore()
    tools = {
        "revenuecat": FakeRevenueCatTool(),
        "twitter": FakeTwitterTool(),
    }
    agent = ContentAgent(memory_store=store, tools=tools)
    agent.router = FakeRouter(router_text)
    agent.embeddings = FakeEmbeddings()
    return agent


def test_generate_idea_no_duplicate() -> None:
    """Agent should avoid returning exact same title from recent history."""

    agent = _make_agent('{"title":"Same Title","type":"blog","angle":"A","target_audience":"dev"}')
    idea = agent.generate_content_idea()
    assert idea["title"] != "Same Title"


def test_write_content_has_code() -> None:
    """Written content should include at least one code fence."""

    agent = _make_agent('{"title":"Guide","body_markdown":"text only","tags":["r"],"content_type":"blog"}')
    content = agent.write_content({"title": "Guide", "type": "blog"})
    assert "```" in content["body_markdown"]


def test_publish_saves_to_db() -> None:
    """Content cycle should create draft row and queue outbox event."""

    agent = _make_agent('{"title":"Guide","body_markdown":"See https://docs.revenuecat.com\n```python\nprint(1)\n```","tags":["r"],"content_type":"blog"}')

    class AlwaysPassChecker:
        def evaluate(self, draft):  # noqa: ANN001,ANN201
            return QualityCheckResult(passed=True, score=90, flags=[], checks={})

    agent.quality_checker = AlwaysPassChecker()
    result = agent.run_content_cycle()

    assert result["status"] == "queued"
    assert len(agent.memory_store.drafts) == 1
    assert len(agent.memory_store.outbox) == 1
