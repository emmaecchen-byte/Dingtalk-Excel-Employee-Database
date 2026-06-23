"""
Build attendance sheet view payloads for the web UI (签字 / 月度汇总 / 加班结算 / 情况说明).
"""

from __future__ import annotations

import calendar
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from app.excel.field_utils import get_overtime_day_hours
from app.excel.template_generator import SIGN_LEGEND_SYMBOLS, count_month_work_days

# Web 签字 tab counts all legend symbols (including 婚假 ML); Excel keeps 9 COUNTIF columns.
WEB_SIGN_COUNT_SYMBOLS = tuple(symbol for symbol, _ in SIGN_LEGEND_SYMBOLS)
from app.models import Company, MonthlyAttendance
from app.excel.monthly_status_display import format_monthly_summary_day_status
from app.services.excel_generator import (
    first_anomaly_date,
    map_sign_sheet_status,
    resolve_day_value,
)
from app.services.sync_counts import count_pending_conflicts, count_pending_updates


def _count_sign_symbols(morning_values: List[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {symbol: 0 for symbol in WEB_SIGN_COUNT_SYMBOLS}
    for value in morning_values:
        if value in counts:
            counts[value] += 1
    return counts


def _build_sign_day_rows(
    record: MonthlyAttendance,
    year: int,
    month: int,
) -> tuple[List[str], List[str]]:
    """Build identical 上午 / 下午 symbol rows for the web 签字 preview."""
    days_in_month = calendar.monthrange(year, month)[1]
    morning: List[str] = []
    afternoon: List[str] = []

    for day in range(1, 32):
        if day > days_in_month:
            morning.append("")
            afternoon.append("")
            continue

        symbol = map_sign_sheet_status(resolve_day_value(record, day))
        morning.append(symbol)
        afternoon.append(symbol)

    return morning, afternoon


def _employee_sheet_row(record: MonthlyAttendance, year: int, month: int) -> dict:
    employee = record.employee
    days_in_month = calendar.monthrange(year, month)[1]

    days: List[str] = []
    for day in range(1, 32):
        if day > days_in_month:
            days.append("")
            continue
        display = format_monthly_summary_day_status(
            record,
            year,
            month,
            day,
            resolve_day_value=resolve_day_value,
        )
        days.append(display or "")

    morning, afternoon = _build_sign_day_rows(record, year, month)
    sign_counts = _count_sign_symbols(morning[:days_in_month])
    present_days = sign_counts.get("√", 0)
    work_days = count_month_work_days(year, month)

    overtime_days: List[float] = []
    for day in range(1, 32):
        if day > days_in_month:
            overtime_days.append(0.0)
            continue
        hours = get_overtime_day_hours(record, day)
        overtime_days.append(float(hours) if hours else 0.0)

    return {
        "id": employee.id,
        "name": employee.name,
        "department": employee.department or "",
        "position": employee.position,
        "employee_code": employee.employee_code,
        "days": days,
        "morning": morning,
        "afternoon": afternoon,
        "overtime_days": overtime_days,
        "sign_counts": sign_counts,
        "absent_days": max(work_days - present_days, 0),
        "work_days": work_days,
        "total_attendance_days": record.total_attendance_days,
        "absenteeism_count": record.absenteeism_count,
        "lateness_count": record.lateness_count,
        "missing_punch_count": record.missing_punch_count,
        "anomaly_summary": record.anomaly_summary,
        "supplement_submitted": record.supplement_submitted,
        "notes": record.notes,
        "first_anomaly_date": first_anomaly_date(record, year, month),
    }


def build_attendance_sheets(
    db: Session,
    company_id: int,
    year: int,
    month: int,
) -> dict:
    company = db.query(Company).filter(Company.id == company_id).first()
    records = (
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

    if not records:
        raise ValueError(f"No attendance data for {year}-{month:02d}")

    employees = [_employee_sheet_row(record, year, month) for record in records]
    last_sync = max(
        (record.last_sync_from_dingtalk for record in records if record.last_sync_from_dingtalk),
        default=None,
    )

    return {
        "company_name": company.name if company else "",
        "year": year,
        "month": month,
        "generated_at": datetime.utcnow(),
        "last_sync": last_sync,
        "work_days": count_month_work_days(year, month),
        "stats": {
            "total_employees": len(employees),
            "total_absenteeism_days": sum(item["absenteeism_count"] for item in employees),
            "total_lateness_days": sum(item["lateness_count"] for item in employees),
            "total_missing_punch_days": sum(item["missing_punch_count"] for item in employees),
            "pending_conflicts": count_pending_conflicts(db, company_id),
            "pending_updates": count_pending_updates(db, company_id),
        },
        "employees": employees,
    }
