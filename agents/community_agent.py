"""Community monitoring and response queue agent."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.base_agent import BaseAgent
from skills.contract import SkillValidator, load_skill_validator


class CommunityAgent(BaseAgent):
    """Scans community channels and queues contextual replies."""

    TASK_TYPE = "community"

    def __init__(
        self,
        memory_store,
        tools: dict[str, Any],
        *,
        skill_validator: SkillValidator | None = None,
    ) -> None:  # type: ignore[no-untyped-def]
        super().__init__(memory_store=memory_store, tools=tools)
        self.skill_validator = skill_validator or load_skill_validator()

    def scan_mentions(self) -> list[dict[str, Any]]:
        """Collect mentions from X and GitHub and filter previously handled records."""

        mentions: list[dict[str, Any]] = []

        twitter_hits = self.tools["twitter"].search_recent("revenuecat -is:retweet", max_results=30)
        for hit in twitter_hits:
            mentions.append(
                {
                    "platform": "twitter",
                    "external_id": str(hit["id"]),
                    "content": hit["text"],
                    "author": str(hit.get("author_id") or "unknown"),
                    "url": f"https://x.com/i/web/status/{hit['id']}",
                }
            )

        github_repo = self.settings.github_repo
        if github_repo and "/" in github_repo:
            owner, repo = github_repo.split("/", 1)
            issues = self.tools["github"].list_recent_issues(owner=owner, repo=repo, per_page=20)
            for issue in issues:
                mentions.append(
                    {
                        "platform": "github",
                        "external_id": str(issue["id"]),
                        "content": issue.get("title", "") + "\n" + (issue.get("body") or ""),
                        "author": issue.get("user", {}).get("login", "unknown"),
                        "url": issue.get("html_url", ""),
                        "issue_number": issue.get("number"),
                        "owner": owner,
                        "repo": repo,
                    }
                )

        return mentions

    def generate_reply(self, mention: dict[str, Any]) -> str:
        """Generate concise channel-appropriate reply text."""

        prompt_template = Path("prompts/community_responder.txt").read_text(encoding="utf-8")
        docs_ctx = self.tools["revenuecat"].search_docs(" ".join(mention["content"].split()[:12]))

        payload = {
            "instructions": prompt_template,
            "platform": mention["platform"],
            "mention": mention,
            "docs": docs_ctx[:2],
        }

        response = self.router.generate(
            system_prompt=self.build_system_prompt(
                task_description=f"community reply generation for {mention['platform']} mention",
            ),
            user_prompt=json.dumps(payload, ensure_ascii=True),
            workload="standard",
        )
        return self.skill_validator.sanitize_community_reply(
            platform=mention["platform"],
            text=response.text,
        )

    def run_community_cycle(self) -> dict[str, int]:
        """Queue community reply outbox events respecting per-user daily caps."""

        processed = 0
        queued = 0

        for mention in self.scan_mentions():
            processed += 1
            author = mention.get("author", "unknown")
            existing_replies = self.memory_store.count_author_replies_today(mention["platform"], author)
            if existing_replies >= 3:
                continue

            reply = self.generate_reply(mention)
            event_payload = {"mention": mention, "reply": reply}
            idempotency_key = f"reply:{mention['platform']}:{mention['external_id']}"
            event_id = self.memory_store.create_outbox_event(
                event_type="reply_community",
                payload=event_payload,
                idempotency_key=idempotency_key,
                platform=mention["platform"],
                max_attempts=5,
            )
            self.memory_store.insert_community_interaction(
                platform=mention["platform"],
                external_id=mention["external_id"],
                content=mention["content"],
                interaction_type="reply_queued",
                author_handle=author,
                our_reply=None,
            )
            queued += 1

        return {"processed": processed, "queued": queued}
