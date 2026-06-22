"""
Parse DingTalk monthly-summary uploads and generate the full 4-sheet workbook.

Pipeline:
  1. Parse uploaded .xlsx (月度汇总 sheet) with openpyxl
  2. Map DingTalk status text → attendance symbols via company rules
  3. Detect anomalies (旷工 / 迟到 / 缺卡)
  4. Generate 签字 / 情况说明 / 月度汇总 / 加班结算加班工资 from master template
"""

from __future__ import annotations

import calendar
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional, Sequence, Tuple

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.excel.template_generator import TemplateEmployee
from app.models import Employee, User
from app.services.attendance_rule_engine import load_company_rules
from app.services.excel_generator import (
    ExcelExportResult,
    load_workbook_from_template,
    populate_workbook,
)
from app.services.excel_parser import ExcelParserError, ParsedWorkbook, parse_uploaded_workbook

logger = logging.getLogger(__name__)

UPLOAD_CHUNK_SIZE = 1024 * 1024

ANOMALY_KEYWORDS = {
    "absenteeism": ("旷工",),
    "lateness": ("迟到",),
    "missing_punch": ("缺卡", "未打卡"),
}


class ExcelConverterError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass
class ConverterAnomalyCounts:
    absenteeism: int = 0
    lateness: int = 0
    missing_punch: int = 0

    @property
    def has_anomaly(self) -> bool:
        return self.absenteeism > 0 or self.lateness > 0 or self.missing_punch > 0

    def to_summary(self) -> str:
        items: List[str] = []
        if self.lateness > 0:
            items.append(f"迟到{self.lateness}天")
        if self.missing_punch > 0:
            items.append(f"缺卡{self.missing_punch}天")
        if self.absenteeism > 0:
            items.append(f"旷工{self.absenteeism}天")
        return "、".join(items)


def _has_keyword(value: str, keywords: Sequence[str]) -> bool:
    return any(keyword in value for keyword in keywords)


def detect_anomalies_in_status(status_text: str) -> ConverterAnomalyCounts:
    """Detect 旷工 / 迟到 / 缺卡 in a single day's DingTalk status text."""
    text = (status_text or "").strip()
    if not text:
        return ConverterAnomalyCounts()
    return ConverterAnomalyCounts(
        absenteeism=1 if _has_keyword(text, ANOMALY_KEYWORDS["absenteeism"]) else 0,
        lateness=1 if _has_keyword(text, ANOMALY_KEYWORDS["lateness"]) else 0,
        missing_punch=1 if _has_keyword(text, ANOMALY_KEYWORDS["missing_punch"]) else 0,
    )


def aggregate_monthly_anomalies(
    daily_status: Dict[str, str],
    *,
    year: int,
    month: int,
) -> Tuple[ConverterAnomalyCounts, int]:
    """Sum anomaly counts across all days in the month; return attendance-day count."""
    days_in_month = calendar.monthrange(year, month)[1]
    totals = ConverterAnomalyCounts()
    attendance_days = 0

    for day in range(1, days_in_month + 1):
        value = (daily_status.get(f"day_{day}") or "").strip()
        if not value:
            continue
        day_anomalies = detect_anomalies_in_status(value)
        totals.absenteeism += day_anomalies.absenteeism
        totals.lateness += day_anomalies.lateness
        totals.missing_punch += day_anomalies.missing_punch
        if not _has_keyword(value, ("旷工", "休息", "请假")):
            attendance_days += 1

    return totals, attendance_days


def _resolve_period(
    parsed: ParsedWorkbook,
    *,
    year: Optional[int],
    month: Optional[int],
) -> Tuple[int, int]:
    resolved_year = year or parsed.year
    resolved_month = month or parsed.month
    if resolved_year is None or resolved_month is None:
        raise ExcelConverterError(
            "Could not determine year/month from the file. "
            "Pass year and month in the upload form or include them in the 月度汇总 title."
        )
    if resolved_month < 1 or resolved_month > 12:
        raise ExcelConverterError("Month must be between 1 and 12")
    if resolved_year < 2000 or resolved_year > 2100:
        raise ExcelConverterError("Year must be between 2000 and 2100")
    return resolved_year, resolved_month


