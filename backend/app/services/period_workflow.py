"""
Attendance period lifecycle: list, confirm, archive, delete draft.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.crud.attendance_period import attendance_period
from app.models import AbnormalRecord, AttendancePeriod, EmployeeAttendance, User

logger = logging.getLogger(__name__)

EDITABLE_STATUSES = frozenset({"draft", "validated", "confirmed", "failed"})
CONFIRMABLE_STATUSES = frozenset({"draft", "validated"})
ARCHIVABLE_STATUSES = frozenset({"confirmed"})
DELETABLE_STATUSES = frozenset({"draft", "failed"})

STATUS_LABELS = {
    "draft": "Draft",
    "validated": "Draft",
    "confirmed": "Confirmed",
    "archived": "Archived",
    "failed": "Draft",
    "published": "Confirmed",
}


class PeriodWorkflowError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def is_period_editable(period: AttendancePeriod) -> bool:
    return period.status in EDITABLE_STATUSES and period.status != "archived"


def is_period_read_only(period: AttendancePeriod) -> bool:
    return period.status == "archived"


def normalize_display_status(status: str) -> str:
    if status in {"draft", "validated", "failed"}:
        return "draft"
    if status == "published":
        return "confirmed"
    return status


def get_period_for_company_or_raise(
    db: Session,
    period_id: int,
    company_id: int,
) -> AttendancePeriod:
    period = (
        db.query(AttendancePeriod)
        .filter(AttendancePeriod.id == period_id, AttendancePeriod.company_id == company_id)
        .first()
    )
    if not period:
        raise PeriodWorkflowError("Attendance period not found", status_code=404)
    return period


def _period_counts(db: Session, period_id: int) -> tuple[int, int]:
    employee_count = (
        db.query(func.count(EmployeeAttendance.id))
        .filter(EmployeeAttendance.period_id == period_id)
        .scalar()
        or 0
    )
    exception_count = (
        db.query(func.count(AbnormalRecord.id))
        .filter(AbnormalRecord.period_id == period_id)
        .scalar()
        or 0
    )
    return int(employee_count), int(exception_count)


def _user_display_name(db: Session, user_id: Optional[int]) -> Optional[str]:
    if not user_id:
        return None
    user = db.query(User).filter(User.id == user_id).first()
    return user.name if user else None


def serialize_period_summary(db: Session, period: AttendancePeriod) -> dict:
    employee_count, exception_count = _period_counts(db, period.id)
    display_status = normalize_display_status(period.status)
    return {
        "id": period.id,
        "year": period.year,
        "month": period.month,
        "data_source": period.data_source or "upload",
        "employee_count": employee_count,
        "exception_count": exception_count,
        "status": period.status,
        "display_status": display_status,
        "is_editable": is_period_editable(period),
        "is_read_only": is_period_read_only(period),
        "created_at": period.created_at,
        "updated_at": period.updated_at,
        "confirmed_at": period.confirmed_at,
        "confirmed_by_name": _user_display_name(db, period.confirmed_by),
        "archived_at": period.archived_at,
        "archived_by_name": _user_display_name(db, period.archived_by),
        "source_filename": period.source_filename,
    }


def list_company_periods(
    db: Session,
    company_id: int,
    *,
    status: Optional[str] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
) -> List[dict]:
    query = db.query(AttendancePeriod).filter(AttendancePeriod.company_id == company_id)
    if year is not None:
        query = query.filter(AttendancePeriod.year == year)
    if month is not None:
        query = query.filter(AttendancePeriod.month == month)
    if status:
        if status == "draft":
            query = query.filter(AttendancePeriod.status.in_(("draft", "validated", "failed")))
        else:
            query = query.filter(AttendancePeriod.status == status)
    periods = query.order_by(
        AttendancePeriod.year.desc(),
        AttendancePeriod.month.desc(),
        AttendancePeriod.id.desc(),
    ).all()
    return [serialize_period_summary(db, period) for period in periods]


def confirm_period(db: Session, period_id: int, user: User) -> dict:
    period = get_period_for_company_or_raise(db, period_id, user.company_id)
    if period.status not in CONFIRMABLE_STATUSES:
        raise PeriodWorkflowError(
            f"Only draft periods can be confirmed (current status: {period.status})",
            status_code=400,
        )

    period.status = "confirmed"
    period.confirmed_by = user.id
    period.confirmed_at = datetime.utcnow()
    period.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(period)

    logger.info(
        "Period confirmed: period_id=%s company_id=%s user_id=%s",
        period.id,
        user.company_id,
        user.id,
    )
    return serialize_period_summary(db, period)


def archive_period(db: Session, period_id: int, user: User) -> dict:
    period = get_period_for_company_or_raise(db, period_id, user.company_id)
    if period.status not in ARCHIVABLE_STATUSES:
        raise PeriodWorkflowError(
            f"Only confirmed periods can be archived (current status: {period.status})",
            status_code=400,
        )

    period.status = "archived"
    period.archived_by = user.id
    period.archived_at = datetime.utcnow()
    period.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(period)

    logger.info(
        "Period archived: period_id=%s company_id=%s user_id=%s",
        period.id,
        user.company_id,
        user.id,
    )
    return serialize_period_summary(db, period)


def delete_draft_period(db: Session, period_id: int, company_id: int) -> None:
    period = get_period_for_company_or_raise(db, period_id, company_id)
    if period.status not in DELETABLE_STATUSES:
        raise PeriodWorkflowError(
            f"Only draft periods can be deleted (current status: {period.status})",
            status_code=400,
        )

    db.delete(period)
    db.commit()
    logger.info("Draft period deleted: period_id=%s company_id=%s", period_id, company_id)


def assert_period_editable(period: AttendancePeriod) -> None:
    if is_period_read_only(period):
        raise PeriodWorkflowError("Archived attendance records are read-only", status_code=403)
