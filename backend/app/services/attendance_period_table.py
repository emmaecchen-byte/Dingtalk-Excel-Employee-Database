"""Build and update attendance period table payloads for the interactive grid."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session, joinedload

from app.excel.template_generator import SIGN_COUNT_SYMBOLS, count_month_work_days
from app.services.audit_log import log_daily_attendance_change
from app.crud.daily_attendance import daily_attendance
from app.models import AttendancePeriod, DailyAttendance, EmployeeAttendance, User
from app.services.attendance_rule_engine import (
    ResolvedAttendanceRule,
    apply_rule_to_totals,
    build_status_options,
    load_company_rules,
    map_status_to_symbol,
    match_rule,
)
from app.services.period_workflow import PeriodWorkflowError, assert_period_editable

SYMBOL_PRESENT = "√"
SYMBOL_PERSONAL = "◇"
SYMBOL_COMP = "✬"
SYMBOL_TRIP = "▼"
SYMBOL_SICK = "※"
SYMBOL_WELFARE = "●"
SYMBOL_ANNUAL = "AL"
SYMBOL_MATERNITY = "○"
SYMBOL_FUNERAL = "FL"
SYMBOL_MARRIAGE = "ML"

SYMBOL_TO_TOTAL_KEY = {
    SYMBOL_PRESENT: "present",
    SYMBOL_PERSONAL: "personal_leave",
    SYMBOL_COMP: "compensatory_leave",
    SYMBOL_TRIP: "business_trip",
    SYMBOL_SICK: "sick_leave",
    SYMBOL_WELFARE: "welfare_leave",
    SYMBOL_ANNUAL: "annual_leave",
    SYMBOL_MATERNITY: "maternity_leave",
    SYMBOL_FUNERAL: "funeral_leave",
    SYMBOL_MARRIAGE: "marriage_leave",
}

STATUS_OPTIONS = [
    {"value": "正常", "symbol": SYMBOL_PRESENT},
    {"value": "事假", "symbol": SYMBOL_PERSONAL},
    {"value": "调休", "symbol": SYMBOL_COMP},
    {"value": "出差", "symbol": SYMBOL_TRIP},
    {"value": "病假", "symbol": SYMBOL_SICK},
    {"value": "福利假", "symbol": SYMBOL_WELFARE},
    {"value": "年假", "symbol": SYMBOL_ANNUAL},
    {"value": "产假", "symbol": SYMBOL_MATERNITY},
    {"value": "丧假", "symbol": SYMBOL_FUNERAL},
    {"value": "婚假", "symbol": SYMBOL_MARRIAGE},
    {"value": "旷工", "symbol": "旷工"},
    {"value": "迟到", "symbol": "迟到"},
    {"value": "缺卡", "symbol": "缺卡"},
    {"value": "休息", "symbol": ""},
]


class AttendanceTableError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _empty_totals() -> Dict[str, int]:
    return {
        "present": 0,
        "personal_leave": 0,
        "compensatory_leave": 0,
        "business_trip": 0,
        "sick_leave": 0,
        "welfare_leave": 0,
        "annual_leave": 0,
        "maternity_leave": 0,
        "funeral_leave": 0,
        "marriage_leave": 0,
        "absenteeism": 0,
        "lateness": 0,
        "missing_punch": 0,
        "work_days": 0,
        "absent_days": 0,
    }


def status_to_symbol(status: Optional[str], rules: Sequence[ResolvedAttendanceRule]) -> str:
    return map_status_to_symbol(status or "", rules)


def combine_raw_text(morning: Optional[str], afternoon: Optional[str]) -> str:
    am = (morning or "").strip()
    pm = (afternoon or "").strip()
    if am and pm and am == pm:
        return am
    if am and pm:
        return f"{am}/{pm}"
    return am or pm


def _count_symbol(symbol: str, totals: Dict[str, int]) -> None:
    key = SYMBOL_TO_TOTAL_KEY.get(symbol)
    if key:
        totals[key] += 1


def _count_from_rule(rule: ResolvedAttendanceRule, totals: Dict[str, int]) -> None:
    apply_rule_to_totals(totals, rule)


def compute_row_totals(
    daily_by_day: Dict[int, DailyAttendance],
    *,
    year: int,
    month: int,
    shift: str,
    rules: Sequence[ResolvedAttendanceRule],
) -> Dict[str, int]:
    totals = _empty_totals()
    days_in_month = calendar.monthrange(year, month)[1]
    totals["work_days"] = count_month_work_days(year, month)

    for day in range(1, days_in_month + 1):
        record = daily_by_day.get(day)
        if not record:
            continue
        status = record.morning_status if shift == "morning" else record.afternoon_status
        if not status:
            continue
        matched = match_rule(status, rules)
        if matched:
            _count_from_rule(matched, totals)
            continue
        symbol = status_to_symbol(status, rules)
        if symbol == "旷工":
            totals["absenteeism"] += 1
        elif symbol == "迟到":
            totals["lateness"] += 1
        elif symbol == "缺卡":
            totals["missing_punch"] += 1
        elif symbol:
            _count_symbol(symbol, totals)

    totals["absent_days"] = max(totals["work_days"] - totals["present"], 0)
    return totals


def compute_employee_totals(
    daily_by_day: Dict[int, DailyAttendance],
    *,
    year: int,
    month: int,
    rules: Sequence[ResolvedAttendanceRule],
) -> Dict[str, int]:
    morning = compute_row_totals(daily_by_day, year=year, month=month, shift="morning", rules=rules)
    afternoon = compute_row_totals(daily_by_day, year=year, month=month, shift="afternoon", rules=rules)
    combined = _empty_totals()
    for key in combined:
        combined[key] = morning.get(key, 0) + afternoon.get(key, 0)
    combined["work_days"] = morning["work_days"]
    combined["absent_days"] = max(combined["work_days"] - combined["present"], 0)
    return combined


def _day_cell(
    record: Optional[DailyAttendance],
    *,
    shift: str,
    rules: Sequence[ResolvedAttendanceRule],
) -> dict:
    if not record:
        return {
            "daily_id": None,
            "day": None,
            "raw_text": "",
            "status": "",
            "symbol": "",
            "requires_review": False,
        }
    status = record.morning_status if shift == "morning" else record.afternoon_status
    symbol = status_to_symbol(status, rules)
    return {
        "daily_id": record.id,
        "day": record.day,
        "raw_text": record.raw_text or "",
        "status": status or "",
        "symbol": symbol,
        "requires_review": record.requires_review,
    }


def get_period_for_company(db: Session, period_id: int, company_id: int) -> AttendancePeriod:
    period = (
        db.query(AttendancePeriod)
        .filter(AttendancePeriod.id == period_id, AttendancePeriod.company_id == company_id)
        .first()
    )
    if not period:
        raise AttendanceTableError("Attendance period not found", status_code=404)
    return period


def build_period_table(
    db: Session,
    *,
    period_id: int,
    company_id: int,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    period = get_period_for_company(db, period_id, company_id)
    days_in_month = calendar.monthrange(period.year, period.month)[1]
    rules = load_company_rules(db, company_id)
    status_options = build_status_options(rules)

    base_query = (
        db.query(EmployeeAttendance)
        .options(joinedload(EmployeeAttendance.daily_records), joinedload(EmployeeAttendance.employee))
        .filter(EmployeeAttendance.period_id == period.id)
        .order_by(EmployeeAttendance.row_index, EmployeeAttendance.id)
    )
    total_employees = base_query.count()
    offset = max(page - 1, 0) * page_size
    employee_rows = base_query.offset(offset).limit(page_size).all()

    employees_payload: List[dict] = []
    for employee_row in employee_rows:
        daily_by_day = {item.day: item for item in employee_row.daily_records}
        employee_totals = compute_employee_totals(
            daily_by_day, year=period.year, month=period.month, rules=rules
        )
        department = employee_row.employee.department if employee_row.employee else ""

        shift_rows = []
        for shift, label in (("morning", "上午"), ("afternoon", "下午")):
            days = [
                _day_cell(daily_by_day.get(day), shift=shift, rules=rules)
                for day in range(1, days_in_month + 1)
            ]
            shift_rows.append(
                {
                    "shift": shift,
                    "shift_label": label,
                    "days": days,
                    "totals": compute_row_totals(
                        daily_by_day,
                        year=period.year,
                        month=period.month,
                        shift=shift,
                        rules=rules,
                    ),
                }
            )

        employees_payload.append(
            {
                "employee_attendance_id": employee_row.id,
                "employee_id": employee_row.employee_id,
                "employee_name": employee_row.employee_name,
                "department": department,
                "requires_review": employee_row.requires_review,
                "rows": shift_rows,
                "totals": employee_totals,
            }
        )

    return {
        "period_id": period.id,
        "year": period.year,
        "month": period.month,
        "days_in_month": days_in_month,
        "status": period.status,
        "is_editable": period.status != "archived",
        "is_read_only": period.status == "archived",
        "total_employees": total_employees,
        "page": page,
        "page_size": page_size,
        "status_options": status_options,
        "employees": employees_payload,
    }


def get_daily_for_company(db: Session, daily_id: int, company_id: int) -> DailyAttendance:
    record = daily_attendance.get_for_company(db, daily_id, company_id)
    if not record:
        raise AttendanceTableError("Daily attendance record not found", status_code=404)
    return record


def patch_daily_cell(
    db: Session,
    *,
    daily_id: int,
    company_id: int,
    shift: str,
    status: str,
    user: Optional[User] = None,
) -> dict:
    if shift not in {"morning", "afternoon"}:
        raise AttendanceTableError("shift must be 'morning' or 'afternoon'")

    record = get_daily_for_company(db, daily_id, company_id)
    employee_row = (
        db.query(EmployeeAttendance)
        .options(joinedload(EmployeeAttendance.daily_records), joinedload(EmployeeAttendance.employee))
        .filter(EmployeeAttendance.id == record.employee_attendance_id)
        .first()
    )
    if not employee_row:
        raise AttendanceTableError("Employee attendance row not found", status_code=404)

    period = get_period_for_company(db, employee_row.period_id, company_id)
    try:
        assert_period_editable(period)
    except PeriodWorkflowError as exc:
        raise AttendanceTableError(exc.message, status_code=exc.status_code) from exc

    rules = load_company_rules(db, company_id)
    normalized = status.strip()
    if shift == "morning":
        old_value = record.morning_status
    else:
        old_value = record.afternoon_status
    old_text = (old_value or "").strip()
    if old_text == normalized:
        symbol = status_to_symbol(normalized, rules)
        morning_symbol = status_to_symbol(record.morning_status, rules)
        afternoon_symbol = status_to_symbol(record.afternoon_status, rules)
        daily_by_day = {item.day: item for item in employee_row.daily_records}
        return {
            "daily_id": record.id,
            "day": record.day,
            "shift": shift,
            "status": normalized,
            "symbol": symbol,
            "morning_status": record.morning_status or "",
            "afternoon_status": record.afternoon_status or "",
            "morning_symbol": morning_symbol,
            "afternoon_symbol": afternoon_symbol,
            "raw_text": record.raw_text or "",
            "requires_review": record.requires_review,
            "employee_attendance_id": employee_row.id,
            "employee_requires_review": employee_row.requires_review,
            "row_totals": compute_row_totals(
                daily_by_day,
                year=period.year,
                month=period.month,
                shift=shift,
                rules=rules,
            ),
            "employee_totals": compute_employee_totals(
                daily_by_day, year=period.year, month=period.month, rules=rules
            ),
        }

    matched = match_rule(normalized, rules)
    symbol = status_to_symbol(normalized, rules)
    requires_review = matched is None and bool(normalized)

    daily_attendance.update_shift_status(
        record,
        shift=shift,
        status=normalized,
        requires_review=requires_review,
    )
    record.raw_text = combine_raw_text(record.morning_status, record.afternoon_status) or None

    daily_by_day = {item.day: item for item in employee_row.daily_records}
    daily_by_day[record.day] = record
    employee_row.requires_review = any(item.requires_review for item in daily_by_day.values())
    period.updated_at = datetime.utcnow()

    field_name = f"day_{record.day}_{shift}"
    log_daily_attendance_change(
        db,
        period_id=period.id,
        company_id=company_id,
        daily_attendance_id=record.id,
        employee_name=employee_row.employee_name,
        user=user,
        field_name=field_name,
        old_value=old_text or None,
        new_value=normalized or None,
    )

    db.commit()
    db.refresh(record)
    db.refresh(employee_row)

    employee_totals = compute_employee_totals(
        daily_by_day, year=period.year, month=period.month, rules=rules
    )
    morning_symbol = status_to_symbol(record.morning_status, rules)
    afternoon_symbol = status_to_symbol(record.afternoon_status, rules)

    return {
        "daily_id": record.id,
        "day": record.day,
        "shift": shift,
        "status": normalized,
        "symbol": symbol,
        "morning_status": record.morning_status or "",
        "afternoon_status": record.afternoon_status or "",
        "morning_symbol": morning_symbol,
        "afternoon_symbol": afternoon_symbol,
        "raw_text": record.raw_text or "",
        "requires_review": record.requires_review,
        "employee_attendance_id": employee_row.id,
        "employee_requires_review": employee_row.requires_review,
        "row_totals": compute_row_totals(
            daily_by_day,
            year=period.year,
            month=period.month,
            shift=shift,
            rules=rules,
        ),
        "employee_totals": employee_totals,
    }
