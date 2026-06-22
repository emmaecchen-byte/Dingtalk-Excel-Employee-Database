from typing import List, Optional

from sqlalchemy.orm import Session

from app.crud.attendance_period import (
    attendance_period,
    employee_attendance,
    match_employee_by_name,
)
from app.crud.daily_attendance import daily_attendance
from app.crud.base import CRUDBase
from app.models import (
    AttendancePeriod,
    Company,
    Conflict,
    DailyAttendance,
    Employee,
    EmployeeAttendance,
    ExcelSnapshot,
    ManualChange,
    MonthlyAttendance,
    User,
    VersionHistory,
)


class CRUDCompany(CRUDBase[Company]):
    def get_by_dingtalk_corp_id(self, db: Session, dingtalk_corp_id: str) -> Optional[Company]:
        return db.query(Company).filter(Company.dingtalk_corp_id == dingtalk_corp_id).first()


class CRUDEmployee(CRUDBase[Employee]):
    def get_by_company(self, db: Session, company_id: int, active_only: bool = True) -> List[Employee]:
        query = db.query(Employee).filter(Employee.company_id == company_id)
        if active_only:
            query = query.filter(Employee.is_active.is_(True))
        return query.order_by(Employee.name).all()

    def get_by_dingtalk_user_id(
        self,
        db: Session,
        company_id: int,
        dingtalk_user_id: str,
    ) -> Optional[Employee]:
        return (
            db.query(Employee)
            .filter(
                Employee.company_id == company_id,
                Employee.dingtalk_user_id == dingtalk_user_id,
            )
            .first()
        )


class CRUDMonthlyAttendance(CRUDBase[MonthlyAttendance]):
    def get_by_period(
        self,
        db: Session,
        company_id: int,
        year: int,
        month: int,
    ) -> List[MonthlyAttendance]:
        return (
            db.query(MonthlyAttendance)
            .filter(
                MonthlyAttendance.company_id == company_id,
                MonthlyAttendance.year == year,
                MonthlyAttendance.month == month,
            )
            .all()
        )

    def get_for_employee(
        self,
        db: Session,
        company_id: int,
        year: int,
        month: int,
        employee_id: int,
    ) -> Optional[MonthlyAttendance]:
        return (
            db.query(MonthlyAttendance)
            .filter(
                MonthlyAttendance.company_id == company_id,
                MonthlyAttendance.year == year,
                MonthlyAttendance.month == month,
                MonthlyAttendance.employee_id == employee_id,
            )
            .first()
        )


class CRUDExcelSnapshot(CRUDBase[ExcelSnapshot]):
    def get_by_period(
        self,
        db: Session,
        company_id: int,
        year: int,
        month: int,
    ) -> List[ExcelSnapshot]:
        return (
            db.query(ExcelSnapshot)
            .filter(
                ExcelSnapshot.company_id == company_id,
                ExcelSnapshot.year == year,
                ExcelSnapshot.month == month,
            )
            .order_by(ExcelSnapshot.snapshot_version.desc())
            .all()
        )


class CRUDManualChange(CRUDBase[ManualChange]):
    def get_by_period(
        self,
        db: Session,
        company_id: int,
        year: int,
        month: int,
    ) -> List[ManualChange]:
        return (
            db.query(ManualChange)
            .filter(
                ManualChange.company_id == company_id,
                ManualChange.year == year,
                ManualChange.month == month,
            )
            .order_by(ManualChange.change_timestamp.desc())
            .all()
        )


class CRUDConflict(CRUDBase[Conflict]):
    def get_pending(
        self,
        db: Session,
        company_id: int,
        year: int,
        month: int,
    ) -> List[Conflict]:
        return (
            db.query(Conflict)
            .filter(
                Conflict.company_id == company_id,
                Conflict.year == year,
                Conflict.month == month,
                Conflict.status == "pending",
            )
            .all()
        )


class CRUDVersionHistory(CRUDBase[VersionHistory]):
    def get_by_period(
        self,
        db: Session,
        company_id: int,
        year: int,
        month: int,
    ) -> List[VersionHistory]:
        return (
            db.query(VersionHistory)
            .filter(
                VersionHistory.company_id == company_id,
                VersionHistory.year == year,
                VersionHistory.month == month,
            )
            .order_by(VersionHistory.version_number.desc())
            .all()
        )


class CRUDUser(CRUDBase[User]):
    def get_by_email(self, db: Session, email: str) -> Optional[User]:
        return db.query(User).filter(User.email == email).first()

    def get_by_company(self, db: Session, company_id: int) -> List[User]:
        return db.query(User).filter(User.company_id == company_id).order_by(User.name).all()


company = CRUDCompany(Company)
employee = CRUDEmployee(Employee)
monthly_attendance = CRUDMonthlyAttendance(MonthlyAttendance)
excel_snapshot = CRUDExcelSnapshot(ExcelSnapshot)
manual_change = CRUDManualChange(ManualChange)
conflict = CRUDConflict(Conflict)
version_history = CRUDVersionHistory(VersionHistory)
user = CRUDUser(User)

__all__ = [
    "company",
    "employee",
    "monthly_attendance",
    "excel_snapshot",
    "manual_change",
    "conflict",
    "version_history",
    "user",
    "attendance_period",
    "employee_attendance",
    "daily_attendance",
    "match_employee_by_name",
]
