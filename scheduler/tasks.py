"""Celery tasks for content, community, feedback, reporting, and ops."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
import structlog
from celery import Celery

from core.settings import get_settings
from memory.store import MemoryStore
from ops.backup.backup_runner import run_backup
from ops.backup.restore_smoke import run_restore_smoke
from ops.system_config import SystemConfigService
from runtime import build_runtime
from scheduler.experiment_tasks import execute_planned_experiment, plan_next_experiment
from tools.errors import ToolExecutionError
from tools.rate_limiter import RateLimitConfig, compute_next_attempt


logger = structlog.get_logger(__name__)
settings = get_settings()

celery_app = Celery("revenuecat_agent")
celery_app.config_from_object("scheduler.celeryconfig")


def _runtime() -> dict[str, Any]:
    return build_runtime()


def _create_job(job_type: str, payload: dict[str, Any], job_run_id: str | None = None) -> tuple[MemoryStore, UUID]:
    store = MemoryStore()
    if job_run_id:
        job_id = UUID(job_run_id)
    else:
        job_id = store.create_job_run(job_type=job_type, payload=payload)
    return store, job_id


def _current_auto_mode(store: MemoryStore) -> str:
    cfg = SystemConfigService(store=store, settings=settings)
    return cfg.get_auto_mode()


@celery_app.task(name="scheduler.tasks.run_content_pipeline")
def run_content_pipeline(
    force: bool = False,
    campaign_id: str | None = None,
    job_run_id: str | None = None,
) -> dict[str, Any]:
    """Queue content publication from generated draft."""

    store, job_id = _create_job("content_pipeline", {"force": force, "campaign_id": campaign_id}, job_run_id)
    try:
        result = _runtime()["agents"]["content"].run_content_cycle()  # type: ignore[index]
        store.update_job_run(job_id, status="success", result=result)
        return {"job_id": str(job_id), **result}
    except Exception as exc:  # noqa: BLE001
        store.update_job_run(job_id, status="failed", error=str(exc))
        raise


@celery_app.task(name="scheduler.tasks.run_community_monitor")
def run_community_monitor(limit: int = 50, job_run_id: str | None = None) -> dict[str, Any]:
    """Scan channels and queue community replies."""

    store, job_id = _create_job("community_monitor", {"limit": limit}, job_run_id)
    try:
        result = _runtime()["agents"]["community"].run_community_cycle()  # type: ignore[index]
        store.update_job_run(job_id, status="success", result=result)
        return {"job_id": str(job_id), **result}
    except Exception as exc:  # noqa: BLE001
        store.update_job_run(job_id, status="failed", error=str(exc))
        raise


@celery_app.task(name="scheduler.tasks.run_feedback_collection")
def run_feedback_collection(job_run_id: str | None = None) -> dict[str, Any]:
    """Collect and submit product feedback items."""

    store, job_id = _create_job("feedback_collection", {}, job_run_id)
    try:
        result = _runtime()["agents"]["feedback"].run_feedback_cycle()  # type: ignore[index]
        store.update_job_run(job_id, status="success", result=result)
        return {"job_id": str(job_id), **result}
    except Exception as exc:  # noqa: BLE001
        store.update_job_run(job_id, status="failed", error=str(exc))
        raise


@celery_app.task(name="scheduler.tasks.run_weekly_report")
def run_weekly_report(week_start: str | None = None, job_run_id: str | None = None) -> dict[str, Any]:
    """Generate weekly KPI report and send to Slack."""

    store, job_id = _create_job("weekly_report", {"week_start": week_start}, job_run_id)
    try:
        parsed_week = datetime.fromisoformat(week_start).date() if week_start else None
        result = _runtime()["agents"]["report"].generate_weekly_report(week_start=parsed_week)  # type: ignore[index]
        store.update_job_run(job_id, status="success", result=result)
        return {"job_id": str(job_id), **result}
    except Exception as exc:  # noqa: BLE001
        store.update_job_run(job_id, status="failed", error=str(exc))
        raise


@celery_app.task(name="scheduler.tasks.run_growth_experiment_planning")
def run_growth_experiment_planning(job_run_id: str | None = None) -> dict[str, Any]:
    """Plan weekly growth experiment from latest report outcomes."""

    store, job_id = _create_job("growth_experiment_planning", {}, job_run_id)
    try:
        runtime = _runtime()
        report_agent = runtime["agents"]["report"]
        result = plan_next_experiment(report_agent=report_agent, store=store)  # type: ignore[arg-type]
        store.update_job_run(job_id, status="success", result=result)
        return {"job_id": str(job_id), **result}
    except Exception as exc:  # noqa: BLE001
        store.update_job_run(job_id, status="failed", error=str(exc))
        raise


@celery_app.task(name="scheduler.tasks.run_growth_experiment_execution")
def run_growth_experiment_execution(
    experiment_id: str | None = None,
    job_run_id: str | None = None,
) -> dict[str, Any]:
    """Start planned experiment and auto-compute baseline."""

    store, job_id = _create_job(
        "growth_experiment_execution",
        {"experiment_id": experiment_id},
        job_run_id,
    )
    try:
        tools = _runtime()["tools"]
        result = execute_planned_experiment(
            store=store,
            success_threshold=settings.experiment_success_threshold,
            tools=tools,
        )
        store.update_job_run(job_id, status="success", result=result)
        return {"job_id": str(job_id), **result}
    except Exception as exc:  # noqa: BLE001
        store.update_job_run(job_id, status="failed", error=str(exc))
        raise


@celery_app.task(name="scheduler.tasks.run_db_backup")
def run_db_backup(job_run_id: str | None = None) -> dict[str, Any]:
    """Run DB backup and upload artifacts."""

    store, job_id = _create_job("db_backup", {}, job_run_id)
    try:
        result = run_backup()
        store.update_job_run(job_id, status="success", result=result)
        return {"job_id": str(job_id), **result}
    except Exception as exc:  # noqa: BLE001
        _notify_slack(f"SEV-2 backup failed: {exc}")
        store.update_job_run(job_id, status="failed", error=str(exc))
        raise


@celery_app.task(name="scheduler.tasks.run_restore_smoke_test")
def run_restore_smoke_test(job_run_id: str | None = None) -> dict[str, Any]:
    """Run restore smoke test against latest backup."""

    store, job_id = _create_job("restore_smoke", {}, job_run_id)
    try:
        result = run_restore_smoke()
        store.update_job_run(job_id, status="success", result=result)
        return {"job_id": str(job_id), **result}
    except Exception as exc:  # noqa: BLE001
        _notify_slack(f"SEV-2 restore smoke test failed: {exc}")
        store.update_job_run(job_id, status="failed", error=str(exc))
        raise


@celery_app.task(name="scheduler.tasks.dispatch_outbox")
def dispatch_outbox(batch_size: int = 20) -> dict[str, int]:
    """Dispatch due outbox events with retry/backoff handling."""

    runtime = _runtime()
    store: MemoryStore = runtime["store"]
    tools = runtime["tools"]
    rate_cfg = RateLimitConfig()
    events = store.fetch_due_outbox_events(limit=batch_size)
    processed = 0
    failed = 0

    for event in events:
        processed += 1
        event_id = event["id"]
        platform = event.get("platform") or "hashnode"
        attempts = int(event.get("attempts", 0))
        max_attempts = int(event.get("max_attempts", 5))

        try:
            auto_mode = _current_auto_mode(store)
            if auto_mode == "DRY_RUN" and event["event_type"] in {
                "publish_content",
                "promote_content",
                "reply_community",
            }:
                store.mark_outbox_done(event_id)
                continue

            if event["event_type"] == "publish_content":
                _handle_publish_event(store=store, tools=tools, event=event)
                store.mark_outbox_done(event_id)
                continue

            if event["event_type"] == "promote_content":
                _handle_promote_event(store=store, tools=tools, event=event)
                store.mark_outbox_done(event_id)
                continue

            if event["event_type"] == "reply_community":
                _handle_reply_event(store=store, tools=tools, event=event)
                store.mark_outbox_done(event_id)
                continue

            store.mark_outbox_done(event_id)
        except ToolExecutionError as exc:
            failed += 1
            if attempts + 1 >= max_attempts:
                store.mark_outbox_dead_letter(event_id, str(exc))
                payload = event.get("payload", {})
                content_id = payload.get("content_id")
                if content_id:
                    store.mark_content_failed(UUID(content_id))
                _notify_slack(f"Outbox dead-letter: {event['event_type']} {event_id} error={exc}")
                continue

            next_attempt = compute_next_attempt(
                platform=platform,
                attempts=attempts,
                retry_after_seconds=exc.retry_after_seconds,
                config=rate_cfg,
            )
            store.mark_outbox_retry(event_id=event_id, error=str(exc), next_attempt_at=next_attempt)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            if attempts + 1 >= max_attempts:
                store.mark_outbox_dead_letter(event_id, str(exc))
                _notify_slack(f"Outbox dead-letter: {event['event_type']} {event_id} error={exc}")
                continue
            next_attempt = compute_next_attempt(
                platform=platform,
                attempts=attempts,
                retry_after_seconds=None,
                config=rate_cfg,
            )
            store.mark_outbox_retry(event_id=event_id, error=str(exc), next_attempt_at=next_attempt)

    return {"processed": processed, "failed": failed}


def _handle_publish_event(store: MemoryStore, tools: dict[str, Any], event: dict[str, Any]) -> None:
    payload = event["payload"]
    content_id = UUID(payload["content_id"])
    platform = payload["platform"]

    if platform == "hashnode":
        result = tools["hashnode"].create_post(
            title=payload["title"],
            body=payload["body_markdown"],
            tags=payload.get("tags", []),
        )
        platform_id = result["id"]
        url = result["url"]
    else:
        filename = payload["title"].replace(" ", "_").lower()[:40] + ".md"
        result = tools["github"].create_gist(filename=filename, content=payload["body_markdown"], description=payload["title"])
        platform_id = result["id"]
        url = result["url"]

    store.mark_content_published(content_id=content_id, platform_id=platform_id, url=url)

    promote_payload = {
        "content_id": str(content_id),
        "title": payload["title"],
        "url": url,
    }
    store.create_outbox_event(
        event_type="promote_content",
        payload=promote_payload,
        idempotency_key=f"promote:{content_id}",
        platform="twitter",
    )


def _handle_promote_event(store: MemoryStore, tools: dict[str, Any], event: dict[str, Any]) -> None:
    payload = event["payload"]
    title = payload["title"]
    url = payload["url"]

    tweets = [
        f"New agentic RevenueCat guide: {title}",
        "Includes implementation details, guardrails, and production-ready patterns.",
        f"Read: {url}",
    ]
    ids = tools["twitter"].post_thread(tweets)
    store.insert_community_interaction(
        platform="twitter",
        external_id=ids[0],
        content=title,
        interaction_type="thread",
        author_handle="self",
        our_reply=f"Promoted content: {url}",
    )


def _handle_reply_event(store: MemoryStore, tools: dict[str, Any], event: dict[str, Any]) -> None:
    payload = event["payload"]
    mention = payload["mention"]
    reply = payload["reply"]

    if mention["platform"] == "twitter":
        tweet_id = tools["twitter"].post_tweet(text=reply, reply_to=mention["external_id"])
        store.insert_community_interaction(
            platform="twitter",
            external_id=mention["external_id"],
            content=mention["content"],
            interaction_type="reply",
            author_handle=mention.get("author", "unknown"),
            our_reply=f"{reply} (tweet_id={tweet_id})",
        )
        return

    if mention["platform"] == "github":
        result = tools["github"].create_issue_comment(
            owner=mention["owner"],
            repo=mention["repo"],
            issue_number=int(mention["issue_number"]),
            body=reply,
        )
        store.insert_community_interaction(
            platform="github",
            external_id=mention["external_id"],
            content=mention["content"],
            interaction_type="reply",
            author_handle=mention.get("author", "unknown"),
            our_reply=f"{reply} (comment_id={result.get('id')})",
        )


def _notify_slack(message: str) -> None:
    if not settings.slack_webhook_url:
        return
    with httpx.Client(timeout=10.0) as client:
        client.post(settings.slack_webhook_url, json={"text": message})
