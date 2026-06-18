"""
Detect and merge attendance exceptions (spec sections 8.1, 8.2).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy.orm import Session, joinedload

from app.models import AbnormalRecord, AttendancePeriod, DailyAttendance, EmployeeAttendance
from app.services.attendance_rule_engine import (
    ResolvedAttendanceRule,
    load_company_rules,
    map_status_to_symbol,
    match_rule,
)

logger = logging.getLogger(__name__)

EXCEPTION_TYPES = (
    "absenteeism",
    "missing_punch",
    "late_arrival",
    "early_departure",
    "unrecognized",
    "conflicting",
)

EXCEPTION_LABELS = {
    "absenteeism": "旷工",
    "missing_punch": "缺卡",
    "late_arrival": "迟到",
    "early_departure": "早退",
    "unrecognized": "未识别状态",
    "conflicting": "冲突状态",
}

NORMAL_KEYWORDS = ("正常", "√", "出勤", "休息", "出差", "事假", "病假", "年假", "调休", "产假", "婚假", "丧假", "福利假", "外勤", "加班")


class ExceptionDetectionError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _format_date(year: int, month: int, day: int) -> str:
    return f"{year}-{month:02d}-{day:02d}"


def _is_normal_status(status: str) -> bool:
    text = status.strip()
    if not text:
        return True
    if text in {"√", "正常", "出勤"}:
        return True
    return any(keyword in text for keyword in NORMAL_KEYWORDS if keyword not in {"迟到", "缺卡", "旷工", "早退"})


def _classify_half_day(status: Optional[str], rules: Sequence[ResolvedAttendanceRule]) -> Set[str]:
    text = (status or "").strip()
    if not text:
        return set()

    types: Set[str] = set()
    matched = match_rule(text, rules)
    if matched and matched.is_abnormal:
        if matched.normalized_status == "旷工":
            types.add("absenteeism")
        if matched.normalized_status == "缺卡":
            types.add("missing_punch")
        if matched.normalized_status == "迟到":
            types.add("late_arrival")
    if "早退" in text:
        types.add("early_departure")
    if not types and matched is None:
        symbol = map_status_to_symbol(text, rules)
        if symbol == "旷工":
            types.add("absenteeism")
        elif symbol == "缺卡":
            types.add("missing_punch")
        elif symbol == "迟到":
            types.add("late_arrival")
    return types


def _is_conflicting(
    morning: Optional[str],
    afternoon: Optional[str],
    rules: Sequence[ResolvedAttendanceRule],
) -> bool:
    am = (morning or "").strip()
    pm = (afternoon or "").strip()
    if not am or not pm:
        return False
    if am == pm:
        return False

    am_types = _classify_half_day(am, rules)
    pm_types = _classify_half_day(pm, rules)
    if am_types != pm_types and (am_types or pm_types):
        return True

    am_normal = _is_normal_status(am)
    pm_normal = _is_normal_status(pm)
    if am_normal != pm_normal and not (am_normal and pm_normal):
        if am_types or pm_types or (not _is_normal_status(am) and not _is_normal_status(pm)):
            return True
    return False


def _detail_text(
    exception_type: str,
    *,
    morning: Optional[str],
    afternoon: Optional[str],
    raw_text: Optional[str],
) -> str:
    am = (morning or "").strip()
    pm = (afternoon or "").strip()
    label = EXCEPTION_LABELS.get(exception_type, exception_type)
    if exception_type == "conflicting":
        return f"上午:{am or '—'} / 下午:{pm or '—'}"
    if exception_type == "unrecognized":
        return raw_text or am or pm or label
    if am and pm and am != pm:
        return f"上午:{am} 下午:{pm}"
    return am or pm or label


def _scan_daily_record(
    record: DailyAttendance,
    *,
    year: int,
    month: int,
    rules: Sequence[ResolvedAttendanceRule],
) -> List[Tuple[str, dict]]:
    events: List[Tuple[str, dict]] = []
    date_str = _format_date(year, month, record.day)
    base_entry = {
        "day": record.day,
        "date": date_str,
        "morning": record.morning_status or "",
        "afternoon": record.afternoon_status or "",
        "raw_text": record.raw_text or "",
        "daily_id": record.id,
    }

    if record.requires_review:
        entry = {
            **base_entry,
            "detail": _detail_text(
                "unrecognized",
                morning=record.morning_status,
                afternoon=record.afternoon_status,
                raw_text=record.raw_text,
            ),
        }
        events.append(("unrecognized", entry))

    if _is_conflicting(record.morning_status, record.afternoon_status, rules):
        entry = {
            **base_entry,
            "detail": _detail_text(
                "conflicting",
                morning=record.morning_status,
                afternoon=record.afternoon_status,
                raw_text=record.raw_text,
            ),
        }
        events.append(("conflicting", entry))

    for shift, status in (
        ("morning", record.morning_status),
        ("afternoon", record.afternoon_status),
    ):
        for exc_type in _classify_half_day(status, rules):
            entry = {
                **base_entry,
                "shift": shift,
                "detail": _detail_text(
                    exc_type,
                    morning=record.morning_status,
                    afternoon=record.afternoon_status,
                    raw_text=record.raw_text,
                ),
            }
            events.append((exc_type, entry))

    return events


def _build_summary(exception_type: str, dates: List[dict]) -> str:
    label = EXCEPTION_LABELS.get(exception_type, exception_type)
    count = len(dates)
    if count == 1:
        return f"{label}（{dates[0]['date']}）"
    day_text = "、".join(item["date"][5:] for item in dates[:5])
    if count > 5:
        day_text += f" 等{count}天"
    return f"{label}{count}天（{day_text}）"


def detect_exceptions_for_period(db: Session, period_id: int, company_id: int) -> dict:
    period = (
        db.query(AttendancePeriod)
        .filter(AttendancePeriod.id == period_id, AttendancePeriod.company_id == company_id)
        .first()
    )
    if not period:
        raise ExceptionDetectionError("Attendance period not found", status_code=404)

    rules = load_company_rules(db, company_id)

    employee_rows = (
        db.query(EmployeeAttendance)
        .options(joinedload(EmployeeAttendance.daily_records))
        .filter(EmployeeAttendance.period_id == period.id)
        .order_by(EmployeeAttendance.row_index)
        .all()
    )

    merged: Dict[Tuple[int, str], dict] = defaultdict(
        lambda: {"dates": [], "employee_name": "", "employee_id": None, "employee_attendance_id": None}
    )

    for employee_row in employee_rows:
        for daily in employee_row.daily_records:
            for exc_type, entry in _scan_daily_record(
                daily, year=period.year, month=period.month, rules=rules
            ):
                key = (employee_row.id, exc_type)
                bucket = merged[key]
                bucket["employee_name"] = employee_row.employee_name
                bucket["employee_id"] = employee_row.employee_id
                bucket["employee_attendance_id"] = employee_row.id
                if not any(item["day"] == entry["day"] for item in bucket["dates"]):
                    bucket["dates"].append(entry)

    db.query(AbnormalRecord).filter(AbnormalRecord.period_id == period.id).delete()
    db.flush()

    created = 0
    for (_, exc_type), payload in merged.items():
        if not payload["dates"]:
            continue
        dates = sorted(payload["dates"], key=lambda item: item["day"])
        record = AbnormalRecord(
            company_id=company_id,
            period_id=period.id,
            employee_attendance_id=payload["employee_attendance_id"],
            employee_id=payload["employee_id"],
            employee_name=payload["employee_name"],
            exception_type=exc_type,
            summary=_build_summary(exc_type, dates),
            dates=dates,
            supplement_status="pending",
            notes=None,
        )
        db.add(record)
        created += 1

    period.updated_at = datetime.utcnow()
    db.flush()

    logger.info(
        "Detected %s abnormal records for period_id=%s company_id=%s",
        created,
        period.id,
        company_id,
    )
    return {
        "period_id": period.id,
        "year": period.year,
        "month": period.month,
        "records_created": created,
    }
