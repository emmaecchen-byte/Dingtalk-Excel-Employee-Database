"""CRUD helpers for daily attendance cell updates."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.models import AttendancePeriod, DailyAttendance, EmployeeAttendance


class CRUDDailyAttendance(CRUDBase[DailyAttendance]):
    def bulk_create(self, db: Session, records: List[DailyAttendance]) -> None:
        db.add_all(records)
        db.flush()

    def get_for_company(self, db: Session, daily_id: int, company_id: int) -> Optional[DailyAttendance]:
        return (
            db.query(DailyAttendance)
            .join(EmployeeAttendance, DailyAttendance.employee_attendance_id == EmployeeAttendance.id)
            .join(AttendancePeriod, EmployeeAttendance.period_id == AttendancePeriod.id)
            .filter(
                DailyAttendance.id == daily_id,
                AttendancePeriod.company_id == company_id,
            )
            .first()
        )

    def update_shift_status(
        self,
        record: DailyAttendance,
        *,
        shift: str,
        status: Optional[str],
        requires_review: bool,
    ) -> DailyAttendance:
        normalized = (status or "").strip() or None
        if shift == "morning":
            record.morning_status = normalized
        elif shift == "afternoon":
            record.afternoon_status = normalized
        else:
            raise ValueError("shift must be 'morning' or 'afternoon'")
        record.requires_review = requires_review
        return record


daily_attendance = CRUDDailyAttendance(DailyAttendance)
