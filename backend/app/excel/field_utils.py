"""Shared helpers for reading and writing monthly_attendance fields."""

from __future__ import annotations

from typing import Any, Optional

from app.models import MonthlyAttendance

BOOL_TRUE = frozenset({"true", "1", "y", "yes", "是"})
BOOL_FALSE = frozenset({"false", "0", "n", "no", "否", ""})


def normalize_numeric_value(value: Any) -> str:
    text = normalize_value(value)
    if text in {"", "false"}:
        return "0"
    try:
        float(text)
        return text
    except (TypeError, ValueError):
        return "0"


def normalize_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip()
    lower = text.lower()
    if lower in BOOL_TRUE:
        return "true"
    if lower in BOOL_FALSE:
        return "false"
    return text


def get_field_value(record: MonthlyAttendance, field_name: str) -> str:
    if field_name.startswith("day_"):
        overrides = record.manual_overrides or {}
        if field_name in overrides and overrides[field_name] is not None:
            return normalize_value(overrides[field_name])
        return normalize_value(getattr(record, field_name, None))

    value = getattr(record, field_name, None)
    if value is None and field_name in (record.manual_overrides or {}):
        return normalize_value(record.manual_overrides[field_name])
    return normalize_value(value)


def apply_field_value(record: MonthlyAttendance, field_name: str, raw_value: Any) -> None:
    if field_name == "supplement_submitted":
        setattr(record, field_name, normalize_value(raw_value) == "true")
        return
    if field_name in {
        "total_attendance_days",
        "absenteeism_count",
        "lateness_count",
        "missing_punch_count",
    }:
        try:
            setattr(record, field_name, int(float(raw_value or 0)))
        except (TypeError, ValueError):
            setattr(record, field_name, 0)
        return
    if field_name in {
        "total_personal_leave",
        "total_sick_leave",
        "total_annual_leave",
        "total_compensatory_leave",
        "total_overtime_hours",
    }:
        try:
            setattr(record, field_name, round(float(raw_value or 0), 1))
        except (TypeError, ValueError):
            setattr(record, field_name, 0.0)
        return
    if field_name.startswith("day_"):
        setattr(record, field_name, str(raw_value) if raw_value is not None else None)
        return
    setattr(record, field_name, str(raw_value) if raw_value is not None else None)


def snapshot_field_value(employee_snapshot: dict, field_name: str) -> str:
    if field_name.startswith("day_"):
        daily = employee_snapshot.get("daily_status") or {}
        return normalize_value(daily.get(field_name, ""))
    if field_name == "total_overtime_hours":
        return normalize_numeric_value(employee_snapshot.get(field_name, 0))
    return normalize_value(employee_snapshot.get(field_name))
