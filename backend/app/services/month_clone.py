"""
Clone monthly attendance from a source period to a new target month.
"""

from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from app.excel.attendance_export import generate_attendance_excel, get_day_value
from app.excel.field_utils import get_overtime_day_hours
from app.models import MonthlyAttendance, User, VersionHistory
from app.services.snapshot_service import create_snapshot
from app.services.version_service import _next_version_number

logger = logging.getLogger(__name__)

BLANK_DAY_STATUS = "未签到"


class MonthCloneError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass
class CloneCopyOptions:
    copy_employees: bool = True
    keep_attendance_data: bool = False
    keep_formulas: bool = True
    keep_manual_notes: bool = True
    reset_anomalies: bool = True

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "CloneCopyOptions":
        return cls(
            copy_employees=bool(payload.get("copy_employees", True)),
            keep_attendance_data=bool(payload.get("keep_attendance_data", False)),
            keep_formulas=bool(payload.get("keep_formulas", True)),
            keep_manual_notes=bool(payload.get("keep_manual_notes", True)),
            reset_anomalies=bool(payload.get("reset_anomalies", True)),
        )


def _target_has_records(db: Session, company_id: int, year: int, month: int) -> bool:
    return (
        db.query(MonthlyAttendance.id)
        .filter(
            MonthlyAttendance.company_id == company_id,
            MonthlyAttendance.year == year,
            MonthlyAttendance.month == month,
        )
        .first()
        is not None
    )


def _load_source_records(
    db: Session,
    company_id: int,
    year: int,
    month: int,
) -> List[MonthlyAttendance]:
    return (
        db.query(MonthlyAttendance)
        .options(joinedload(MonthlyAttendance.employee))
        .filter(
            MonthlyAttendance.company_id == company_id,
            MonthlyAttendance.year == year,
            MonthlyAttendance.month == month,
        )
        .order_by(MonthlyAttendance.employee_id)
        .all()
    )


def _days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _apply_day_fields(
    target: MonthlyAttendance,
    source: MonthlyAttendance,
    *,
    target_year: int,
    target_month: int,
    keep_attendance_data: bool,
) -> None:
    target_days = _days_in_month(target_year, target_month)
    source_days = _days_in_month(source.year, source.month)
    overrides: Dict[str, Any] = {}

    if keep_attendance_data:
        for day in range(1, min(target_days, source_days) + 1):
            value = get_day_value(source, day)
            setattr(target, f"day_{day}", value or None)
        for day in range(source_days + 1, target_days + 1):
            setattr(target, f"day_{day}", BLANK_DAY_STATUS)
        for day in range(target_days + 1, 32):
            setattr(target, f"day_{day}", None)

        source_overrides = source.manual_overrides or {}
        for day in range(1, target_days + 1):
            field_name = f"day_{day}"
            if field_name in source_overrides:
                overrides[field_name] = source_overrides[field_name]
        target.manual_overrides = overrides
        target.total_attendance_days = int(source.total_attendance_days or 0)
        return

    for day in range(1, target_days + 1):
        setattr(target, f"day_{day}", BLANK_DAY_STATUS)
    for day in range(target_days + 1, 32):
        setattr(target, f"day_{day}", None)
    target.manual_overrides = {}
    target.total_attendance_days = 0


def _apply_overtime_day_fields(
    target: MonthlyAttendance,
    source: MonthlyAttendance,
    *,
    target_year: int,
    target_month: int,
    keep_attendance_data: bool,
    keep_formulas: bool,
) -> None:
    target_days = _days_in_month(target_year, target_month)
    source_days = _days_in_month(source.year, source.month)

    if keep_attendance_data and keep_formulas:
        for day in range(1, min(target_days, source_days) + 1):
            hours = get_overtime_day_hours(source, day)
            setattr(target, f"overtime_day_{day}", hours if hours else None)
        for day in range(min(target_days, source_days) + 1, target_days + 1):
            setattr(target, f"overtime_day_{day}", None)
        for day in range(target_days + 1, 32):
            setattr(target, f"overtime_day_{day}", None)
        target.total_overtime_hours = float(source.total_overtime_hours or 0)
        return

    for day in range(1, 32):
        setattr(target, f"overtime_day_{day}", None)
    target.total_overtime_hours = 0


def _apply_formula_fields(
    target: MonthlyAttendance,
    source: MonthlyAttendance,
    *,
    keep_attendance_data: bool,
    keep_formulas: bool,
) -> None:
    numeric_fields = [
        "total_personal_leave",
        "total_sick_leave",
        "total_annual_leave",
        "total_compensatory_leave",
    ]
    if keep_attendance_data and keep_formulas:
        for field in numeric_fields:
            setattr(target, field, getattr(source, field))
        return

    for field in numeric_fields:
        setattr(target, field, 0)


def _apply_notes_fields(
    target: MonthlyAttendance,
    source: MonthlyAttendance,
    *,
    keep_manual_notes: bool,
) -> None:
    if keep_manual_notes:
        target.notes = source.notes
        target.supplement_submitted = bool(source.supplement_submitted)
        return
    target.notes = None
    target.supplement_submitted = False


