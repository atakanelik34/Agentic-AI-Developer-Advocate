"""Run SQL migrations in lexical order."""

from __future__ import annotations

from pathlib import Path

import psycopg
import structlog

from core.logging import configure_logging
from core.settings import get_settings


logger = structlog.get_logger(__name__)


def run_migrations() -> None:
    """Execute migration SQL files in sorted order."""

    settings = get_settings()
    configure_logging(settings.log_level)

    migrations_dir = Path(__file__).resolve().parent
    sql_files = sorted(migrations_dir.glob("*.sql"))

    if not sql_files:
        logger.warning("no_migrations_found", path=str(migrations_dir))
        return

    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            for sql_file in sql_files:
                logger.info("applying_migration", file=sql_file.name)
                cur.execute(sql_file.read_text(encoding="utf-8"))

    logger.info("migrations_complete", count=len(sql_files))


if __name__ == "__main__":
    run_migrations()
