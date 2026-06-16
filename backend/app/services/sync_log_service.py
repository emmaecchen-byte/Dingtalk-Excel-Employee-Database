"""
Persist and query DingTalk sync operation logs.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import SyncLog, VersionHistory

logger = logging.getLogger(__name__)

SYNC_STATUS_RUNNING = "running"
SYNC_STATUS_COMPLETED = "completed"
SYNC_STATUS_FAILED = "failed"


def begin_sync_log(
    db: Session,
    *,
    company_id: int,
    sync_type: str,
    started_at: Optional[datetime] = None,
) -> SyncLog:
    log = SyncLog(
        company_id=company_id,
        sync_type=sync_type,
        started_at=started_at or datetime.utcnow(),
        status=SYNC_STATUS_RUNNING,
        records_processed=0,
    )
    db.add(log)
    db.flush()
    return log


def finish_sync_log(
    db: Session,
    log: SyncLog,
    *,
    status: str = SYNC_STATUS_COMPLETED,
    records_processed: int = 0,
    message: Optional[str] = None,
) -> SyncLog:
    log.status = status
    log.records_processed = records_processed
    log.message = message
    log.completed_at = datetime.utcnow()
    db.flush()
    logger.info(
        "Sync log finished: id=%s company_id=%s type=%s status=%s records=%s",
        log.id,
        log.company_id,
        log.sync_type,
        log.status,
        log.records_processed,
    )
    return log


def get_last_successful_sync_timestamp(db: Session, company_id: int) -> Optional[datetime]:
    """Most recent completed sync from sync_logs, with version_history fallback."""
    log_row = (
        db.query(SyncLog)
        .filter(
            SyncLog.company_id == company_id,
            SyncLog.status == SYNC_STATUS_COMPLETED,
            SyncLog.completed_at.isnot(None),
        )
        .order_by(SyncLog.completed_at.desc(), SyncLog.id.desc())
        .first()
    )
    if log_row and log_row.completed_at:
        return log_row.completed_at

    version_row = (
        db.query(VersionHistory.created_at)
        .filter(VersionHistory.company_id == company_id)
        .order_by(VersionHistory.created_at.desc())
        .first()
    )
    if version_row and version_row[0]:
        return version_row[0]

    return None
