"""
Build rows for the 情况说明 sheet — matches the web UI 情况说明 tab.

The UI shows one row per employee with anomalies, using ``anomaly_summary`` text
(e.g. ``迟到、旷工2天``) and ``first_anomaly_date`` from the monthly_attendance record.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Sequence

from app.models import MonthlyAttendance


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


def collect_situation_rows(
    records: Sequence[MonthlyAttendance],
    year: int,
    month: int,
    *,
    first_anomaly_date: Callable[[MonthlyAttendance, int, int], str | None],
) -> List[SituationRow]:
    """
    Return 情况说明 rows identical to the web UI explanation sheet.

    One row per employee with any 旷工 / 迟到 / 缺卡 counts, using stored
    ``anomaly_summary`` combined text and the first anomaly date in the month.
    """
    rows: List[SituationRow] = []
    month_fallback = f"{year}-{month:02d}-01"

    for record in records:
        if not has_explanation_anomaly(record):
            continue

        employee = record.employee
        anomaly_date = first_anomaly_date(record, year, month) or month_fallback

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
