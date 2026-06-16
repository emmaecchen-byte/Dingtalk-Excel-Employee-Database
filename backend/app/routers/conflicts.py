"""
Conflict resolution API: list pending conflicts and apply HR resolutions.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.database import get_db
from app.models import Conflict, Employee, MonthlyAttendance, User
from app.schemas import (
    ConflictAutoResolveRequest,
    ConflictBatchResolveRequest,
    ConflictItem,
    ConflictListResponse,
    ConflictResolveRequest,
    ConflictResolveResponse,
    ConflictSingleResolveResponse,
)
from app.services.conflict_resolution import (
    ConflictResolutionError,
    auto_resolve_conflicts,
    resolve_conflicts_batch,
    resolve_single_conflict,
)
from app.services.sync_counts import count_pending_conflicts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conflicts", tags=["conflicts"])

HR_ROLES = ["hr_admin", "hr_viewer"]


def _validate_period(year: int, month: int) -> None:
    if year < 2000 or year > 2100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Year must be between 2000 and 2100",
        )
    if month < 1 or month > 12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Month must be between 1 and 12",
        )


def _format_timestamp(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _build_conflict_items(
    db: Session,
    *,
    company_id: int,
    year: int,
    month: int,
    conflicts: List[Conflict],
) -> List[ConflictItem]:
    """Join conflicts with employee names and attendance sync metadata."""
    if not conflicts:
        return []

    employee_ids = {conflict.employee_id for conflict in conflicts}
    employees = {
        employee.id: employee
        for employee in db.query(Employee).filter(Employee.id.in_(employee_ids)).all()
    }
    attendance_records = {
        record.employee_id: record
        for record in db.query(MonthlyAttendance).filter(
            MonthlyAttendance.company_id == company_id,
            MonthlyAttendance.year == year,
            MonthlyAttendance.month == month,
            MonthlyAttendance.employee_id.in_(employee_ids),
        ).all()
    }

    items: List[ConflictItem] = []
    for conflict in conflicts:
        employee = employees.get(conflict.employee_id)
        record = attendance_records.get(conflict.employee_id)

        items.append(
            ConflictItem(
                id=conflict.id,
                employee_id=conflict.employee_id,
                employee_name=employee.name if employee else "",
                department=employee.department if employee else "",
                field_name=conflict.field_name,
                manual_value=conflict.manual_value,
                dingtalk_value=conflict.dingtalk_value,
                manual_edit_at=_format_timestamp(conflict.created_at),
                dingtalk_sync_at=_format_timestamp(
                    record.last_sync_from_dingtalk if record else None
                ),
                created_at=_format_timestamp(conflict.created_at),
                status=conflict.status,
            )
        )
    return items


@router.post("/batch-resolve", response_model=ConflictResolveResponse)
def batch_resolve_conflicts(
    payload: ConflictBatchResolveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    """
    Resolve multiple conflicts with the same resolution method.

    Body: ``{ conflict_ids: [1, 2, 3], resolution_method: 'dingtalk_priority' }``
    """
    try:
        resolved, failed = resolve_conflicts_batch(
            db,
            company_id=current_user.company_id,
            conflict_ids=payload.conflict_ids,
            resolution_method=payload.resolution_method,
            resolved_by=current_user.id,
            resolved_value=payload.resolved_value,
            user=current_user,
        )
    except ConflictResolutionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    remaining = count_pending_conflicts(db, current_user.company_id)
    resolved_count = len(resolved)
    logger.info(
        "Batch resolve: user_id=%s resolved=%s failed=%s remaining=%s",
        current_user.id,
        resolved_count,
        failed,
        remaining,
    )
    return ConflictResolveResponse(
        success=True,
        resolved=resolved_count,
        failed=failed,
        remaining=remaining,
        resolved_count=resolved_count,
        pending_conflicts_count=remaining,
        conflict_ids=[conflict.id for conflict in resolved],
        resolution_method=payload.resolution_method,
    )


@router.post("/auto-resolve", response_model=ConflictResolveResponse)
def auto_resolve(
    payload: ConflictAutoResolveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    """
    Auto-resolve pending conflicts using ``users.preferences.conflict_priority``.

    Optional ``year`` / ``month`` limit scope; otherwise all pending conflicts apply.
    """
    if payload.year is not None or payload.month is not None:
        if payload.year is None or payload.month is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Both year and month are required when filtering by period",
            )
        _validate_period(payload.year, payload.month)

    try:
        resolved, skipped, method_used = auto_resolve_conflicts(
            db,
            company_id=current_user.company_id,
            user=current_user,
            year=payload.year,
            month=payload.month,
        )
    except ConflictResolutionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    remaining = count_pending_conflicts(db, current_user.company_id)
    resolved_count = len(resolved)
    logger.info(
        "Auto-resolve: user_id=%s resolved=%s skipped=%s remaining=%s method=%s",
        current_user.id,
        resolved_count,
        skipped,
        remaining,
        method_used,
    )
    return ConflictResolveResponse(
        success=True,
        resolved=resolved_count,
        failed=skipped,
        remaining=remaining,
        resolved_count=resolved_count,
        pending_conflicts_count=remaining,
        conflict_ids=[conflict.id for conflict in resolved],
        skipped_count=skipped,
        resolution_method=method_used,
    )


@router.get("/{year}/{month}", response_model=ConflictListResponse)
def list_conflicts(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    """
    List pending conflicts for a month with employee names.

    Returns items shaped as:
    ``{ id, employee_name, field_name, dingtalk_value, manual_value, created_at }``
    (plus employee_id, department, status for the UI).
    """
    _validate_period(year, month)

    conflicts = (
        db.query(Conflict)
        .filter(
            Conflict.company_id == current_user.company_id,
            Conflict.year == year,
            Conflict.month == month,
            Conflict.status == "pending",
        )
        .order_by(Conflict.created_at.asc())
        .all()
    )

    items = _build_conflict_items(
        db,
        company_id=current_user.company_id,
        year=year,
        month=month,
        conflicts=conflicts,
    )

    return ConflictListResponse(
        year=year,
        month=month,
        total=len(items),
        pending_conflicts_count=count_pending_conflicts(db, current_user.company_id),
        conflicts=items,
    )


@router.post("/{conflict_id}/resolve", response_model=ConflictSingleResolveResponse)
def resolve_conflict_endpoint(
    conflict_id: int,
    payload: ConflictResolveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    """
    Resolve a single conflict.

    - ``manual`` — use ``resolved_value`` from the request body
    - ``dingtalk_priority`` — use ``dingtalk_value`` from the conflict record
    - ``manual_priority`` — use ``manual_value`` from the conflict record

    Updates ``conflicts``, ``monthly_attendance``, ``manual_changes``, and ``version_history``.
    """
    try:
        conflict = resolve_single_conflict(
            db,
            company_id=current_user.company_id,
            conflict_id=conflict_id,
            resolution_method=payload.resolution_method,
            resolved_by=current_user.id,
            resolved_value=payload.resolved_value,
            user=current_user,
        )
    except ConflictResolutionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    logger.info(
        "Conflict resolved: user_id=%s conflict_id=%s method=%s value=%s",
        current_user.id,
        conflict.id,
        conflict.resolution_method,
        conflict.resolved_value,
    )

    return ConflictSingleResolveResponse(
        success=True,
        conflict_id=conflict.id,
        status=conflict.status,
        resolution_method=conflict.resolution_method or payload.resolution_method,
        resolved_value=conflict.resolved_value,
        pending_conflicts_count=count_pending_conflicts(db, current_user.company_id),
    )
