import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.database import get_db
from app.models import Conflict, Employee, ManualChange, MonthlyAttendance, User
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
    employee_ids = {conflict.employee_id for conflict in conflicts}
    employees = {
        employee.id: employee
        for employee in db.query(Employee).filter(Employee.id.in_(employee_ids)).all()
    } if employee_ids else {}

    attendance_records = {
        record.employee_id: record
        for record in db.query(MonthlyAttendance).filter(
            MonthlyAttendance.company_id == company_id,
            MonthlyAttendance.year == year,
            MonthlyAttendance.month == month,
            MonthlyAttendance.employee_id.in_(employee_ids),
        ).all()
    } if employee_ids else {}

    items: List[ConflictItem] = []
    for conflict in conflicts:
        employee = employees.get(conflict.employee_id)
        record = attendance_records.get(conflict.employee_id)
        manual_change = (
            db.query(ManualChange)
            .filter(
                ManualChange.company_id == company_id,
                ManualChange.year == year,
                ManualChange.month == month,
                ManualChange.employee_id == conflict.employee_id,
                ManualChange.field_name == conflict.field_name,
            )
            .order_by(ManualChange.change_timestamp.desc())
            .first()
        )

        items.append(
            ConflictItem(
                id=conflict.id,
                employee_id=conflict.employee_id,
                employee_name=employee.name if employee else "",
                department=employee.department if employee else "",
                field_name=conflict.field_name,
                manual_value=conflict.manual_value,
                dingtalk_value=conflict.dingtalk_value,
                manual_edit_at=_format_timestamp(
                    manual_change.change_timestamp if manual_change else conflict.created_at
                ),
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
    try:
        resolved = resolve_conflicts_batch(
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

    pending_count = count_pending_conflicts(db, current_user.company_id)
    return ConflictResolveResponse(
        success=True,
        resolved_count=len(resolved),
        pending_conflicts_count=pending_count,
        conflict_ids=[conflict.id for conflict in resolved],
    )


@router.post("/auto-resolve", response_model=ConflictResolveResponse)
def auto_resolve(
    payload: ConflictAutoResolveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    try:
        resolved = auto_resolve_conflicts(
            db,
            company_id=current_user.company_id,
            user=current_user,
            year=payload.year,
            month=payload.month,
        )
    except ConflictResolutionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    pending_count = count_pending_conflicts(db, current_user.company_id)
    logger.info(
        "Auto-resolve requested by user_id=%s resolved=%s pending=%s",
        current_user.id,
        len(resolved),
        pending_count,
    )
    return ConflictResolveResponse(
        success=True,
        resolved_count=len(resolved),
        pending_conflicts_count=pending_count,
        conflict_ids=[conflict.id for conflict in resolved],
    )


@router.get("/{year}/{month}", response_model=ConflictListResponse)
def list_conflicts(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    if month < 1 or month > 12:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Month must be between 1 and 12")

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

    return ConflictSingleResolveResponse(
        success=True,
        conflict_id=conflict.id,
        status=conflict.status,
        resolution_method=conflict.resolution_method or payload.resolution_method,
        resolved_value=conflict.resolved_value,
        pending_conflicts_count=count_pending_conflicts(db, current_user.company_id),
    )
