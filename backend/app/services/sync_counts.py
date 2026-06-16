from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import Conflict, Employee, MonthlyAttendance, PendingUpdate
from app.services.sync_log_service import get_last_successful_sync_timestamp
from app.sync_state import sync_state


def count_pending_updates(db: Session, company_id: int) -> int:
    return (
        db.query(PendingUpdate)
        .filter(
            PendingUpdate.company_id == company_id,
            PendingUpdate.status == "pending",
        )
        .count()
    )


def count_pending_conflicts(db: Session, company_id: int) -> int:
    return (
        db.query(Conflict)
        .filter(
            Conflict.company_id == company_id,
            Conflict.status == "pending",
        )
        .count()
    )


def _resolve_last_sync_timestamp(db: Session, company_id: int) -> Optional[datetime]:
    from_sync_logs = get_last_successful_sync_timestamp(db, company_id)
    if from_sync_logs:
        return from_sync_logs

    candidates: List[datetime] = []

    for timestamp in (
        sync_state.attendance_synced_at,
        sync_state.employees_synced_at,
        sync_state.leaves_synced_at,
        sync_state.overtime_synced_at,
    ):
        if timestamp:
            candidates.append(timestamp)

    db_last_sync = (
        db.query(MonthlyAttendance.last_sync_from_dingtalk)
        .filter(
            MonthlyAttendance.company_id == company_id,
            MonthlyAttendance.last_sync_from_dingtalk.isnot(None),
        )
        .order_by(MonthlyAttendance.last_sync_from_dingtalk.desc())
        .first()
    )
    if db_last_sync and db_last_sync[0]:
        candidates.append(db_last_sync[0])

    if not candidates:
        return None
    return max(candidates)


def list_pending_updates(db: Session, company_id: int) -> List[Dict[str, Any]]:
    updates = (
        db.query(PendingUpdate)
        .filter(
            PendingUpdate.company_id == company_id,
            PendingUpdate.status == "pending",
        )
        .order_by(PendingUpdate.created_at.desc())
        .all()
    )

    employee_ids = {update.employee_id for update in updates if update.employee_id}
    employees_by_id = {
        employee.id: employee
        for employee in db.query(Employee).filter(Employee.id.in_(employee_ids)).all()
    } if employee_ids else {}

    items: List[Dict[str, Any]] = []
    for update in updates:
        employee = employees_by_id.get(update.employee_id)
        employee_name = employee.name if employee else update.dingtalk_user_id
        items.append(
            {
                "employee_name": employee_name,
                "field_name": update.field_name,
                "new_value": update.dingtalk_value or "",
            }
        )
    return items


def get_sync_status(db: Session, company_id: int) -> Dict[str, Any]:
    pending_updates_count = count_pending_updates(db, company_id)
    pending_conflicts_count = count_pending_conflicts(db, company_id)
    last_sync_timestamp = _resolve_last_sync_timestamp(db, company_id)

    return {
        "last_sync_timestamp": last_sync_timestamp,
        "pending_updates_count": pending_updates_count,
        "pending_conflicts_count": pending_conflicts_count,
        "pending_updates_list": list_pending_updates(db, company_id),
        "employees_synced_at": sync_state.employees_synced_at,
        "attendance_synced_at": sync_state.attendance_synced_at,
        "leaves_synced_at": sync_state.leaves_synced_at,
        "overtime_synced_at": sync_state.overtime_synced_at,
        "pending_updates": pending_updates_count,
        "pending_conflicts": pending_conflicts_count,
    }
