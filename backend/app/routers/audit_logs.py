"""Unified audit log API routes."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.crud.edit_log import edit_log
from app.database import get_db
from app.models import User
from app.schemas import EditLogListResponse, EditLogResponse
from app.services.period_workflow import PeriodWorkflowError, get_period_for_company_or_raise

logger = logging.getLogger(__name__)

router = APIRouter(tags=["attendance-audit"])

HR_ADMIN_ROLES = ["hr_admin"]


def _serialize_log(entry) -> EditLogResponse:
    return EditLogResponse(
        id=entry.id,
        period_id=entry.period_id,
        user_id=entry.user_id,
        user_name=entry.user_name,
        entity_type=entry.entity_type,
        entity_id=entry.entity_id,
        field_name=entry.field_name,
        old_value=entry.old_value,
        new_value=entry.new_value,
        action=entry.action,
        created_at=entry.created_at,
    )


@router.get("/period/{period_id}/audit-logs", response_model=EditLogListResponse)
def list_period_audit_logs(
    period_id: int,
    user_id: Optional[int] = Query(None),
    entity_type: Optional[str] = Query(None, description="daily_attendance or abnormal_record"),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ADMIN_ROLES)),
):
    """Return unified edit audit history for an attendance period."""
    try:
        get_period_for_company_or_raise(db, period_id, current_user.company_id)
    except PeriodWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    total = edit_log.count_for_period(
        db,
        period_id=period_id,
        company_id=current_user.company_id,
        user_id=user_id,
        entity_type=entity_type,
        date_from=date_from,
        date_to=date_to,
    )
    logs = edit_log.list_for_period(
        db,
        period_id=period_id,
        company_id=current_user.company_id,
        user_id=user_id,
        entity_type=entity_type,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )

    logger.info(
        "Audit logs listed: period_id=%s user_id=%s total=%s returned=%s",
        period_id,
        current_user.id,
        total,
        len(logs),
    )

    return EditLogListResponse(
        period_id=period_id,
        total=total,
        logs=[_serialize_log(entry) for entry in logs],
    )
