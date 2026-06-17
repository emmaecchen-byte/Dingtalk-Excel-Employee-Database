"""
Per-user DingTalk sync helpers invoked by real-time webhooks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import Company, Employee, MonthlyAttendance
from app.services.dingtalk_api import DingTalkAPIError, dingtalk_corp_client
from app.services.leave_overtime_sync import (
    _classify_leave,
    _collect_month_approvals,
    _daily_overtime_from_approvals,
    _daily_overtime_from_report,
    _format_api_datetime,
    _get_or_create_monthly_record,
    _minutes_to_hours,
    _parse_duration_to_hours,
    _sum_leave_hours_from_report,
    apply_daily_overtime,
    month_bounds,
)

logger = logging.getLogger(__name__)

TIME_RESULT_LABELS = {
    "Normal": "√",
    "Late": "迟到",
    "SeriousLate": "严重迟到",
    "Absenteeism": "旷工",
    "NotSigned": "缺卡",
    "Early": "早退",
}


@dataclass
class SyncFieldUpdate:
    field_name: str
    dingtalk_value: str
    previous_value: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_name": self.field_name,
            "dingtalk_value": self.dingtalk_value,
            "previous_value": self.previous_value,
        }


def _parse_work_date(work_date: str) -> tuple[int, int, int]:
    parts = work_date.strip().split("-")
    if len(parts) != 3:
        raise ValueError(f"Invalid work_date: {work_date}")
    return int(parts[0]), int(parts[1]), int(parts[2])


def _day_status_from_attendance_result(result: Dict[str, Any]) -> str:
    attendance_items = result.get("attendance_result_list") or []
    if not attendance_items:
        return "√"

    severity = {
        "Normal": 0,
        "Early": 1,
        "Late": 2,
        "SeriousLate": 3,
        "NotSigned": 4,
        "Absenteeism": 5,
    }
    worst = "Normal"
    worst_rank = -1
    for item in attendance_items:
        time_result = str(item.get("time_result") or "Normal")
        rank = severity.get(time_result, 1)
        if rank > worst_rank:
            worst_rank = rank
            worst = time_result
    return TIME_RESULT_LABELS.get(worst, worst)


def _field_updates_from_webhook_data(data: Dict[str, Any], work_date: str) -> List[SyncFieldUpdate]:
    """Use explicit field/value pairs from webhook payload when API is unavailable."""
    updates: List[SyncFieldUpdate] = []
    year, month, day = _parse_work_date(work_date)
    field_name = data.get("field_name") or data.get("fieldName") or f"day_{day}"
    value = data.get("value") or data.get("dingtalk_value") or data.get("new_value")
    if value is not None:
        updates.append(SyncFieldUpdate(field_name=field_name, dingtalk_value=str(value)))
        return updates

    fields = data.get("fields") or data.get("updates") or []
    for item in fields:
        name = item.get("field_name") or item.get("fieldName")
        field_value = item.get("value") or item.get("dingtalk_value")
        if name and field_value is not None:
            updates.append(SyncFieldUpdate(field_name=name, dingtalk_value=str(field_value)))
    if updates:
        return updates

    return [SyncFieldUpdate(field_name=f"day_{day}", dingtalk_value="√")]


def sync_attendance(
    db: Session,
    *,
    company: Company,
    employee: Employee,
    work_date: str,
    webhook_data: Optional[Dict[str, Any]] = None,
) -> List[SyncFieldUpdate]:
    """
    Sync a single employee's attendance for one calendar day.

    Pulls data from DingTalk ``getupdatedata`` when configured; otherwise uses
    values supplied in the webhook ``data`` payload (demo / push-only mode).
    """
    year, month, day = _parse_work_date(work_date)
    record = _get_or_create_monthly_record(db, company.id, employee.id, year, month)
    field_name = f"day_{day}"
    previous_value = getattr(record, field_name, None)
    previous_text = str(previous_value) if previous_value is not None else None

    dingtalk_value: Optional[str] = None
    if dingtalk_corp_client.is_configured() and employee.dingtalk_user_id:
        try:
            payload = dingtalk_corp_client.get_attendance_update_data(
                employee.dingtalk_user_id,
                work_date,
            )
            result = payload.get("result") or {}
            dingtalk_value = _day_status_from_attendance_result(result)
            logger.info(
                "Fetched attendance update for user=%s date=%s status=%s",
                employee.dingtalk_user_id,
                work_date,
                dingtalk_value,
            )
        except DingTalkAPIError as exc:
            logger.warning(
                "DingTalk attendance fetch failed for %s on %s: %s",
                employee.dingtalk_user_id,
                work_date,
                exc.message,
            )

    if dingtalk_value is None:
        fallback = _field_updates_from_webhook_data(webhook_data or {}, work_date)
        if fallback:
            for item in fallback:
                item.previous_value = previous_text
            return fallback
        dingtalk_value = "√"

    return [
        SyncFieldUpdate(
            field_name=field_name,
            dingtalk_value=dingtalk_value,
            previous_value=previous_text,
        )
    ]


def sync_leaves(
    db: Session,
    *,
    company: Company,
    employee: Employee,
    year: int,
    month: int,
    webhook_data: Optional[Dict[str, Any]] = None,
) -> List[SyncFieldUpdate]:
    """Sync leave totals for one employee for the given month."""
    if not employee.dingtalk_user_id:
        return []

    record = _get_or_create_monthly_record(db, company.id, employee.id, year, month)
    previous = {
        "total_personal_leave": record.total_personal_leave,
        "total_sick_leave": record.total_sick_leave,
        "total_annual_leave": record.total_annual_leave,
        "total_compensatory_leave": record.total_compensatory_leave,
    }

    totals = {"personal": 0.0, "sick": 0.0, "annual": 0.0, "compensatory": 0.0}
    from_date, to_date, _ = month_bounds(year, month)

    if dingtalk_corp_client.is_configured():
        approvals = _collect_month_approvals(employee.dingtalk_user_id, year, month, biz_type=3)
        for approval in approvals:
            begin = _format_api_datetime(approval.get("begin_time"))
            end = _format_api_datetime(approval.get("end_time"))
            category = _classify_leave(approval.get("sub_type"))
            if not category or not begin or not end:
                continue
            try:
                minutes = dingtalk_corp_client.get_leave_approval_duration(
                    employee.dingtalk_user_id,
                    begin,
                    end,
                )
                hours = _minutes_to_hours(minutes)
            except DingTalkAPIError as exc:
                logger.warning(
                    "Leave duration fetch failed for %s: %s",
                    employee.dingtalk_user_id,
                    exc.message,
                )
                hours = _parse_duration_to_hours(
                    approval.get("duration"),
                    approval.get("duration_unit"),
                )
            totals[category] = round(totals[category] + hours, 1)

        if not approvals:
            totals = _sum_leave_hours_from_report(employee.dingtalk_user_id, from_date, to_date)
    elif webhook_data:
        totals["personal"] = float(webhook_data.get("total_personal_leave") or 0)
        totals["sick"] = float(webhook_data.get("total_sick_leave") or 0)
        totals["annual"] = float(webhook_data.get("total_annual_leave") or 0)
        totals["compensatory"] = float(webhook_data.get("total_compensatory_leave") or 0)

    field_map = {
        "personal": "total_personal_leave",
        "sick": "total_sick_leave",
        "annual": "total_annual_leave",
        "compensatory": "total_compensatory_leave",
    }
    updates: List[SyncFieldUpdate] = []
    for key, field_name in field_map.items():
        new_value = str(round(totals[key], 1))
        old_value = previous[field_name]
        old_text = str(old_value) if old_value is not None else None
        if old_text != new_value:
            updates.append(
                SyncFieldUpdate(
                    field_name=field_name,
                    dingtalk_value=new_value,
                    previous_value=old_text,
                )
            )

    logger.info(
        "Leave sync for employee_id=%s period=%s-%02d produced %s field updates",
        employee.id,
        year,
        month,
        len(updates),
    )
    return updates


def sync_overtime(
    db: Session,
    *,
    company: Company,
    employee: Employee,
    year: int,
    month: int,
    webhook_data: Optional[Dict[str, Any]] = None,
) -> List[SyncFieldUpdate]:
    """Sync overtime totals for one employee for the given month."""
    if not employee.dingtalk_user_id:
        return []

    record = _get_or_create_monthly_record(db, company.id, employee.id, year, month)
    previous_total = str(record.total_overtime_hours or 0)
    from_date, to_date, _ = month_bounds(year, month)
    daily: Dict[int, float] = {}

    if dingtalk_corp_client.is_configured():
        approvals = _collect_month_approvals(employee.dingtalk_user_id, year, month, biz_type=1)
        daily = _daily_overtime_from_report(
            employee.dingtalk_user_id,
            from_date,
            to_date,
            year,
            month,
        )
        if not daily and approvals:
            daily = _daily_overtime_from_approvals(
                employee.dingtalk_user_id,
                approvals,
                year,
                month,
            )
    elif webhook_data:
        for day in range(1, 32):
            key = f"overtime_day_{day}"
            if key in webhook_data and webhook_data[key] is not None:
                daily[day] = float(webhook_data[key])

    new_total = apply_daily_overtime(record, daily, year, month)
    new_total_str = str(new_total)
    if previous_total != new_total_str:
        return [
            SyncFieldUpdate(
                field_name="total_overtime_hours",
                dingtalk_value=new_total_str,
                previous_value=previous_total,
            )
        ]

    logger.info(
        "Overtime sync for employee_id=%s period=%s-%02d produced no total change",
        employee.id,
        year,
        month,
    )
    return []
