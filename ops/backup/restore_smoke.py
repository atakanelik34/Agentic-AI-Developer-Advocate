"""Restore smoke-test routine."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import psycopg

from core.settings import get_settings


def run_restore_smoke() -> dict[str, int]:
    """Restore latest backup into temp DB and validate row counts."""

    settings = get_settings()
    latest_backup = _find_latest_local_backup(Path("/tmp/revenuecat-backups"))
    if latest_backup is None:
        raise RuntimeError("no local backup available for restore smoke test")

    test_db = "revenuecat_restore_test"
    base_dsn = settings.database_url

    with psycopg.connect(base_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {test_db}")
            cur.execute(f"CREATE DATABASE {test_db}")

    restore_dsn = _replace_db_name(base_dsn, test_db)

    subprocess.run(["gunzip", "-c", str(latest_backup)], check=True, stdout=open("/tmp/restore.dump", "wb"))
    subprocess.run(["pg_restore", "-d", restore_dsn, "/tmp/restore.dump"], check=True)

    with psycopg.connect(restore_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM published_content")
            content_rows = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM community_interactions")
            interaction_rows = cur.fetchone()[0]

    return {"published_content": int(content_rows), "community_interactions": int(interaction_rows)}


def _find_latest_local_backup(path: Path) -> Path | None:
    files = sorted(path.glob("*.dump.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _replace_db_name(dsn: str, db_name: str) -> str:
    if "/" not in dsn:
        raise ValueError("invalid DATABASE_URL")
    return dsn.rsplit("/", 1)[0] + "/" + db_name
