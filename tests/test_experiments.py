"""Tests for growth experiment baseline automation."""

from __future__ import annotations

from uuid import uuid4

from scheduler.experiment_tasks import execute_planned_experiment


class FakeStore:
    def __init__(self):
        self.experiment = {"id": uuid4(), "target_metric": "impressions", "status": "planned"}
        self.updates = []

    def get_planned_experiment(self):
        return self.experiment

    def calculate_metric_baseline(self, target_metric: str) -> float:  # noqa: ARG002
        return 100.0

    def update_growth_experiment(self, experiment_id, **kwargs):  # noqa: ANN001,ANN003
        self.updates.append(kwargs)

    def get_recent_weekly_reports(self, weeks: int = 1):  # noqa: ARG002, ANN201
        return []

    def get_recent_interactions(self, days: int = 7):  # noqa: ARG002, ANN201
        return []


def test_planned_to_running_baseline_autofill() -> None:
    """Execution should auto-fill baseline when moving to running."""

    store = FakeStore()
    result = execute_planned_experiment(store=store, success_threshold=0.10)
    assert result["baseline"] == 100.0
    assert any(update.get("status") == "running" for update in store.updates)


def test_experiment_uses_live_twitter_metrics_when_available() -> None:
    """Execution should use live thread impression metrics when twitter tool is provided."""

    class MetricsStore(FakeStore):
        def get_recent_interactions(self, days: int = 7):  # noqa: ARG002, ANN201
            return [
                {
                    "platform": "twitter",
                    "interaction_type": "thread",
                    "external_id": "tweet_1",
                },
                {
                    "platform": "twitter",
                    "interaction_type": "thread",
                    "external_id": "tweet_2",
                },
            ]

    class FakeTwitterTool:
        def get_tweet_metrics(self, tweet_id: str):  # noqa: ANN201
            return {"impression": 80 if tweet_id == "tweet_1" else 70}

    store = MetricsStore()
    result = execute_planned_experiment(
        store=store,
        success_threshold=0.10,
        tools={"twitter": FakeTwitterTool()},
    )
    assert result["result"] == 150.0
    assert result["success"] is True
