import logging
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Company, Employee, MonthlyAttendance
from app.services.dingtalk_api import DingTalkAPIError, dingtalk_corp_client

logger = logging.getLogger(__name__)

LEAVE_TYPE_MAP = {
    "事假": "personal",
    "病假": "sick",
    "年假": "annual",
    "调休": "compensatory",
}


@dataclass
class EmployeeLeaveTotals:
    employee_id: int
    name: str
    personal_leave_hours: float = 0.0
    sick_leave_hours: float = 0.0
    annual_leave_hours: float = 0.0
    compensatory_leave_hours: float = 0.0


@dataclass
class EmployeeOvertimeTotals:
    employee_id: int
    name: str
    overtime_hours: float = 0.0


@dataclass
class LeaveSyncSummary:
    employees_updated: int = 0
    employees: List[EmployeeLeaveTotals] = field(default_factory=list)
    message: str = ""


@dataclass
class OvertimeSyncSummary:
    employees_updated: int = 0
    employees: List[EmployeeOvertimeTotals] = field(default_factory=list)
    message: str = ""


def month_bounds(year: int, month: int) -> Tuple[str, str, int]:
    last_day = monthrange(year, month)[1]
    from_date = f"{year}-{month:02d}-01 00:00:00"
    to_date = f"{year}-{month:02d}-{last_day} 23:59:59"
    return from_date, to_date, last_day


def _format_api_datetime(value: object) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.utcfromtimestamp(value / 1000).strftime("%Y-%m-%d %H:%M:%S")
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 10:
        return f"{text} 00:00:00"
    return text.replace("T", " ")[:19]


def _minutes_to_hours(minutes: float) -> float:
    return round(minutes / 60.0, 1)


def _parse_duration_to_hours(duration: object, duration_unit: Optional[str]) -> float:
    try:
        amount = float(duration or 0)
    except (TypeError, ValueError):
        return 0.0
    unit = (duration_unit or "hour").lower()
    if unit in {"day", "percent_day"}:
        return round(amount * 8.0, 1)
    if unit in {"halfday", "half_day"}:
        return round(amount * 4.0, 1)
    return round(amount, 1)


def _classify_leave(sub_type: Optional[str]) -> Optional[str]:
    if not sub_type:
        return None
    normalized = sub_type.strip()
    if normalized in LEAVE_TYPE_MAP:
        return LEAVE_TYPE_MAP[normalized]
    lowered = normalized.lower()
    for key, value in LEAVE_TYPE_MAP.items():
        if key in normalized or key.lower() in lowered:
            return value
    return None


def _collect_month_approvals(userid: str, year: int, month: int, biz_type: int) -> List[Dict]:
    _, _, last_day = month_bounds(year, month)
    approvals: Dict[str, Dict] = {}

    for day in range(1, last_day + 1):
        work_date = f"{year}-{month:02d}-{day:02d}"
        try:
            payload = dingtalk_corp_client.get_attendance_update_data(userid, work_date)
        except DingTalkAPIError as exc:
            logger.warning(
                "Failed to fetch attendance update data for %s on %s: %s",
                userid,
                work_date,
                exc.message,
            )
            continue

        result = payload.get("result") or {}
        for item in result.get("approve_list") or []:
            if int(item.get("biz_type") or 0) != biz_type:
                continue
            key = str(item.get("procInst_id") or item.get("procinst_id") or f"{userid}-{item.get('begin_time')}")
            approvals[key] = item

    return list(approvals.values())


def _get_or_create_monthly_record(
    db: Session,
    company_id: int,
    employee_id: int,
    year: int,
    month: int,
) -> MonthlyAttendance:
    record = (
        db.query(MonthlyAttendance)
        .filter(
            MonthlyAttendance.company_id == company_id,
            MonthlyAttendance.employee_id == employee_id,
            MonthlyAttendance.year == year,
            MonthlyAttendance.month == month,
        )
        .first()
    )
    if record:
        return record

    record = MonthlyAttendance(
        company_id=company_id,
        employee_id=employee_id,
        year=year,
        month=month,
    )
    db.add(record)
    db.flush()
    return record


def _sum_leave_hours_from_report(userid: str, from_date: str, to_date: str) -> Dict[str, float]:
    totals = {"personal": 0.0, "sick": 0.0, "annual": 0.0, "compensatory": 0.0}
    try:
        payload = dingtalk_corp_client.get_leave_time_by_names(
            userid,
            "事假,病假,年假,调休",
            from_date,
            to_date,
        )
    except DingTalkAPIError as exc:
        logger.warning("getleavetimebynames failed for %s: %s", userid, exc.message)
        return totals

    columns = (payload.get("result") or {}).get("columns") or []
    for column in columns:
        column_info = column.get("columnvo") or {}
        leave_name = column_info.get("name")
        category = _classify_leave(leave_name)
        if not category:
            continue
        amount = 0.0
        for day_value in column.get("columnvals") or []:
            try:
                amount += float(day_value.get("value") or 0)
            except (TypeError, ValueError):
                continue
        totals[category] = round(totals[category] + amount * 8.0, 1)
    return totals


