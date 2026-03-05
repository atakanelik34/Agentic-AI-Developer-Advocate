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


def test_planned_to_running_baseline_autofill() -> None:
    """Execution should auto-fill baseline when moving to running."""

    store = FakeStore()
    result = execute_planned_experiment(store=store, success_threshold=0.10)
    assert result["baseline"] == 100.0
    assert any(update.get("status") == "running" for update in store.updates)
