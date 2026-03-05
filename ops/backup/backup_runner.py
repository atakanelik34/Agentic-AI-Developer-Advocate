"""Database backup routines."""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import structlog

from core.settings import get_settings


logger = structlog.get_logger(__name__)


def run_backup() -> dict[str, str]:
    """Create compressed pg_dump and upload to remote object storage via rclone."""

    settings = get_settings()
    remote_url = settings.backup_remote_url
    if not remote_url:
        raise RuntimeError("BACKUP_REMOTE_URL is required for backups")

    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    backup_dir = Path("/tmp/revenuecat-backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    dump_file = backup_dir / f"backup-{timestamp}.dump"
    archive_file = backup_dir / f"backup-{timestamp}.dump.gz"

    if _disk_usage_percent(str(backup_dir)) >= 85:
        _cleanup_old_files(backup_dir)

    subprocess.run(
        ["pg_dump", settings.database_url, "-Fc", "-f", str(dump_file)],
        check=True,
    )
    subprocess.run(["gzip", "-f", str(dump_file)], check=True)

    subprocess.run(["rclone", "copy", str(archive_file), remote_url], check=True)
    _cleanup_old_files(backup_dir)

    logger.info("backup_uploaded", file=str(archive_file), remote=remote_url)
    return {"file": str(archive_file), "remote": remote_url}


def _disk_usage_percent(path: str) -> int:
    total, used, _ = shutil.disk_usage(path)
    return int((used / total) * 100)


def _cleanup_old_files(path: Path) -> None:
    for file in path.glob("*.gz"):
        try:
            if file.stat().st_mtime < (datetime.now().timestamp() - 86400 * 2):
                file.unlink(missing_ok=True)
        except OSError:
            continue
