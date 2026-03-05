"""Database access layer for agent runtime state."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import psycopg
import structlog
from psycopg.rows import dict_row

from core.settings import get_settings


logger = structlog.get_logger(__name__)


class MemoryStore:
    """Persistence adapter around PostgreSQL and pgvector."""

    def __init__(self, dsn: str | None = None) -> None:
        settings = get_settings()
        self.dsn = dsn or settings.database_url

    def _conn(self) -> psycopg.Connection[Any]:
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def health_check(self) -> bool:
        """Validate database connectivity."""

        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return True

    def redis_health_check(self) -> bool:
        """Placeholder for API health compatibility; Redis checked elsewhere."""

        return True

    def insert_memory(self, memory_type: str, content: str, embedding: list[float], importance: int = 5) -> UUID:
        """Store semantic memory item."""

        query = """
            INSERT INTO agent_memory (memory_type, content, embedding, importance)
            VALUES (%s, %s, %s::vector, %s)
            RETURNING id
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (memory_type, content, _vector_literal(embedding), importance))
                row = cur.fetchone()
                assert row is not None
                return row["id"]

    def search_memory(self, embedding: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        """Search memory by vector similarity."""

        query = """
            SELECT id, memory_type, content, importance, created_at,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM agent_memory
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                vec = _vector_literal(embedding)
                cur.execute(query, (vec, vec, top_k))
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def get_recent_publications(self, days: int = 30) -> list[dict[str, Any]]:
        """Fetch recently published content."""

        query = """
            SELECT id, title, content_type, platform, url, published_at
            FROM published_content
            WHERE published_at >= NOW() - (%s || ' days')::interval
              AND status = 'published'
            ORDER BY published_at DESC
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (days,))
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def get_recent_memories(self, limit: int = 20) -> list[dict[str, Any]]:
        """Fetch most recent memory items."""

        query = """
            SELECT id, memory_type, content, importance, created_at
            FROM agent_memory
            ORDER BY created_at DESC
            LIMIT %s
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (limit,))
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def create_content_draft(
        self,
        title: str,
        body: str,
        content_type: str,
        platform: str,
        tags: list[str],
        embedding: list[float],
    ) -> dict[str, Any]:
        """Insert draft content row before quality checks and publishing."""

        query = """
            INSERT INTO published_content
                (title, body, content_type, platform, tags, embedding, status, embedding_generated_at)
            VALUES (%s, %s, %s, %s, %s, %s::vector, 'draft', NOW())
            RETURNING id, title, status, published_at
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (title, body, content_type, platform, tags, _vector_literal(embedding)),
                )
                row = cur.fetchone()
                assert row is not None
                return dict(row)

    def find_similar_content(
        self,
        embedding: list[float],
        days: int = 90,
        limit: int = 1,
    ) -> list[dict[str, Any]]:
        """Find most similar content from recent window."""

        query = """
            SELECT id, title, 1 - (embedding <=> %s::vector) AS similarity
            FROM published_content
            WHERE published_at >= NOW() - (%s || ' days')::interval
              AND embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        vec = _vector_literal(embedding)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (vec, days, vec, limit))
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def mark_quality_result(
        self,
        content_id: UUID,
        score: float,
        flags: list[dict[str, Any]],
        similarity_score: float,
        dedupe_source_id: UUID | None,
        passed: bool,
    ) -> None:
        """Persist quality check output for draft."""

        status = "queued" if passed else "quality_failed"
        query = """
            UPDATE published_content
            SET quality_score = %s,
                quality_flags = %s::jsonb,
                similarity_score = %s,
                dedupe_source_id = %s,
                status = %s
            WHERE id = %s
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (score, json.dumps(flags), similarity_score, dedupe_source_id, status, content_id),
                )

    def link_content_outbox(self, content_id: UUID, outbox_event_id: UUID) -> None:
        """Attach outbox event id to content row."""

        query = "UPDATE published_content SET outbox_event_id = %s WHERE id = %s"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (outbox_event_id, content_id))

    def create_outbox_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        idempotency_key: str,
        platform: str | None = None,
        max_attempts: int = 5,
    ) -> UUID:
        """Store external write command in outbox."""

        query = """
            INSERT INTO outbox_events (event_type, payload, idempotency_key, platform, max_attempts, next_attempt_at)
            VALUES (%s, %s::jsonb, %s, %s, %s, NOW())
            ON CONFLICT (idempotency_key) DO UPDATE
              SET updated_at = NOW()
            RETURNING id
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (event_type, json.dumps(payload), idempotency_key, platform, max_attempts))
                row = cur.fetchone()
                assert row is not None
                return row["id"]

    def fetch_due_outbox_events(self, limit: int = 20) -> list[dict[str, Any]]:
        """Atomically claim queued/deferred events that are ready."""

        query = """
            WITH to_claim AS (
                SELECT id
                FROM outbox_events
                WHERE status IN ('queued', 'deferred')
                  AND COALESCE(next_attempt_at, NOW()) <= NOW()
                ORDER BY created_at ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
            )
            UPDATE outbox_events o
            SET status = 'processing',
                updated_at = NOW()
            FROM to_claim
            WHERE o.id = to_claim.id
            RETURNING o.*
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (limit,))
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def mark_outbox_done(self, event_id: UUID) -> None:
        """Mark outbox event as successfully processed."""

        query = """
            UPDATE outbox_events
            SET status = 'done', updated_at = NOW(), last_error = NULL
            WHERE id = %s
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (event_id,))

    def mark_outbox_retry(
        self,
        event_id: UUID,
        error: str,
        next_attempt_at: datetime,
    ) -> None:
        """Defer event to a later time after recoverable failure."""

        query = """
            UPDATE outbox_events
            SET status = 'deferred',
                attempts = attempts + 1,
                last_error = %s,
                next_attempt_at = %s,
                updated_at = NOW()
            WHERE id = %s
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (error, next_attempt_at, event_id))

    def mark_outbox_dead_letter(self, event_id: UUID, error: str) -> None:
        """Mark outbox event unrecoverable after max attempts."""

        query = """
            UPDATE outbox_events
            SET status = 'dead_letter', attempts = attempts + 1,
                last_error = %s, updated_at = NOW()
            WHERE id = %s
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (error, event_id))

    def mark_content_published(self, content_id: UUID, platform_id: str, url: str) -> None:
        """Finalize published content metadata."""

        query = """
            UPDATE published_content
            SET status = 'published', platform_id = %s, url = %s, published_at = NOW()
            WHERE id = %s
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (platform_id, url, content_id))

    def mark_content_failed(self, content_id: UUID) -> None:
        """Mark draft as failed after unrecoverable publish issue."""

        query = "UPDATE published_content SET status = 'failed' WHERE id = %s"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (content_id,))

    def get_content_by_id(self, content_id: UUID) -> dict[str, Any] | None:
        """Fetch a single content row."""

        query = "SELECT * FROM published_content WHERE id = %s"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (content_id,))
                row = cur.fetchone()
        return dict(row) if row else None

    def insert_community_interaction(
        self,
        platform: str,
        external_id: str,
        content: str,
        interaction_type: str,
        author_handle: str | None = None,
        our_reply: str | None = None,
    ) -> bool:
        """Insert interaction, returning False on uniqueness conflict."""

        query = """
            INSERT INTO community_interactions
                (platform, external_id, content, interaction_type, author_handle, our_reply, replied_at)
            VALUES (%s, %s, %s, %s, %s, %s, CASE WHEN %s IS NULL THEN NULL ELSE NOW() END)
            ON CONFLICT (platform, external_id) DO NOTHING
            RETURNING id
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (platform, external_id, content, interaction_type, author_handle, our_reply, our_reply),
                )
                row = cur.fetchone()
        return row is not None

    def count_author_replies_today(self, platform: str, author_handle: str) -> int:
        """Return number of replies sent to same author in current UTC day."""

        query = """
            SELECT COUNT(*) AS c
            FROM community_interactions
            WHERE platform = %s
              AND author_handle = %s
              AND our_reply IS NOT NULL
              AND replied_at::date = NOW()::date
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (platform, author_handle))
                row = cur.fetchone()
                assert row is not None
                return int(row["c"])

    def get_recent_interactions(self, days: int = 7) -> list[dict[str, Any]]:
        """Fetch interaction signals for feedback aggregation."""

        query = """
            SELECT *
            FROM community_interactions
            WHERE COALESCE(replied_at, NOW()) >= NOW() - (%s || ' days')::interval
            ORDER BY COALESCE(replied_at, NOW()) DESC
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (days,))
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def insert_feedback_item(
        self,
        title: str,
        description: str,
        category: str,
        priority: str,
        evidence: list[str],
        submitted_to_team: bool = False,
    ) -> UUID:
        """Store structured product feedback."""

        query = """
            INSERT INTO product_feedback (title, description, category, priority, evidence, submitted_to_team)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (title, description, category, priority, evidence, submitted_to_team))
                row = cur.fetchone()
                assert row is not None
                return row["id"]

    def get_weekly_metrics(self, week_start: date) -> dict[str, Any] | None:
        """Get weekly metrics snapshot."""

        query = "SELECT * FROM weekly_metrics WHERE week_start = %s"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (week_start,))
                row = cur.fetchone()
        return dict(row) if row else None

    def upsert_weekly_metrics(self, week_start: date, payload: dict[str, Any]) -> None:
        """Store weekly KPI snapshot."""

        query = """
            INSERT INTO weekly_metrics (
                week_start, content_published, community_interactions, feedback_submitted,
                total_reach, top_content, growth_experiments, raw_report
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
            ON CONFLICT (week_start) DO UPDATE SET
                content_published = EXCLUDED.content_published,
                community_interactions = EXCLUDED.community_interactions,
                feedback_submitted = EXCLUDED.feedback_submitted,
                total_reach = EXCLUDED.total_reach,
                top_content = EXCLUDED.top_content,
                growth_experiments = EXCLUDED.growth_experiments,
                raw_report = EXCLUDED.raw_report
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        week_start,
                        payload.get("content_published", 0),
                        payload.get("community_interactions", 0),
                        payload.get("feedback_submitted", 0),
                        payload.get("total_reach", 0),
                        json.dumps(payload.get("top_content", [])),
                        json.dumps(payload.get("growth_experiments", [])),
                        payload.get("raw_report", ""),
                    ),
                )

    def create_job_run(self, job_type: str, payload: dict[str, Any]) -> UUID:
        """Create async job record."""

        query = """
            INSERT INTO job_runs (job_type, status, payload, started_at)
            VALUES (%s, 'running', %s::jsonb, NOW())
            RETURNING id
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (job_type, json.dumps(payload)))
                row = cur.fetchone()
                assert row is not None
                return row["id"]

    def update_job_run(
        self,
        job_id: UUID,
        status: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        provider: str | None = None,
        attempt: int | None = None,
    ) -> None:
        """Update async job state."""

        query = """
            UPDATE job_runs
            SET status = %s,
                result = COALESCE(%s::jsonb, result),
                error = COALESCE(%s, error),
                provider = COALESCE(%s, provider),
                attempt = COALESCE(%s, attempt),
                updated_at = NOW(),
                finished_at = CASE WHEN %s IN ('success', 'failed') THEN NOW() ELSE finished_at END
            WHERE id = %s
        """
        result_json = json.dumps(result) if result is not None else None
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (status, result_json, error, provider, attempt, status, job_id))

    def get_job_run(self, job_id: UUID) -> dict[str, Any] | None:
        """Fetch job state by id."""

        query = "SELECT * FROM job_runs WHERE id = %s"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (job_id,))
                row = cur.fetchone()
        return dict(row) if row else None

    def log_provider_usage(
        self,
        provider: str,
        model: str,
        request_id: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        success: bool,
        cost_estimate_usd: float,
        error: str | None = None,
    ) -> None:
        """Persist LLM usage/cost record."""

        query = """
            INSERT INTO provider_usage
                (provider, model, request_id, input_tokens, output_tokens, latency_ms, success, cost_estimate_usd, error)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        provider,
                        model,
                        request_id,
                        input_tokens,
                        output_tokens,
                        latency_ms,
                        success,
                        cost_estimate_usd,
                        error,
                    ),
                )

    def get_recent_provider_usage(self, hours: int = 1) -> list[dict[str, Any]]:
        """Get usage stats for provider health heuristics."""

        query = """
            SELECT provider, model, success, latency_ms, created_at
            FROM provider_usage
            WHERE created_at >= NOW() - (%s || ' hours')::interval
            ORDER BY created_at DESC
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (hours,))
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def get_system_config(self, key: str) -> str | None:
        """Read a runtime configuration value from DB."""

        query = "SELECT value FROM system_config WHERE key = %s"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (key,))
                row = cur.fetchone()
        return row["value"] if row else None

    def set_system_config(self, key: str, value: str, updated_by: str) -> None:
        """Set runtime configuration value."""

        query = """
            INSERT INTO system_config (key, value, updated_by, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value,
                updated_by = EXCLUDED.updated_by,
                updated_at = NOW()
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (key, value, updated_by))

    def create_growth_experiment(
        self,
        week_start: date,
        hypothesis: str,
        method: str,
        target_metric: str,
        status: str = "planned",
        notes: str | None = None,
    ) -> UUID:
        """Insert growth experiment planning record."""

        query = """
            INSERT INTO growth_experiments
                (week_start, hypothesis, method, target_metric, status, notes)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (week_start, hypothesis, method, target_metric, status, notes))
                row = cur.fetchone()
                assert row is not None
                return row["id"]

    def get_latest_growth_experiment(self) -> dict[str, Any] | None:
        """Get most recent experiment."""

        query = "SELECT * FROM growth_experiments ORDER BY created_at DESC LIMIT 1"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                row = cur.fetchone()
        return dict(row) if row else None

    def get_planned_experiment(self) -> dict[str, Any] | None:
        """Get earliest planned experiment ready to start."""

        query = """
            SELECT *
            FROM growth_experiments
            WHERE status = 'planned'
            ORDER BY created_at ASC
            LIMIT 1
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                row = cur.fetchone()
        return dict(row) if row else None

    def update_growth_experiment(
        self,
        experiment_id: UUID,
        *,
        status: str | None = None,
        baseline_value: float | None = None,
        result_value: float | None = None,
        success: bool | None = None,
        notes: str | None = None,
    ) -> None:
        """Update experiment lifecycle fields."""

        query = """
            UPDATE growth_experiments
            SET status = COALESCE(%s, status),
                baseline_value = COALESCE(%s, baseline_value),
                result_value = COALESCE(%s, result_value),
                success = COALESCE(%s, success),
                notes = COALESCE(%s, notes),
                updated_at = NOW()
            WHERE id = %s
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (status, baseline_value, result_value, success, notes, experiment_id))

    def calculate_metric_baseline(self, target_metric: str) -> float:
        """Compute baseline from the previous 4 completed weeks."""

        mapping = {
            "impressions": "total_reach",
            "content_published": "content_published",
            "community_interactions": "community_interactions",
            "feedback_submitted": "feedback_submitted",
        }
        column = mapping.get(target_metric, "total_reach")
        query = f"""
            SELECT AVG({column}) AS baseline
            FROM (
                SELECT {column}
                FROM weekly_metrics
                ORDER BY week_start DESC
                LIMIT 4
            ) s
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                row = cur.fetchone()
                if row and row["baseline"] is not None:
                    return float(row["baseline"])
        return 0.0

    def get_recent_weekly_reports(self, weeks: int = 4) -> list[dict[str, Any]]:
        """Get latest weekly metrics rows for planning and analysis."""

        query = """
            SELECT *
            FROM weekly_metrics
            ORDER BY week_start DESC
            LIMIT %s
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (weeks,))
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def get_recent_content(self, limit: int = 10) -> list[dict[str, Any]]:
        """Fetch recent content rows for API."""

        query = """
            SELECT id, title, content_type, platform, status, url, published_at
            FROM published_content
            ORDER BY published_at DESC
            LIMIT %s
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (limit,))
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def get_weekly_metrics_window(self, limit: int = 8) -> list[dict[str, Any]]:
        """Fetch recent weekly metrics for dashboard endpoint."""

        query = """
            SELECT *
            FROM weekly_metrics
            ORDER BY week_start DESC
            LIMIT %s
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (limit,))
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def compute_weekly_summary(self, week_start: date) -> dict[str, Any]:
        """Build KPI summary for week starting on given date."""

        week_end = week_start + timedelta(days=7)

        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) AS c, COALESCE(SUM((metrics->>'impressions')::int), 0) AS reach
                    FROM published_content
                    WHERE published_at >= %s AND published_at < %s AND status = 'published'
                    """,
                    (week_start, week_end),
                )
                content_row = cur.fetchone() or {"c": 0, "reach": 0}

                cur.execute(
                    """
                    SELECT COUNT(*) AS c
                    FROM community_interactions
                    WHERE COALESCE(replied_at, NOW()) >= %s
                      AND COALESCE(replied_at, NOW()) < %s
                    """,
                    (week_start, week_end),
                )
                interaction_row = cur.fetchone() or {"c": 0}

                cur.execute(
                    """
                    SELECT COUNT(*) AS c
                    FROM product_feedback
                    WHERE submitted_at >= %s AND submitted_at < %s
                    """,
                    (week_start, week_end),
                )
                feedback_row = cur.fetchone() or {"c": 0}

                cur.execute(
                    """
                    SELECT id, hypothesis, method, target_metric, baseline_value, result_value, success, status
                    FROM growth_experiments
                    WHERE week_start = %s
                    ORDER BY created_at DESC
                    """,
                    (week_start,),
                )
                experiments = [dict(r) for r in cur.fetchall()]

        return {
            "week_start": str(week_start),
            "content_published": int(content_row["c"]),
            "community_interactions": int(interaction_row["c"]),
            "feedback_submitted": int(feedback_row["c"]),
            "total_reach": int(content_row["reach"] or 0),
            "growth_experiments": experiments,
        }

    def utc_now(self) -> datetime:
        """Return current UTC timestamp."""

        return datetime.now(UTC)


def _vector_literal(values: list[float]) -> str:
    """Convert float vector to pgvector literal."""

    return "[" + ",".join(f"{v:.8f}" for v in values) + "]"
