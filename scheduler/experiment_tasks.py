"""Growth experiment planning and execution helpers."""

from __future__ import annotations

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


def execute_planned_experiment(
    store: MemoryStore,
    success_threshold: float,
    tools: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Move planned experiment to running and compute result from live signals when possible."""

    return execute_planned_experiment_with_tools(
        store=store,
        success_threshold=success_threshold,
        tools=tools,
    )


def execute_planned_experiment_with_tools(
    *,
    store: MemoryStore,
    success_threshold: float,
    tools: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Move planned experiment to running and compute measurable result."""

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

    target_metric = str(experiment.get("target_metric") or "impressions")
    result_value = _measure_experiment_result(store=store, tools=tools, target_metric=target_metric)
    threshold = baseline * (1 + success_threshold)
    success = result_value >= threshold if baseline > 0 else result_value > 0
    notes = f"live_measurement target_metric={target_metric} result={result_value} threshold={threshold}"

    store.update_growth_experiment(
        experiment_id=experiment["id"],
        status="completed",
        result_value=result_value,
        success=success,
        notes=notes,
    )

    return {
        "experiment_id": str(experiment["id"]),
        "baseline": baseline,
        "result": result_value,
        "success": success,
    }


def _measure_experiment_result(
    *,
    store: MemoryStore,
    tools: dict[str, Any] | None,
    target_metric: str,
) -> float:
    metric = target_metric.lower().strip()

    if metric in {"impressions", "total_reach"} and tools and tools.get("twitter"):
        return _measure_twitter_thread_impressions(store=store, tools=tools)

    reports = store.get_recent_weekly_reports(weeks=1)
    if reports:
        latest = reports[0]
        mapping = {
            "content_published": "content_published",
            "community_interactions": "community_interactions",
            "feedback_submitted": "feedback_submitted",
            "impressions": "total_reach",
            "total_reach": "total_reach",
        }
        column = mapping.get(metric)
        if column:
            value = latest.get(column)
            if value is not None:
                return float(value)
    return 0.0


def _measure_twitter_thread_impressions(*, store: MemoryStore, tools: dict[str, Any]) -> float:
    interactions = store.get_recent_interactions(days=7)
    tweet_ids: list[str] = []
    seen: set[str] = set()

    for item in interactions:
        if item.get("platform") != "twitter":
            continue
        if item.get("interaction_type") != "thread":
            continue
        external_id = str(item.get("external_id") or "").strip()
        if not external_id or external_id in seen:
            continue
        seen.add(external_id)
        tweet_ids.append(external_id)

    total = 0.0
    twitter_tool = tools["twitter"]
    for tweet_id in tweet_ids[:20]:
        try:
            metrics = twitter_tool.get_tweet_metrics(tweet_id)
        except Exception:  # noqa: BLE001
            continue
        total += float(metrics.get("impression", 0) or 0)

    return total
