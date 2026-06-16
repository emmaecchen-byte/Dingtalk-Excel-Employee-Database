"""
Inline web UI updates to monthly_attendance with conflict detection.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional, Set

from sqlalchemy.orm import Session

from app.excel.field_utils import apply_field_value, get_field_value, normalize_value
from app.models import ManualChange, MonthlyAttendance, User
from app.services.conflict_detection import detect_conflicts

logger = logging.getLogger(__name__)

EDITABLE_FIELDS = frozenset(
    {
        "total_attendance_days",
        "absenteeism_count",
        "lateness_count",
        "missing_punch_count",
        "supplement_submitted",
        "notes",
    }
)


class AttendanceUpdateError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _mark_manual_override(record: MonthlyAttendance, field_name: str, value: str) -> None:
    overrides = dict(record.manual_overrides or {})
    overrides[field_name] = value
    record.manual_overrides = overrides


def _manual_override_fields(record: MonthlyAttendance) -> Set[str]:
    return set((record.manual_overrides or {}).keys())


def patch_employee_attendance(
    db: Session,
    *,
    company_id: int,
    year: int,
    month: int,
    employee_id: int,
    field_name: str,
    new_value: Any,
    user: User,
) -> Dict[str, Any]:
    if month < 1 or month > 12:
        raise AttendanceUpdateError("Month must be between 1 and 12")

    if field_name not in EDITABLE_FIELDS:
        raise AttendanceUpdateError(f"Field '{field_name}' is not editable")

    record = (
        db.query(MonthlyAttendance)
        .filter(
            MonthlyAttendance.company_id == company_id,
            MonthlyAttendance.year == year,
            MonthlyAttendance.month == month,
            MonthlyAttendance.employee_id == employee_id,
        )
        .first()
    )
    if not record:
        raise AttendanceUpdateError("Attendance record not found", status_code=404)

    normalized_new = normalize_value(new_value)
    old_value = get_field_value(record, field_name)

    if normalize_value(old_value) == normalized_new:
        return {
            "success": True,
            "conflict_detected": False,
            "conflict_id": None,
            "field_name": field_name,
            "old_value": old_value,
            "new_value": normalized_new,
            "manual_override_fields": sorted(_manual_override_fields(record)),
        }

    now = datetime.utcnow()
    manual_change = ManualChange(
        company_id=company_id,
        year=year,
        month=month,
        employee_id=employee_id,
        field_name=field_name,
        old_value=old_value,
        new_value=normalized_new,
        change_source="web_ui",
        change_timestamp=now,
        changed_by=user.id,
    )
    db.add(manual_change)
    db.flush()

    conflict_result = detect_conflicts(
        db,
        company_id,
        year,
        month,
        [manual_change],
        user=user,
        attendance_by_employee_id={employee_id: record},
        baseline_timestamp=record.last_manual_edit,
        auto_apply_resolutions=False,
    )

    conflict_id = conflict_result.conflicts[0].id if conflict_result.conflicts else None
    conflict_detected = conflict_id is not None

    if not conflict_detected:
        apply_field_value(record, field_name, normalized_new)
        _mark_manual_override(record, field_name, normalized_new)
        record.last_manual_edit = now
        record.updated_at = now
        manual_change.merged_to_truth = True
        manual_change.merged_at = now

    db.commit()
    db.refresh(record)

    logger.info(
        "Attendance patched: user_id=%s employee_id=%s field=%s conflict=%s",
        user.id,
        employee_id,
        field_name,
        conflict_detected,
    )

    return {
        "success": True,
        "conflict_detected": conflict_detected,
        "conflict_id": conflict_id,
        "field_name": field_name,
        "old_value": old_value,
        "new_value": normalized_new if not conflict_detected else old_value,
        "manual_override_fields": sorted(_manual_override_fields(record)),
    }