def _apply_anomaly_fields(
    target: MonthlyAttendance,
    source: MonthlyAttendance,
    *,
    reset_anomalies: bool,
) -> None:
    if reset_anomalies:
        target.absenteeism_count = 0
        target.lateness_count = 0
        target.missing_punch_count = 0
        target.anomaly_summary = None
        return

    target.absenteeism_count = int(source.absenteeism_count or 0)
    target.lateness_count = int(source.lateness_count or 0)
    target.missing_punch_count = int(source.missing_punch_count or 0)
    target.anomaly_summary = source.anomaly_summary


def _build_target_record(
    source: MonthlyAttendance,
    *,
    company_id: int,
    target_year: int,
    target_month: int,
    options: CloneCopyOptions,
    now: datetime,
) -> MonthlyAttendance:
    target = MonthlyAttendance(
        company_id=company_id,
        year=target_year,
        month=target_month,
        employee_id=source.employee_id,
        created_at=now,
        updated_at=now,
    )
    _apply_day_fields(
        target,
        source,
        target_year=target_year,
        target_month=target_month,
        keep_attendance_data=options.keep_attendance_data,
    )
    _apply_formula_fields(
        target,
        source,
        keep_attendance_data=options.keep_attendance_data,
        keep_formulas=options.keep_formulas,
    )
    _apply_overtime_day_fields(
        target,
        source,
        target_year=target_year,
        target_month=target_month,
        keep_attendance_data=options.keep_attendance_data,
        keep_formulas=options.keep_formulas,
    )
    _apply_notes_fields(target, source, keep_manual_notes=options.keep_manual_notes)
    _apply_anomaly_fields(target, source, reset_anomalies=options.reset_anomalies)
    target.last_sync_from_dingtalk = None
    target.last_manual_edit = now if options.keep_manual_notes or options.keep_attendance_data else None
    return target


def clone_month(
    db: Session,
    *,
    company_id: int,
    user: User,
    source_year: int,
    source_month: int,
    target_year: int,
    target_month: int,
    copy_options: CloneCopyOptions,
) -> Dict[str, Any]:
    for label, year, month in (
        ("source", source_year, source_month),
        ("target", target_year, target_month),
    ):
        if month < 1 or month > 12:
            raise MonthCloneError(f"{label.capitalize()} month must be between 1 and 12")
        if year < 2000 or year > 2100:
            raise MonthCloneError(f"{label.capitalize()} year must be between 2000 and 2100")

    if source_year == target_year and source_month == target_month:
        raise MonthCloneError("Source and target month must be different")

    if _target_has_records(db, company_id, target_year, target_month):
        raise MonthCloneError(
            f"Target month {target_year}-{target_month:02d} already has attendance data",
            status_code=409,
        )

    if not copy_options.copy_employees:
        raise MonthCloneError("copy_employees must be enabled to clone a month")

    source_records = _load_source_records(db, company_id, source_year, source_month)
    if not source_records:
        raise MonthCloneError(
            f"No attendance data for source month {source_year}-{source_month:02d}",
            status_code=404,
        )

    now = datetime.utcnow()
    employees_copied = 0
    first_target_record_id: Optional[int] = None

    for source in source_records:
        target_record = _build_target_record(
            source,
            company_id=company_id,
            target_year=target_year,
            target_month=target_month,
            options=copy_options,
            now=now,
        )
        db.add(target_record)
        db.flush()
        if first_target_record_id is None:
            first_target_record_id = target_record.id
        employees_copied += 1

    db.flush()

    snapshot_id: Optional[int] = None
    version_number: Optional[int] = None
    version_id: Optional[int] = None

    if employees_copied > 0:
        export_result = generate_attendance_excel(db, company_id, target_year, target_month)
        try:
            file_size = export_result.path.stat().st_size
            snapshot_id = create_snapshot(
                db,
                company_id,
                target_year,
                target_month,
                user.id,
                dingtalk_sync_timestamp=None,
                file_name=export_result.filename,
                file_size=file_size,
                record_version_history=False,
                commit=False,
            )
        finally:
            export_result.cleanup()

        version_number = _next_version_number(db, company_id, target_year, target_month)
        version = VersionHistory(
            company_id=company_id,
            year=target_year,
            month=target_month,
            version_number=version_number,
            created_by="month_clone",
            created_by_user_id=user.id,
            snapshot_id=snapshot_id,
            changes_summary={
                "event": "month_clone",
                "source_year": source_year,
                "source_month": source_month,
                "target_year": target_year,
                "target_month": target_month,
                "employees_copied": employees_copied,
                "copy_options": {
                    "copy_employees": copy_options.copy_employees,
                    "keep_attendance_data": copy_options.keep_attendance_data,
                    "keep_formulas": copy_options.keep_formulas,
                    "keep_manual_notes": copy_options.keep_manual_notes,
                    "reset_anomalies": copy_options.reset_anomalies,
                },
            },
            version_note=(
                f"Cloned from {source_year}-{source_month:02d} "
                f"({employees_copied} employees)"
            ),
        )
        db.add(version)
        db.flush()
        version_id = version.id

    db.commit()

    logger.info(
        "Month cloned: company_id=%s %s-%02d -> %s-%02d employees=%s version_id=%s",
        company_id,
        source_year,
        source_month,
        target_year,
        target_month,
        employees_copied,
        version_id,
    )

    return {
        "success": True,
        "target_month_id": version_id or first_target_record_id or 0,
        "employees_copied": employees_copied,
        "snapshot_id": snapshot_id,
        "version_number": version_number,
        "target_year": target_year,
        "target_month": target_month,
    }
