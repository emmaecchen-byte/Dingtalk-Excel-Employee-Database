"""
Build rows for the 情况说明 sheet — matches the web UI 情况说明 tab.

The UI shows one row per employee with anomalies, using ``anomaly_summary`` text
(e.g. ``迟到1天、缺卡2天``) and a date derived from daily attendance status.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from app.excel.field_utils import get_field_value
from app.models import MonthlyAttendance

SITUATION_ANOMALY_KEYWORDS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("absenteeism", ("旷工",)),
    ("lateness", ("迟到",)),
    ("missing_punch", ("缺卡", "未打卡")),
)


@dataclass
class SituationRow:
    name: str
    date: str
    anomaly: str
    supplement_submitted: str
    notes: str


def has_explanation_anomaly(record: MonthlyAttendance) -> bool:
    """Same filter as the web UI ``explanationRows`` helper."""
    return (
        record.absenteeism_count > 0
        or record.lateness_count > 0
        or record.missing_punch_count > 0
    )


def _active_anomaly_categories(record: MonthlyAttendance) -> List[str]:
    categories: List[str] = []
    if (record.absenteeism_count or 0) > 0:
        categories.append("absenteeism")
    if (record.lateness_count or 0) > 0:
        categories.append("lateness")
    if (record.missing_punch_count or 0) > 0:
        categories.append("missing_punch")
    return categories


def _day_matches_category(status_text: str, category: str) -> bool:
    value = (status_text or "").strip()
    if not value:
        return False
    keywords = dict(SITUATION_ANOMALY_KEYWORDS).get(category, ())
    return any(keyword in value for keyword in keywords)


def situation_explanation_date(
    record: MonthlyAttendance,
    year: int,
    month: int,
) -> Optional[str]:
    """
    Pick the 情况说明 date for one employee.

    - Exactly one anomaly category (旷工 / 迟到 / 缺卡): first day in the month
      with that category in the daily status text.
    - Multiple categories: leave blank (``None``).
    """
    categories = _active_anomaly_categories(record)
    if len(categories) != 1:
        return None

    category = categories[0]
    days_in_month = calendar.monthrange(year, month)[1]
    for day in range(1, days_in_month + 1):
        value = get_field_value(record, f"day_{day}")
        if _day_matches_category(value, category):
            return f"{year}-{month:02d}-{day:02d}"
    return None


def collect_situation_rows(
    records: Sequence[MonthlyAttendance],
    year: int,
    month: int,
) -> List[SituationRow]:
    """
    Return 情况说明 rows identical to the web UI explanation sheet.

    One row per employee with any 旷工 / 迟到 / 缺卡 counts, using stored
    ``anomaly_summary`` combined text and ``situation_explanation_date``.
    """
    rows: List[SituationRow] = []

    for record in records:
        if not has_explanation_anomaly(record):
            continue

        employee = record.employee
        anomaly_date = situation_explanation_date(record, year, month) or ""

        rows.append(
            SituationRow(
                name=employee.name,
                date=anomaly_date,
                anomaly=record.anomaly_summary or "",
                supplement_submitted="Y" if record.supplement_submitted else "",
                notes=record.notes or "",
            )
        )

    return rows
