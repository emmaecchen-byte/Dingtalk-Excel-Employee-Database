"""CRUD helpers for attendance period upload pipeline."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app.crud.base import CRUDBase
from app.models import AttendancePeriod, DailyAttendance, Employee, EmployeeAttendance


class CRUDAttendancePeriod(CRUDBase[AttendancePeriod]):
    def get_by_company_period(
        self,
        db: Session,
        company_id: int,
        year: int,
        month: int,
        *,
        status: Optional[str] = None,
    ) -> Optional[AttendancePeriod]:
        query = db.query(AttendancePeriod).filter(
            AttendancePeriod.company_id == company_id,
            AttendancePeriod.year == year,
            AttendancePeriod.month == month,
        )
        if status:
            query = query.filter(AttendancePeriod.status == status)
        return query.order_by(AttendancePeriod.id.desc()).first()

    def get_with_details(self, db: Session, period_id: int) -> Optional[AttendancePeriod]:
        return (
            db.query(AttendancePeriod)
            .options(
                joinedload(AttendancePeriod.employee_rows).joinedload(EmployeeAttendance.daily_records),
                joinedload(AttendancePeriod.employee_rows).joinedload(EmployeeAttendance.employee),
            )
            .filter(AttendancePeriod.id == period_id)
            .first()
        )


class CRUDEmployeeAttendance(CRUDBase[EmployeeAttendance]):
    def get_by_period(self, db: Session, period_id: int) -> List[EmployeeAttendance]:
        return (
            db.query(EmployeeAttendance)
            .filter(EmployeeAttendance.period_id == period_id)
            .order_by(EmployeeAttendance.row_index)
            .all()
        )


class CRUDDailyAttendance(CRUDBase[DailyAttendance]):
    def bulk_create(self, db: Session, records: List[DailyAttendance]) -> None:
        db.add_all(records)
        db.flush()


attendance_period = CRUDAttendancePeriod(AttendancePeriod)
employee_attendance = CRUDEmployeeAttendance(EmployeeAttendance)
daily_attendance = CRUDDailyAttendance(DailyAttendance)


def match_employee_by_name(db: Session, company_id: int, employee_name: str) -> Optional[Employee]:
    return (
        db.query(Employee)
        .filter(
            Employee.company_id == company_id,
            Employee.is_active.is_(True),
            Employee.name == employee_name,
        )
        .first()
    )
