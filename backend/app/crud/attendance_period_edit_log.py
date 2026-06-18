"""CRUD helpers for attendance period cell edit audit logs."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.models import AttendancePeriodEditLog


class CRUDAttendancePeriodEditLog(CRUDBase[AttendancePeriodEditLog]):
    def log_change(
        self,
        db: Session,
        *,
        period_id: int,
        daily_attendance_id: Optional[int],
        employee_name: Optional[str],
        edited_by: Optional[int],
        editor_name: Optional[str],
        field_name: str,
        old_value: Optional[str],
        new_value: Optional[str],
    ) -> AttendancePeriodEditLog:
        entry = AttendancePeriodEditLog(
            period_id=period_id,
            daily_attendance_id=daily_attendance_id,
            employee_name=employee_name,
            edited_by=edited_by,
            editor_name=editor_name,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
        )
        db.add(entry)
        db.flush()
        return entry

    def list_for_period(self, db: Session, period_id: int, *, limit: int = 200) -> List[AttendancePeriodEditLog]:
        return (
            db.query(AttendancePeriodEditLog)
            .filter(AttendancePeriodEditLog.period_id == period_id)
            .order_by(AttendancePeriodEditLog.edited_at.desc())
            .limit(limit)
            .all()
        )


attendance_period_edit_log = CRUDAttendancePeriodEditLog(AttendancePeriodEditLog)
