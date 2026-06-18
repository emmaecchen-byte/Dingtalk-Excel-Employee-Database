"""
Orchestrate DingTalk Excel upload: parse, validate, persist attendance period data.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.crud.attendance_period import attendance_period, match_employee_by_name
from app.models import AttendancePeriod, DailyAttendance, EmployeeAttendance, User
from app.services.dingtalk_attendance_parser import (
    DingTalkParserError,
    ParsedDingTalkWorkbook,
    ValidationIssue,
    ValidationSeverity,
    parse_dingtalk_workbook,
)
from app.services.attendance_rule_engine import load_company_rules

logger = logging.getLogger(__name__)

UPLOAD_CHUNK_SIZE = 1024 * 1024


class AttendanceUploadError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass
class AttendanceUploadResult:
    period_id: int
    year: int
    month: int
    status: str
    employee_count: int
    daily_record_count: int
    requires_review_count: int
    validation_issues: List[dict]
    has_blocking_errors: bool
    persisted: bool


async def _save_upload_to_tempfile(upload: UploadFile) -> str:
    if not upload.filename or not upload.filename.lower().endswith(".xlsx"):
        raise AttendanceUploadError("File must be an Excel workbook (.xlsx)")

    fd, temp_path = tempfile.mkstemp(prefix="attendance_upload_", suffix=".xlsx")
    os.close(fd)
    try:
        with open(temp_path, "wb") as handle:
            while True:
                chunk = await upload.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                handle.write(chunk)
        return temp_path
    except Exception:
        os.unlink(temp_path)
        raise


def _validation_summary(parsed: ParsedDingTalkWorkbook) -> dict:
    return {
        "error_count": parsed.error_count,
        "warning_count": parsed.warning_count,
        "info_count": parsed.info_count,
        "has_blocking_errors": parsed.has_blocking_errors,
        "issues": [issue.to_dict() for issue in parsed.issues],
    }


def _get_or_create_draft_period(
    db: Session,
    *,
    company_id: int,
    year: int,
    month: int,
    source_filename: str,
    uploaded_by: int,
    validation_summary: dict,
) -> AttendancePeriod:
    existing = (
        db.query(AttendancePeriod)
        .filter(
            AttendancePeriod.company_id == company_id,
            AttendancePeriod.year == year,
            AttendancePeriod.month == month,
            AttendancePeriod.status.in_(("draft", "validated", "failed")),
        )
        .order_by(AttendancePeriod.id.desc())
        .first()
    )
    if existing:
        existing.source_filename = source_filename
        existing.uploaded_by = uploaded_by
        existing.validation_summary = validation_summary
        existing.updated_at = datetime.utcnow()
        db.flush()
        db.query(EmployeeAttendance).filter(EmployeeAttendance.period_id == existing.id).delete()
        db.flush()
        return existing

    period = AttendancePeriod(
        company_id=company_id,
        year=year,
        month=month,
        status="draft",
        data_source="upload",
        source_filename=source_filename,
        uploaded_by=uploaded_by,
        validation_summary=validation_summary,
    )
    db.add(period)
    db.flush()
    return period


def _persist_parsed_rows(
    db: Session,
    *,
    period: AttendancePeriod,
    company_id: int,
    parsed: ParsedDingTalkWorkbook,
) -> tuple[int, int, int]:
    employee_count = 0
    daily_record_count = 0
    requires_review_count = 0

    for employee_row in parsed.employees:
        matched_employee = match_employee_by_name(db, company_id, employee_row.employee_name)
        employee_record = EmployeeAttendance(
            period_id=period.id,
            employee_id=matched_employee.id if matched_employee else None,
            employee_name=employee_row.employee_name,
            row_index=employee_row.row_index,
            requires_review=employee_row.requires_review,
        )
        db.add(employee_record)
        db.flush()

        if employee_row.requires_review:
            requires_review_count += 1

        for cell in employee_row.daily_cells:
            if not cell.raw_text and not cell.morning_status and not cell.afternoon_status:
                continue
            db.add(
                DailyAttendance(
                    employee_attendance_id=employee_record.id,
                    day=cell.day,
                    raw_text=cell.raw_text or None,
                    morning_status=cell.morning_status,
                    afternoon_status=cell.afternoon_status,
                    requires_review=cell.requires_review,
                )
            )
            daily_record_count += 1
            if cell.requires_review:
                requires_review_count += 1

        employee_count += 1

    return employee_count, daily_record_count, requires_review_count


async def handle_attendance_upload(
    db: Session,
    user: User,
    upload: UploadFile,
    *,
    fallback_year: Optional[int] = None,
    fallback_month: Optional[int] = None,
) -> AttendanceUploadResult:
    temp_path = await _save_upload_to_tempfile(upload)
    try:
        try:
            parsed = parse_dingtalk_workbook(
                temp_path,
                fallback_year=fallback_year,
                fallback_month=fallback_month,
                attendance_rules=load_company_rules(db, user.company_id),
            )
        except DingTalkParserError as exc:
            raise AttendanceUploadError(exc.message, status_code=exc.status_code) from exc

        validation_summary = _validation_summary(parsed)
        period = _get_or_create_draft_period(
            db,
            company_id=user.company_id,
            year=parsed.year,
            month=parsed.month,
            source_filename=upload.filename or "upload.xlsx",
            uploaded_by=user.id,
            validation_summary=validation_summary,
        )

        persisted = False
        employee_count = 0
        daily_record_count = 0
        requires_review_count = 0

        if not parsed.has_blocking_errors:
            employee_count, daily_record_count, requires_review_count = _persist_parsed_rows(
                db,
                period=period,
                company_id=user.company_id,
                parsed=parsed,
            )
            period.status = "draft"
            persisted = True
            from app.services.exception_detection import detect_exceptions_for_period

            detect_exceptions_for_period(db, period.id, user.company_id)
        else:
            period.status = "failed"

        period.validation_summary = {
            **validation_summary,
            "employee_count": employee_count,
            "daily_record_count": daily_record_count,
            "requires_review_count": requires_review_count,
            "persisted": persisted,
        }
        period.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(period)

        logger.info(
            "Attendance upload processed period_id=%s status=%s employees=%s daily=%s review=%s",
            period.id,
            period.status,
            employee_count,
            daily_record_count,
            requires_review_count,
        )

        return AttendanceUploadResult(
            period_id=period.id,
            year=parsed.year,
            month=parsed.month,
            status=period.status,
            employee_count=employee_count,
            daily_record_count=daily_record_count,
            requires_review_count=requires_review_count,
            validation_issues=[issue.to_dict() for issue in parsed.issues],
            has_blocking_errors=parsed.has_blocking_errors,
            persisted=persisted,
        )
    except AttendanceUploadError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Attendance upload failed for user_id=%s", user.id)
        raise AttendanceUploadError("Failed to process attendance upload") from exc
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
