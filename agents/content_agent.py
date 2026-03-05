"""Content generation and publish queue agent."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog

from agents.base_agent import BaseAgent
from quality.checker import ContentDraft, QualityChecker


logger = structlog.get_logger(__name__)


class ContentAgent(BaseAgent):
    """Owns the content pipeline from ideation to queued publication."""

    TASK_TYPE = "content"

    def __init__(self, memory_store, tools: dict[str, Any]) -> None:  # type: ignore[no-untyped-def]
        super().__init__(memory_store=memory_store, tools=tools)
        self.quality_checker = QualityChecker()

    def generate_content_idea(self) -> dict[str, Any]:
        """Generate a content idea while avoiding duplicates from recent posts."""

        changelog = self.tools["revenuecat"].fetch_changelog()
        mentions = self.tools["twitter"].search_recent("revenuecat -is:retweet", max_results=20)
        recent = self.memory_store.get_recent_publications(days=7)

        prompt = {
            "changelog": changelog[:5],
            "mentions": mentions[:10],
            "recent_titles": [item["title"] for item in recent],
            "instruction": "Return JSON: {title, type, angle, target_audience}",
        }

        response = self.router.generate(
            system_prompt=self.build_system_prompt(
                task_description="content idea generation from changelog and community mentions",
            ),
            user_prompt=json.dumps(prompt, ensure_ascii=True),
            response_format={"type": "json_object"},
            workload="standard",
        )
        parsed = _parse_json_response(response.text, default={})
        title = parsed.get("title", "RevenueCat Agent Playbook")
        recent_titles = {item["title"].strip().lower() for item in recent}
        if title.strip().lower() in recent_titles:
            parsed["title"] = f"{title} (New Angle)"
        return parsed

    def write_content(self, idea: dict[str, Any]) -> dict[str, Any]:
        """Write a full markdown post with code examples."""

        prompt_template = Path("prompts/content_writer.txt").read_text(encoding="utf-8")
        docs_ctx = self.tools["revenuecat"].search_docs(idea.get("title", "RevenueCat"))

        payload = {
            "instructions": prompt_template,
            "idea": idea,
            "docs_context": docs_ctx[:3],
            "word_range": "800-1500",
        }

        response = self.router.generate(
            system_prompt=self.build_system_prompt(
                task_description=f"write {idea.get('type', 'blog')} content about {idea.get('title', '')}",
            ),
            user_prompt=json.dumps(payload, ensure_ascii=True),
            response_format={"type": "json_object"},
            workload="heavy",
        )
        content = _parse_json_response(response.text, default={})
        body = content.get("body_markdown", "")
        if "```" not in body:
            body += (
                "\n\n```python\n"
                "from revenuecat import Client\n"
                "client = Client(api_key=\"YOUR_API_KEY\")\n"
                "print(\"RevenueCat SDK initialized\")\n"
                "```\n"
            )
        return {
            "title": content.get("title", idea.get("title", "RevenueCat Guide")),
            "body_markdown": body,
            "tags": content.get("tags", ["revenuecat", "agentic-ai"]),
            "content_type": content.get("content_type", idea.get("type", "blog")),
        }

    def run_content_cycle(self) -> dict[str, Any]:
        """Execute full content cycle and queue publish/promote outbox events."""

        idea = self.generate_content_idea()
        content = self.write_content(idea)

        embedding = self.embeddings.embed(content["body_markdown"])
        platform = "hashnode" if content["content_type"] in {"blog", "tutorial", "case_study"} else "github"

        draft = self.memory_store.create_content_draft(
            title=content["title"],
            body=content["body_markdown"],
            content_type=content["content_type"],
            platform=platform,
            tags=content["tags"],
            embedding=embedding,
        )
        content_id = draft["id"]

        similar = self.memory_store.find_similar_content(embedding, days=90, limit=1)
        similarity_score = float(similar[0]["similarity"]) if similar else 0.0
        dedupe_source_id: UUID | None = similar[0]["id"] if similar and similarity_score >= 0.92 else None

        quality_input = ContentDraft(
            title=content["title"],
            body_markdown=content["body_markdown"],
            content_type=content["content_type"],
            tags=content["tags"],
            metadata={"similarity_score": similarity_score},
        )
        quality = self.quality_checker.evaluate(quality_input)

        self.memory_store.mark_quality_result(
            content_id=content_id,
            score=quality.score,
            flags=[asdict(flag) for flag in quality.flags],
            similarity_score=similarity_score,
            dedupe_source_id=dedupe_source_id,
            passed=quality.passed,
        )

        if not quality.passed:
            return {
                "idea": idea,
                "content_id": str(content_id),
                "status": "quality_failed",
                "quality_score": quality.score,
                "quality_flags": [asdict(flag) for flag in quality.flags],
            }

        idempotency_key = f"publish:{content_id}"
        outbox_id = self.memory_store.create_outbox_event(
            event_type="publish_content",
            payload={
                "content_id": str(content_id),
                "platform": platform,
                "title": content["title"],
                "body_markdown": content["body_markdown"],
                "tags": content["tags"],
                "created_at": datetime.now(UTC).isoformat(),
            },
            idempotency_key=idempotency_key,
            platform=platform,
            max_attempts=5,
        )
        self.memory_store.link_content_outbox(content_id=content_id, outbox_event_id=outbox_id)

        return {
            "idea": idea,
            "content_id": str(content_id),
            "status": "queued",
            "outbox_event_id": str(outbox_id),
            "quality_score": quality.score,
        }


def _parse_json_response(text: str, default: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default