def sync_leaves_for_company(db: Session, company: Company, year: int, month: int) -> LeaveSyncSummary:
    if not dingtalk_corp_client.is_configured():
        raise DingTalkAPIError(
            "DingTalk API is not configured. Set DINGTALK_CLIENT_ID and DINGTALK_CLIENT_SECRET.",
            status_code=503,
        )

    from_date, to_date, _ = month_bounds(year, month)
    employees = (
        db.query(Employee)
        .filter(
            Employee.company_id == company.id,
            Employee.is_active.is_(True),
            Employee.dingtalk_user_id.isnot(None),
        )
        .all()
    )
    summary = LeaveSyncSummary()
    logger.info(
        "Starting leave sync for company_id=%s period=%s-%02d (%s employees)",
        company.id,
        year,
        month,
        len(employees),
    )

    for employee in employees:
        assert employee.dingtalk_user_id is not None
        totals = {"personal": 0.0, "sick": 0.0, "annual": 0.0, "compensatory": 0.0}
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
                    "getleaveapproveduration failed for %s (%s-%s): %s",
                    employee.dingtalk_user_id,
                    begin,
                    end,
                    exc.message,
                )
                hours = _parse_duration_to_hours(
                    approval.get("duration"),
                    approval.get("duration_unit"),
                )
            totals[category] = round(totals[category] + hours, 1)

        if not approvals:
            totals = _sum_leave_hours_from_report(employee.dingtalk_user_id, from_date, to_date)

        record = _get_or_create_monthly_record(db, company.id, employee.id, year, month)
        record.total_personal_leave = totals["personal"]
        record.total_sick_leave = totals["sick"]
        record.total_annual_leave = totals["annual"]
        record.total_compensatory_leave = totals["compensatory"]
        record.last_sync_from_dingtalk = datetime.utcnow()
        record.updated_at = datetime.utcnow()

        summary.employees_updated += 1
        summary.employees.append(
            EmployeeLeaveTotals(
                employee_id=employee.id,
                name=employee.name,
                personal_leave_hours=totals["personal"],
                sick_leave_hours=totals["sick"],
                annual_leave_hours=totals["annual"],
                compensatory_leave_hours=totals["compensatory"],
            )
        )
        logger.info(
            "Leave sync updated %s: personal=%s sick=%s annual=%s compensatory=%s",
            employee.name,
            totals["personal"],
            totals["sick"],
            totals["annual"],
            totals["compensatory"],
        )

    db.commit()
    summary.message = (
        f"Leave sync completed for {year}-{month:02d}: "
        f"{summary.employees_updated} employees updated"
    )
    logger.info(summary.message)
    return summary


def sync_overtime_for_company(db: Session, company: Company, year: int, month: int) -> OvertimeSyncSummary:
    if not dingtalk_corp_client.is_configured():
        raise DingTalkAPIError(
            "DingTalk API is not configured. Set DINGTALK_CLIENT_ID and DINGTALK_CLIENT_SECRET.",
            status_code=503,
        )

    from_date, to_date, _ = month_bounds(year, month)
    employees = (
        db.query(Employee)
        .filter(
            Employee.company_id == company.id,
            Employee.is_active.is_(True),
            Employee.dingtalk_user_id.isnot(None),
        )
        .all()
    )
    summary = OvertimeSyncSummary()
    logger.info(
        "Starting overtime sync for company_id=%s period=%s-%02d (%s employees)",
        company.id,
        year,
        month,
        len(employees),
    )

    for employee in employees:
        assert employee.dingtalk_user_id is not None
        overtime_hours = 0.0
        approvals = _collect_month_approvals(employee.dingtalk_user_id, year, month, biz_type=1)

        for approval in approvals:
            begin = _format_api_datetime(approval.get("begin_time"))
            end = _format_api_datetime(approval.get("end_time"))
            hours = 0.0

            if begin and end:
                minutes = dingtalk_corp_client.get_overtime_approval_duration(
                    employee.dingtalk_user_id,
                    begin,
                    end,
                )
                if minutes > 0:
                    hours = _minutes_to_hours(minutes)
                else:
                    hours = _parse_duration_to_hours(
                        approval.get("duration") or approval.get("overtime_duration"),
                        approval.get("duration_unit") or "hour",
                    )
            else:
                hours = _parse_duration_to_hours(
                    approval.get("duration") or approval.get("overtime_duration"),
                    approval.get("duration_unit") or "hour",
                )

            overtime_hours = round(overtime_hours + hours, 1)

        if not approvals:
            try:
                overtime_payload = dingtalk_corp_client.get_leave_time_by_names(
                    employee.dingtalk_user_id,
                    "加班",
                    from_date,
                    to_date,
                )
                columns = (overtime_payload.get("result") or {}).get("columns") or []
                overtime_hours = 0.0
                for column in columns:
                    for day_value in column.get("columnvals") or []:
                        try:
                            overtime_hours += float(day_value.get("value") or 0)
                        except (TypeError, ValueError):
                            continue
                overtime_hours = round(overtime_hours, 1)
            except DingTalkAPIError as exc:
                logger.warning("Overtime report fallback failed for %s: %s", employee.name, exc.message)

        record = _get_or_create_monthly_record(db, company.id, employee.id, year, month)
        record.total_overtime_hours = overtime_hours
        record.last_sync_from_dingtalk = datetime.utcnow()
        record.updated_at = datetime.utcnow()

        summary.employees_updated += 1
        summary.employees.append(
            EmployeeOvertimeTotals(
                employee_id=employee.id,
                name=employee.name,
                overtime_hours=overtime_hours,
            )
        )
        logger.info("Overtime sync updated %s: overtime_hours=%s", employee.name, overtime_hours)

    db.commit()
    summary.message = (
        f"Overtime sync completed for {year}-{month:02d}: "
        f"{summary.employees_updated} employees updated"
    )
    logger.info(summary.message)
    return summary
