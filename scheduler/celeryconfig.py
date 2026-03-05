"""Celery configuration."""

from __future__ import annotations

from celery.schedules import crontab

from core.settings import get_settings


settings = get_settings()

broker_url = settings.redis_url
result_backend = settings.redis_url
timezone = "UTC"
enable_utc = True

task_serializer = "json"
result_serializer = "json"
accept_content = ["json"]

beat_schedule = {
    "content-pipeline": {
        "task": "scheduler.tasks.run_content_pipeline",
        "schedule": crontab(hour=10, minute=0, day_of_week="2,4"),
    },
    "community-monitor": {
        "task": "scheduler.tasks.run_community_monitor",
        "schedule": crontab(minute=0),
    },
    "feedback-collection": {
        "task": "scheduler.tasks.run_feedback_collection",
        "schedule": crontab(hour=14, minute=0, day_of_week="5"),
    },
    "weekly-report": {
        "task": "scheduler.tasks.run_weekly_report",
        "schedule": crontab(hour=9, minute=0, day_of_week="1"),
    },
    "growth-planning": {
        "task": "scheduler.tasks.run_growth_experiment_planning",
        "schedule": crontab(hour=11, minute=0, day_of_week="1"),
    },
    "growth-execution": {
        "task": "scheduler.tasks.run_growth_experiment_execution",
        "schedule": crontab(hour=13, minute=0, day_of_week="1"),
    },
    "db-backup": {
        "task": "scheduler.tasks.run_db_backup",
        "schedule": crontab(hour=2, minute=30),
    },
    "restore-smoke": {
        "task": "scheduler.tasks.run_restore_smoke_test",
        "schedule": crontab(hour=3, minute=0, day_of_week="0"),
    },
    "outbox-dispatch": {
        "task": "scheduler.tasks.dispatch_outbox",
        "schedule": crontab(minute="*/1"),
    },
}
