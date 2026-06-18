"""
Two-step Excel workflow helpers:
1) DingTalk original monthly summary upload
2) Generate full 4-sheet workbook from uploaded monthly data
"""

from __future__ import annotations

import calendar
import os
import tempfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Sequence

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.excel.template_generator import TemplateEmployee
from app.models import Employee, User
from app.services.excel_generator import (
    ExcelExportResult,
    ExcelGeneratorError,
    load_workbook_from_template,
    populate_workbook,
)
from app.services.excel_parser import ExcelParserError, ParsedWorkbook, parse_uploaded_workbook

UPLOAD_CHUNK_SIZE = 1024 * 1024


class ExcelWorkflowError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def _save_upload_to_tempfile(upload: UploadFile) -> str:
    suffix = ".xlsx"
    if upload.filename and upload.filename.lower().endswith(".xlsm"):
        suffix = ".xlsm"
    fd, temp_path = tempfile.mkstemp(prefix="dingtalk_source_", suffix=suffix)
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


def _has_keyword(value: str, keywords: Sequence[str]) -> bool:
    return any(keyword in value for keyword in keywords)


def _build_summary(absenteeism_count: int, lateness_count: int, missing_punch_count: int) -> str:
    items: List[str] = []
    if lateness_count > 0:
        items.append(f"迟到{lateness_count}天")
    if missing_punch_count > 0:
        items.append(f"缺卡{missing_punch_count}天")
    if absenteeism_count > 0:
        items.append(f"旷工{absenteeism_count}天")
    return "、".join(items)


def _build_import_records(
    parsed: ParsedWorkbook,
    employees_by_name: Dict[str, Employee],
    year: int,
    month: int,
):
    days_in_month = calendar.monthrange(year, month)[1]
    records = []

    for row in parsed.employees:
        employee = employees_by_name.get(row.name)
        employee_payload = SimpleNamespace(
            name=row.name,
            department=employee.department if employee else "",
            position=employee.position if employee else "",
            employee_code=employee.employee_code if employee else "",
        )
        record = SimpleNamespace(
            employee=employee_payload,
            manual_overrides={},
            total_attendance_days=0,
            total_personal_leave=0.0,
            total_sick_leave=0.0,
            total_annual_leave=0.0,
            total_compensatory_leave=0.0,
            total_overtime_hours=0.0,
            absenteeism_count=0,
            lateness_count=0,
            missing_punch_count=0,
            anomaly_summary="",
            supplement_submitted=False,
            notes="",
            last_sync_from_dingtalk=datetime.utcnow(),
        )

        attendance_days = 0
        for day in range(1, 32):
            field_name = f"day_{day}"
            value = (row.daily_status.get(field_name) or "").strip()
            setattr(record, field_name, value or None)
            setattr(record, f"overtime_day_{day}", None)

            if day > days_in_month or not value:
                continue
            if _has_keyword(value, ("旷工",)):
                record.absenteeism_count += 1
            if _has_keyword(value, ("迟到",)):
                record.lateness_count += 1
            if _has_keyword(value, ("缺卡", "未打卡")):
                record.missing_punch_count += 1
            if not _has_keyword(value, ("旷工", "休息", "请假")):
                attendance_days += 1

        record.total_attendance_days = attendance_days
        record.anomaly_summary = _build_summary(
            record.absenteeism_count,
            record.lateness_count,
            record.missing_punch_count,
        )
        records.append(record)

    return records


async def generate_full_excel_from_dingtalk_upload(
    db: Session,
    user: User,
    year: int,
    month: int,
    upload: UploadFile,
) -> ExcelExportResult:
    if not upload.filename or not upload.filename.lower().endswith((".xlsx", ".xlsm")):
        raise ExcelWorkflowError("File must be an Excel workbook (.xlsx)")
    if month < 1 or month > 12:
        raise ExcelWorkflowError("Month must be between 1 and 12")

    temp_path = await _save_upload_to_tempfile(upload)
    try:
        try:
            parsed = parse_uploaded_workbook(temp_path, year=year, month=month)
        except ExcelParserError as exc:
            raise ExcelWorkflowError(exc.message, status_code=exc.status_code) from exc
        except Exception as exc:
            raise ExcelWorkflowError(
                "Invalid or malformed Excel file. Ensure it contains a 月度汇总 worksheet."
            ) from exc

        employees = (
            db.query(Employee)
            .filter(
                Employee.company_id == user.company_id,
                Employee.is_active.is_(True),
            )
            .all()
        )
        employees_by_name = {item.name: item for item in employees}
        records = _build_import_records(parsed, employees_by_name, year, month)
        if not records:
            raise ExcelWorkflowError("No employee rows found in uploaded 月度汇总")

        template_employees = [
            TemplateEmployee(
                name=record.employee.name,
                department=record.employee.department,
                position=record.employee.position,
                employee_code=record.employee.employee_code,
            )
            for record in records
        ]
        workbook = load_workbook_from_template(year, month, template_employees)
        populate_workbook(workbook, records, year, month, generated_at=datetime.utcnow())

        fd, temp_output = tempfile.mkstemp(prefix="attendance_from_dingtalk_", suffix=".xlsx")
        os.close(fd)
        output_path = Path(temp_output)
        workbook.save(output_path)
        return ExcelExportResult(
            path=output_path,
            filename=f"attendance_full_{year}_{month:02d}.xlsx",
            year=year,
            month=month,
            employee_count=len(records),
        )
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