def _build_converter_records(
    parsed: ParsedWorkbook,
    employees_by_name: Dict[str, Employee],
    *,
    year: int,
    month: int,
) -> List[SimpleNamespace]:
    records: List[SimpleNamespace] = []

    for row in parsed.employees:
        employee = employees_by_name.get(row.name)
        employee_payload = SimpleNamespace(
            name=row.name,
            department=employee.department if employee else "",
            position=employee.position if employee else "",
            employee_code=employee.employee_code if employee else "",
        )
        anomalies, attendance_days = aggregate_monthly_anomalies(
            row.daily_status,
            year=year,
            month=month,
        )
        record = SimpleNamespace(
            employee=employee_payload,
            manual_overrides={},
            total_attendance_days=attendance_days,
            total_personal_leave=0.0,
            total_sick_leave=0.0,
            total_annual_leave=0.0,
            total_compensatory_leave=0.0,
            total_overtime_hours=0.0,
            absenteeism_count=anomalies.absenteeism,
            lateness_count=anomalies.lateness,
            missing_punch_count=anomalies.missing_punch,
            anomaly_summary=anomalies.to_summary(),
            supplement_submitted=False,
            notes=row.notes or "",
            last_sync_from_dingtalk=datetime.utcnow(),
        )

        for day in range(1, 32):
            field_name = f"day_{day}"
            value = (row.daily_status.get(field_name) or "").strip()
            setattr(record, field_name, value or None)
            setattr(record, f"overtime_day_{day}", None)

        records.append(record)

    return records


async def _save_upload_to_tempfile(upload: UploadFile) -> str:
    suffix = ".xlsx"
    if upload.filename and upload.filename.lower().endswith(".xlsm"):
        suffix = ".xlsm"
    fd, temp_path = tempfile.mkstemp(prefix="dingtalk_convert_", suffix=suffix)
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


def _validate_upload(upload: UploadFile) -> None:
    if not upload.filename or not upload.filename.lower().endswith((".xlsx", ".xlsm")):
        raise ExcelConverterError("File must be an Excel workbook (.xlsx)")


async def convert_dingtalk_upload_to_workbook(
    db: Session,
    user: User,
    upload: UploadFile,
    *,
    year: Optional[int] = None,
    month: Optional[int] = None,
) -> ExcelExportResult:
    """
    Parse a DingTalk monthly-summary upload and return a generated 4-sheet workbook.

    Does not persist to the database — conversion only.
    """
    _validate_upload(upload)

    temp_path = await _save_upload_to_tempfile(upload)
    try:
        fallback_year = year or datetime.utcnow().year
        fallback_month = month or datetime.utcnow().month
        try:
            parsed = parse_uploaded_workbook(temp_path, year=fallback_year, month=fallback_month)
        except ExcelParserError as exc:
            raise ExcelConverterError(exc.message, status_code=exc.status_code) from exc
        except Exception as exc:
            raise ExcelConverterError(
                "Invalid or malformed Excel file. Ensure it contains a 月度汇总 worksheet."
            ) from exc

        resolved_year, resolved_month = _resolve_period(parsed, year=year, month=month)

        employees = (
            db.query(Employee)
            .filter(
                Employee.company_id == user.company_id,
                Employee.is_active.is_(True),
            )
            .all()
        )
        employees_by_name = {item.name: item for item in employees}
        records = _build_converter_records(
            parsed,
            employees_by_name,
            year=resolved_year,
            month=resolved_month,
        )
        if not records:
            raise ExcelConverterError("No employee rows found in uploaded 月度汇总")

        rules = load_company_rules(db, user.company_id)
        template_employees = [
            TemplateEmployee(
                name=record.employee.name,
                department=record.employee.department,
                position=record.employee.position,
                employee_code=record.employee.employee_code,
            )
            for record in records
        ]
        workbook = load_workbook_from_template(resolved_year, resolved_month, template_employees)
        populate_workbook(
            workbook,
            records,
            resolved_year,
            resolved_month,
            generated_at=datetime.utcnow(),
            rules=rules,
        )

        fd, temp_output = tempfile.mkstemp(prefix="attendance_converted_", suffix=".xlsx")
        os.close(fd)
        output_path = Path(temp_output)
        workbook.save(output_path)

        anomaly_rows = sum(1 for record in records if record.anomaly_summary)
        logger.info(
            "Converted DingTalk upload: company_id=%s period=%s-%02d employees=%s anomalies=%s",
            user.company_id,
            resolved_year,
            resolved_month,
            len(records),
            anomaly_rows,
        )

        return ExcelExportResult(
            path=output_path,
            filename=f"attendance_full_{resolved_year}_{resolved_month:02d}.xlsx",
            year=resolved_year,
            month=resolved_month,
            employee_count=len(records),
        )
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
