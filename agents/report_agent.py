"""Weekly reporting agent."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from agents.base_agent import BaseAgent


class ReportAgent(BaseAgent):
    """Generates weekly KPI reports and stores snapshots."""

    TASK_TYPE = "report"

    def generate_weekly_report(self, week_start: date | None = None) -> dict[str, Any]:
        """Build weekly report markdown and persist metrics."""

        if week_start is None:
            now = datetime.now(UTC).date()
            week_start = now - timedelta(days=now.weekday())

        summary = self.memory_store.compute_weekly_summary(week_start)
        prompt_template = Path("prompts/report_generator.txt").read_text(encoding="utf-8")
        payload = {
            "instructions": prompt_template,
            "summary": summary,
            "targets": {"content": 2, "interaction": 50, "feedback": 3},
        }
        response = self.router.generate(
            system_prompt=self.build_system_prompt(
                task_description=f"weekly report generation for week_start={week_start}",
            ),
            user_prompt=json.dumps(payload, ensure_ascii=True),
            workload="heavy",
        )
        report_markdown = response.text

        summary["raw_report"] = report_markdown
        self.memory_store.upsert_weekly_metrics(week_start, summary)

        if self.settings.slack_webhook_url:
            with httpx.Client(timeout=10.0) as client:
                client.post(self.settings.slack_webhook_url, json={"text": report_markdown[:3500]})

        return {"week_start": str(week_start), "report": report_markdown, "summary": summary}
