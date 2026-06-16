"""
Manual change tracking: persist edits and optionally merge into monthly_attendance.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.excel.field_utils import apply_field_value
from app.models import ManualChange, MonthlyAttendance

logger = logging.getLogger(__name__)


class ChangeTrackerError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def track_manual_change(
    db: Session,
    *,
    company_id: int,
    year: int,
    month: int,
    employee_id: int,
    field_name: str,
    old_value: Optional[str],
    new_value: Optional[str],
    snapshot_id: Optional[int],
    change_source: str,
    changed_by: int,
    merged_to_truth: bool = False,
    commit: bool = False,
) -> ManualChange:
    """
    Create a manual_changes record and optionally apply the new value to monthly_attendance.
    """
    if month < 1 or month > 12:
        raise ChangeTrackerError("Month must be between 1 and 12")

    now = datetime.utcnow()
    manual_change = ManualChange(
        company_id=company_id,
        year=year,
        month=month,
        employee_id=employee_id,
        snapshot_id=snapshot_id,
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
        change_source=change_source,
        change_timestamp=now,
        changed_by=changed_by,
        merged_to_truth=merged_to_truth,
        merged_at=now if merged_to_truth else None,
    )
    db.add(manual_change)

    if merged_to_truth:
        record = (
            db.query(MonthlyAttendance)
            .options(joinedload(MonthlyAttendance.employee))
            .filter(
                MonthlyAttendance.company_id == company_id,
                MonthlyAttendance.year == year,
                MonthlyAttendance.month == month,
                MonthlyAttendance.employee_id == employee_id,
            )
            .first()
        )
        if not record:
            raise ChangeTrackerError(
                f"No attendance record for employee_id={employee_id} in {year}-{month:02d}",
                status_code=404,
            )

        apply_field_value(record, field_name, new_value)
        record.last_manual_edit = now
        record.updated_at = now

        logger.info(
            "Manual change merged to truth: employee_id=%s field=%s source=%s",
            employee_id,
            field_name,
            change_source,
        )

    db.flush()

    if commit:
        db.commit()
        db.refresh(manual_change)

    return manual_change
