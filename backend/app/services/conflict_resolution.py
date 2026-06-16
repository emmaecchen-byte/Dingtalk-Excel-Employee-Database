"""
Apply conflict resolutions to monthly_attendance, version_history, and conflicts table.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.excel.field_utils import apply_field_value
from app.models import Conflict, ManualChange, MonthlyAttendance, User, VersionHistory
from app.services.conflict_detection import (
    PRIORITY_ASK,
    PRIORITY_DINGTALK,
    PRIORITY_MANUAL,
    get_conflict_priority,
)
from app.services.sync_counts import count_pending_conflicts

logger = logging.getLogger(__name__)

RESOLUTION_MANUAL = "manual"
RESOLUTION_MANUAL_PRIORITY = "manual_priority"
RESOLUTION_DINGTALK_PRIORITY = "dingtalk_priority"

# Legacy aliases used by older clients
RESOLUTION_DINGTALK = "dingtalk"
RESOLUTION_CUSTOM = "custom"

VALID_RESOLUTION_METHODS = frozenset(
    {
        RESOLUTION_MANUAL,
        RESOLUTION_MANUAL_PRIORITY,
        RESOLUTION_DINGTALK_PRIORITY,
        RESOLUTION_DINGTALK,
        RESOLUTION_CUSTOM,
    }
)

PRIORITY_TO_RESOLUTION = {
    PRIORITY_MANUAL: RESOLUTION_MANUAL_PRIORITY,
    PRIORITY_DINGTALK: RESOLUTION_DINGTALK_PRIORITY,
}


class ConflictResolutionError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _resolve_value(conflict: Conflict, method: str, resolved_value: Optional[str]) -> str:
    if method == RESOLUTION_MANUAL:
        if resolved_value is None or str(resolved_value).strip() == "":
            raise ConflictResolutionError("resolved_value is required for manual resolution")
        return str(resolved_value)
    if method == RESOLUTION_MANUAL_PRIORITY:
        return conflict.manual_value or ""
    if method in {RESOLUTION_DINGTALK_PRIORITY, RESOLUTION_DINGTALK}:
        return conflict.dingtalk_value or ""
    if method == RESOLUTION_CUSTOM:
        if resolved_value is None or str(resolved_value).strip() == "":
            raise ConflictResolutionError("resolved_value is required for custom resolution")
        return str(resolved_value)
    raise ConflictResolutionError(f"Invalid resolution method: {method}")


def _next_version_number(db: Session, company_id: int, year: int, month: int) -> int:
    current = (
        db.query(func.max(VersionHistory.version_number))
        .filter(
            VersionHistory.company_id == company_id,
            VersionHistory.year == year,
            VersionHistory.month == month,
        )
        .scalar()
    )
    return int(current or 0) + 1


def _record_version_history(
    db: Session,
    *,
    company_id: int,
    year: int,
    month: int,
    user: User,
    resolution_method: str,
    resolved_conflicts: List[Conflict],
) -> VersionHistory:
    version = VersionHistory(
        company_id=company_id,
        year=year,
        month=month,
        version_number=_next_version_number(db, company_id, year, month),
        created_by=user.name,
        created_by_user_id=user.id,
        changes_summary={
            "event": "conflict_resolution",
            "resolution_method": resolution_method,
            "resolved_count": len(resolved_conflicts),
            "conflicts": [
                {
                    "conflict_id": conflict.id,
                    "employee_id": conflict.employee_id,
                    "field_name": conflict.field_name,
                    "resolved_value": conflict.resolved_value,
                    "manual_value": conflict.manual_value,
                    "dingtalk_value": conflict.dingtalk_value,
                }
                for conflict in resolved_conflicts
            ],
        },
        version_note=f"Resolved {len(resolved_conflicts)} conflict(s) via {resolution_method}",
    )
    db.add(version)
    db.flush()
    return version


def resolve_conflict(
    db: Session,
    conflict: Conflict,
    *,
    resolution_method: str,
    resolved_by: int,
    resolved_value: Optional[str] = None,
    record_version: bool = True,
    user: Optional[User] = None,
) -> Conflict:
    if conflict.status != "pending":
        raise ConflictResolutionError(f"Conflict {conflict.id} is already resolved", status_code=409)

    if resolution_method not in VALID_RESOLUTION_METHODS:
        raise ConflictResolutionError(f"Invalid resolution method: {resolution_method}")

    record = (
        db.query(MonthlyAttendance)
        .filter(
            MonthlyAttendance.company_id == conflict.company_id,
            MonthlyAttendance.year == conflict.year,
            MonthlyAttendance.month == conflict.month,
            MonthlyAttendance.employee_id == conflict.employee_id,
        )
        .first()
    )
    if not record:
        raise ConflictResolutionError(
            f"No attendance record for employee_id={conflict.employee_id}",
            status_code=404,
        )

    final_value = _resolve_value(conflict, resolution_method, resolved_value)
    now = datetime.utcnow()

    apply_field_value(record, conflict.field_name, final_value)
    record.last_manual_edit = now
    record.updated_at = now

    conflict.status = "resolved"
    conflict.resolution_method = resolution_method
    conflict.resolved_value = final_value
    conflict.resolved_by = resolved_by
    conflict.resolved_at = now

    manual_change = (
        db.query(ManualChange)
        .filter(
            ManualChange.company_id == conflict.company_id,
            ManualChange.year == conflict.year,
            ManualChange.month == conflict.month,
            ManualChange.employee_id == conflict.employee_id,
            ManualChange.field_name == conflict.field_name,
        )
        .order_by(ManualChange.change_timestamp.desc())
        .first()
    )
    if manual_change:
        manual_change.merged_to_truth = True
        manual_change.merged_at = now

    if record_version and user:
        _record_version_history(
            db,
            company_id=conflict.company_id,
            year=conflict.year,
            month=conflict.month,
            user=user,
            resolution_method=resolution_method,
            resolved_conflicts=[conflict],
        )

    logger.info(
        "Conflict resolved: id=%s employee_id=%s field=%s method=%s",
        conflict.id,
        conflict.employee_id,
        conflict.field_name,
        resolution_method,
    )
    return conflict


def _get_conflict(db: Session, company_id: int, conflict_id: int) -> Conflict:
    conflict = (
        db.query(Conflict)
        .filter(Conflict.id == conflict_id, Conflict.company_id == company_id)
        .first()
    )
    if not conflict:
        raise ConflictResolutionError(f"Conflict {conflict_id} not found", status_code=404)
    return conflict


def resolve_single_conflict(
    db: Session,
    *,
    company_id: int,
    conflict_id: int,
    resolution_method: str,
    resolved_by: int,
    resolved_value: Optional[str],
    user: User,
) -> Conflict:
    conflict = _get_conflict(db, company_id, conflict_id)
    resolved = resolve_conflict(
        db,
        conflict,
        resolution_method=resolution_method,
        resolved_by=resolved_by,
        resolved_value=resolved_value,
        record_version=True,
        user=user,
    )
    db.commit()
    return resolved


def resolve_conflicts_batch(
    db: Session,
    *,
    company_id: int,
    conflict_ids: List[int],
    resolution_method: str,
    resolved_by: int,
    resolved_value: Optional[str],
    user: User,
) -> List[Conflict]:
    if not conflict_ids:
        raise ConflictResolutionError("conflict_ids must not be empty")

    resolved: List[Conflict] = []
    for conflict_id in conflict_ids:
        conflict = _get_conflict(db, company_id, conflict_id)
        resolved.append(
            resolve_conflict(
                db,
                conflict,
                resolution_method=resolution_method,
                resolved_by=resolved_by,
                resolved_value=resolved_value,
                record_version=False,
                user=None,
            )
        )

    grouped: dict[tuple[int, int], List[Conflict]] = {}
    for conflict in resolved:
        key = (conflict.year, conflict.month)
        grouped.setdefault(key, []).append(conflict)

    for (group_year, group_month), group_conflicts in grouped.items():
        _record_version_history(
            db,
            company_id=company_id,
            year=group_year,
            month=group_month,
            user=user,
            resolution_method=resolution_method,
            resolved_conflicts=group_conflicts,
        )

    db.commit()
    return resolved


def auto_resolve_conflicts(
    db: Session,
    *,
    company_id: int,
    user: User,
    year: Optional[int] = None,
    month: Optional[int] = None,
) -> List[Conflict]:
    query = db.query(Conflict).filter(
        Conflict.company_id == company_id,
        Conflict.status == "pending",
    )
    if year is not None:
        query = query.filter(Conflict.year == year)
    if month is not None:
        query = query.filter(Conflict.month == month)

    pending = query.order_by(Conflict.created_at.asc()).all()
    if not pending:
        return []

    resolved: List[Conflict] = []
    skipped = 0
    grouped: dict[tuple[int, int], List[Conflict]] = {}

    for conflict in pending:
        priority = get_conflict_priority(user, conflict.field_name)
        if priority == PRIORITY_ASK:
            skipped += 1
            continue

        method = PRIORITY_TO_RESOLUTION[priority]
        resolved_conflict = resolve_conflict(
            db,
            conflict,
            resolution_method=method,
            resolved_by=user.id,
            resolved_value=None,
            record_version=False,
            user=None,
        )
        resolved.append(resolved_conflict)
        key = (conflict.year, conflict.month)
        grouped.setdefault(key, []).append(resolved_conflict)

    for (group_year, group_month), group_conflicts in grouped.items():
        _record_version_history(
            db,
            company_id=company_id,
            year=group_year,
            month=group_month,
            user=user,
            resolution_method="auto_resolve",
            resolved_conflicts=group_conflicts,
        )

    db.commit()
    logger.info(
        "Auto-resolve complete: company_id=%s resolved=%s skipped=%s pending=%s",
        company_id,
        len(resolved),
        skipped,
        count_pending_conflicts(db, company_id),
    )
    return resolved
