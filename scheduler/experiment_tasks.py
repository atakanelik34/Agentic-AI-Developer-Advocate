"""Growth experiment planning and execution helpers."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

from agents.report_agent import ReportAgent
from memory.store import MemoryStore


def plan_next_experiment(report_agent: ReportAgent, store: MemoryStore) -> dict[str, Any]:
    """Create a planned experiment based on weekly report and last 4-week trend."""

    reports = store.get_recent_weekly_reports(weeks=4)
    latest = reports[0] if reports else None
    prev = reports[1] if len(reports) > 1 else None

    trend = "inconclusive"
    if latest and prev:
        latest_reach = int(latest.get("total_reach") or 0)
        prev_reach = int(prev.get("total_reach") or 0)
        if latest_reach > prev_reach:
            trend = "success"
        elif latest_reach < prev_reach:
            trend = "fail"

    hypothesis = {
        "success": "Tutorial-first content structure can increase agent developer reach by 10%.",
        "fail": "Switching to short thread hooks plus CTA may recover reach in one week.",
        "inconclusive": "A consistent two-post cadence with clearer code snippets will improve reach.",
    }[trend]

    method = {
        "success": "thread_format",
        "fail": "cross_post",
        "inconclusive": "programmatic_seo",
    }[trend]

    today = datetime.now(UTC).date()
    week_start = today - timedelta(days=today.weekday())

    experiment_id = store.create_growth_experiment(
        week_start=week_start,
        hypothesis=hypothesis,
        method=method,
        target_metric="impressions",
        status="planned",
        notes=f"planned_from_weekly_report trend={trend}",
    )

    return {
        "experiment_id": str(experiment_id),
        "week_start": str(week_start),
        "trend": trend,
        "hypothesis": hypothesis,
        "method": method,
    }


def execute_planned_experiment(store: MemoryStore, success_threshold: float) -> dict[str, Any]:
    """Move planned experiment to running and auto-fill baseline metric."""

    experiment = store.get_planned_experiment()
    if not experiment:
        return {"status": "noop", "reason": "no planned experiment"}

    baseline = store.calculate_metric_baseline(experiment.get("target_metric", "impressions"))
    store.update_growth_experiment(
        experiment_id=experiment["id"],
        status="running",
        baseline_value=baseline,
        notes=f"baseline_auto_filled={baseline}",
    )

    # Placeholder result in MVP; expected to be replaced by measurement pipeline.
    simulated_result = baseline * 1.12 if baseline > 0 else 10.0
    success = simulated_result >= baseline * (1 + success_threshold) if baseline > 0 else True

    store.update_growth_experiment(
        experiment_id=experiment["id"],
        status="completed",
        result_value=simulated_result,
        success=success,
        notes=f"simulated_result={simulated_result}",
    )

    return {
        "experiment_id": str(experiment["id"]),
        "baseline": baseline,
        "result": simulated_result,
        "success": success,
    }
