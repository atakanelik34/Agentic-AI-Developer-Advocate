"""Product feedback collection and submission agent."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from agents.base_agent import BaseAgent


class FeedbackAgent(BaseAgent):
    """Aggregates community signals into structured product feedback."""

    def collect_signals(self) -> list[dict[str, Any]]:
        """Collect raw feedback signals from interactions and public channels."""

        signals = self.memory_store.get_recent_interactions(days=7)
        twitter_hits = self.tools["twitter"].search_recent(
            "(revenuecat bug OR revenuecat feature OR revenuecat wish) -is:retweet",
            max_results=30,
        )
        signals.extend(
            {
                "platform": "twitter",
                "external_id": str(hit["id"]),
                "content": hit["text"],
                "url": f"https://x.com/i/web/status/{hit['id']}",
            }
            for hit in twitter_hits
        )

        github_repo = self.settings.github_repo
        if github_repo and "/" in github_repo:
            owner, repo = github_repo.split("/", 1)
            issues = self.tools["github"].list_recent_issues(owner=owner, repo=repo, per_page=20)
            for issue in issues:
                signals.append(
                    {
                        "platform": "github",
                        "external_id": str(issue["id"]),
                        "content": issue.get("title", "") + "\n" + (issue.get("body") or ""),
                        "url": issue.get("html_url", ""),
                    }
                )

        return signals

    def analyze_and_cluster(self, signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Cluster and structure signals into 3-5 feedback items."""

        prompt_template = Path("prompts/feedback_analyzer.txt").read_text(encoding="utf-8")
        payload = {
            "instructions": prompt_template,
            "signals": signals[:120],
            "min_items": 3,
            "max_items": 5,
        }
        response = self.router.generate(
            system_prompt=self.build_system_prompt(),
            user_prompt=json.dumps(payload, ensure_ascii=True),
            response_format={"type": "json_object"},
            workload="heavy",
        )

        parsed = _parse_possible_list(response.text)
        if parsed:
            return parsed[:5]

        return [
            {
                "title": "Docs clarity around agent workflows",
                "description": "Users ask for clearer examples for agentic app monetization setup.",
                "category": "docs",
                "priority": "medium",
                "evidence": [],
            }
        ]

    def submit_feedback(self, feedback_items: list[dict[str, Any]]) -> list[str]:
        """Persist feedback and notify Slack webhook."""

        created_ids: list[str] = []
        for item in feedback_items:
            fid = self.memory_store.insert_feedback_item(
                title=item.get("title", "Untitled Feedback"),
                description=item.get("description", ""),
                category=item.get("category", "feature_request"),
                priority=item.get("priority", "medium"),
                evidence=item.get("evidence", []),
                submitted_to_team=True,
            )
            created_ids.append(str(fid))

        if self.settings.slack_webhook_url:
            summary = {
                "text": "RevenueCat Agent Product Feedback",
                "attachments": [
                    {
                        "color": "#2eb886",
                        "title": f"{item.get('priority', 'medium').upper()} - {item.get('title', '')}",
                        "text": item.get("description", ""),
                    }
                    for item in feedback_items
                ],
            }
            with httpx.Client(timeout=10.0) as client:
                client.post(self.settings.slack_webhook_url, json=summary)

        return created_ids

    def run_feedback_cycle(self) -> dict[str, Any]:
        """Run full feedback loop and return summary payload."""

        signals = self.collect_signals()
        clusters = self.analyze_and_cluster(signals)
        ids = self.submit_feedback(clusters)
        return {"signals": len(signals), "submitted": len(ids), "ids": ids}


def _parse_possible_list(text: str) -> list[dict[str, Any]]:
    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return []

    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        maybe_items = parsed.get("items")
        if isinstance(maybe_items, list):
            return [item for item in maybe_items if isinstance(item, dict)]
    return []
