"""Attendance period list, confirm, archive, and delete routes."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.crud.attendance_period_edit_log import attendance_period_edit_log
from app.database import get_db
from app.models import User
from app.schemas import (
    AttendancePeriodActionResponse,
    AttendancePeriodEditLogResponse,
    AttendancePeriodListResponse,
    AttendancePeriodSummary,
)
from app.services.period_workflow import (
    PeriodWorkflowError,
    archive_period,
    confirm_period,
    delete_draft_period,
    get_period_for_company_or_raise,
    list_company_periods,
    serialize_period_summary,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["attendance-periods"])

HR_ROLES = ["hr_admin", "hr_viewer"]
HR_ADMIN_ROLES = ["hr_admin"]


@router.get("/period/{period_id}", response_model=AttendancePeriodSummary)
def get_attendance_period(
    period_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    """Get a single attendance period summary."""
    try:
        period = get_period_for_company_or_raise(db, period_id, current_user.company_id)
    except PeriodWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return AttendancePeriodSummary(**serialize_period_summary(db, period))


@router.get("/periods", response_model=AttendancePeriodListResponse)
def list_attendance_periods(
    status: Optional[str] = Query(None, description="Filter by display status: draft, confirmed, archived"),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    month: Optional[int] = Query(None, ge=1, le=12),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    """List processed attendance months for the company."""
    periods = list_company_periods(
        db,
        current_user.company_id,
        status=status,
        year=year,
        month=month,
    )
    return AttendancePeriodListResponse(
        total=len(periods),
        periods=[AttendancePeriodSummary(**item) for item in periods],
    )


@router.post("/period/{period_id}/confirm", response_model=AttendancePeriodActionResponse)
def confirm_attendance_period(
    period_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ADMIN_ROLES)),
):
    """Mark a draft period as confirmed by HR."""
    try:
        period = confirm_period(db, period_id, current_user)
    except PeriodWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return AttendancePeriodActionResponse(period=AttendancePeriodSummary(**period))


@router.post("/period/{period_id}/archive", response_model=AttendancePeriodActionResponse)
def archive_attendance_period(
    period_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ADMIN_ROLES)),
):
    """Archive a confirmed period (read-only)."""
    try:
        period = archive_period(db, period_id, current_user)
    except PeriodWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return AttendancePeriodActionResponse(period=AttendancePeriodSummary(**period))


@router.delete("/period/{period_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attendance_period_draft(
    period_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ADMIN_ROLES)),
):
    """Delete a draft period and all related data."""
    try:
        delete_draft_period(db, period_id, current_user.company_id)
    except PeriodWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return None


@router.get("/period/{period_id}/edit-logs", response_model=list[AttendancePeriodEditLogResponse])
def list_period_edit_logs(
    period_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    """Return cell edit audit history for a period."""
    try:
        get_period_for_company_or_raise(db, period_id, current_user.company_id)
    except PeriodWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    logs = attendance_period_edit_log.list_for_period(db, period_id)
    return [
        AttendancePeriodEditLogResponse(
            id=log.id,
            field_name=log.field_name,
            old_value=log.old_value,
            new_value=log.new_value,
            employee_name=log.employee_name,
            editor_name=log.editor_name,
            edited_at=log.edited_at,
        )
        for log in logs
    ]
