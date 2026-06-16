"""
Excel snapshot creation, retrieval, diffing, and version history.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from sqlalchemy.orm import Session, joinedload

from app.excel.field_utils import get_overtime_day_hours, normalize_numeric_value, normalize_value, snapshot_field_value
from app.services.excel_generator import get_day_value
from app.models import ExcelSnapshot, MonthlyAttendance, User, VersionHistory

logger = logging.getLogger(__name__)

COMPARABLE_FIELDS = [f"day_{day}" for day in range(1, 32)] + [
    "total_attendance_days",
    "total_personal_leave",
    "total_sick_leave",
    "total_annual_leave",
    "total_compensatory_leave",
    "total_overtime_hours",
    "absenteeism_count",
    "lateness_count",
    "missing_punch_count",
    "anomaly_summary",
    "supplement_submitted",
    "notes",
]


SNAPSHOT_REQUIRED_MESSAGE = "Please download the original Excel first."


class SnapshotServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def serialize_attendance_record(record: MonthlyAttendance) -> Dict[str, Any]:
    employee = record.employee
    return {
        "attendance_id": record.id,
        "employee_id": employee.id,
        "employee_name": employee.name,
        "department": employee.department,
        "position": employee.position,
        "employee_code": employee.employee_code,
        "dingtalk_user_id": employee.dingtalk_user_id,
        "total_attendance_days": int(record.total_attendance_days or 0),
        "total_personal_leave": float(record.total_personal_leave or 0),
        "total_sick_leave": float(record.total_sick_leave or 0),
        "total_annual_leave": float(record.total_annual_leave or 0),
        "total_compensatory_leave": float(record.total_compensatory_leave or 0),
        "total_overtime_hours": float(record.total_overtime_hours or 0),
        "absenteeism_count": int(record.absenteeism_count or 0),
        "lateness_count": int(record.lateness_count or 0),
        "missing_punch_count": int(record.missing_punch_count or 0),
        "anomaly_summary": record.anomaly_summary,
        "supplement_submitted": bool(record.supplement_submitted),
        "notes": record.notes,
        "manual_overrides": record.manual_overrides or {},
        "last_sync_from_dingtalk": (
            record.last_sync_from_dingtalk.isoformat() if record.last_sync_from_dingtalk else None
        ),
        "last_manual_edit": record.last_manual_edit.isoformat() if record.last_manual_edit else None,
        "daily_status": {f"day_{day}": get_day_value(record, day) for day in range(1, 32)},
        "daily_overtime": {
            f"overtime_day_{day}": get_overtime_day_hours(record, day) for day in range(1, 32)
        },
    }


def build_attendance_data_snapshot(
    records: List[MonthlyAttendance],
    year: int,
    month: int,
    *,
    dingtalk_sync_timestamp: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Build JSON snapshot payload with ``employees`` keyed by ``employee_id`` (string).
    """
    last_sync = dingtalk_sync_timestamp or max(
        (record.last_sync_from_dingtalk for record in records if record.last_sync_from_dingtalk),
        default=None,
    )
    employees_by_id: Dict[str, Dict[str, Any]] = {}
    for record in records:
        payload = serialize_attendance_record(record)
        employees_by_id[str(record.employee_id)] = payload

    return {
        "year": year,
        "month": month,
        "exported_at": datetime.utcnow().isoformat(),
        "employee_count": len(records),
        "last_sync_from_dingtalk": last_sync.isoformat() if last_sync else None,
        "employees": employees_by_id,
    }


def snapshot_employee_index(snapshot: ExcelSnapshot) -> Dict[int, dict]:
    """
    Normalize snapshot JSON into ``{employee_id: employee_payload}``.

    Supports both dict-keyed and legacy list-based ``employees`` storage.
    """
    data = snapshot.data_snapshot or {}
    employees = data.get("employees")

    if isinstance(employees, dict):
        index: Dict[int, dict] = {}
        for key, payload in employees.items():
            if not isinstance(payload, dict):
                continue
            employee_id = payload.get("employee_id")
            if employee_id is None:
                try:
                    employee_id = int(key)
                except (TypeError, ValueError):
                    continue
            index[int(employee_id)] = payload
        return index

    if isinstance(employees, list):
        return {
            int(employee["employee_id"]): employee
            for employee in employees
            if isinstance(employee, dict) and employee.get("employee_id") is not None
        }

    return {}


def _query_attendance_records(
    db: Session,
    company_id: int,
    year: int,
    month: int,
) -> List[MonthlyAttendance]:
    return (
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


def _get_latest_snapshot_record(
    db: Session,
    company_id: int,
    year: int,
    month: int,
    *,
    active_only: bool = False,
) -> Optional[ExcelSnapshot]:
    query = db.query(ExcelSnapshot).filter(
        ExcelSnapshot.company_id == company_id,
        ExcelSnapshot.year == year,
        ExcelSnapshot.month == month,
    )
    if active_only:
        query = query.filter(ExcelSnapshot.status == "active")
    return query.order_by(ExcelSnapshot.snapshot_version.desc(), ExcelSnapshot.id.desc()).first()


def create_snapshot(
    db: Session,
    company_id: int,
    year: int,
    month: int,
    downloaded_by: int,
    dingtalk_sync_timestamp: Optional[datetime] = None,
    *,
    file_name: Optional[str] = None,
    file_size: Optional[int] = None,
    record_version_history: bool = True,
    commit: bool = True,
) -> int:
    """
    Capture monthly_attendance state as a versioned excel_snapshots row.

    Returns the new snapshot ID.
    """
    if month < 1 or month > 12:
        raise SnapshotServiceError("Month must be between 1 and 12")

    records = _query_attendance_records(db, company_id, year, month)
    if not records:
        raise SnapshotServiceError(
            f"No attendance data for {year}-{month:02d}",
            status_code=404,
        )

    if dingtalk_sync_timestamp is None:
        dingtalk_sync_timestamp = max(
            (record.last_sync_from_dingtalk for record in records if record.last_sync_from_dingtalk),
            default=None,
        )

    data_snapshot = build_attendance_data_snapshot(
        records,
        year,
        month,
        dingtalk_sync_timestamp=dingtalk_sync_timestamp,
    )

    previous = _get_latest_snapshot_record(db, company_id, year, month)
    new_version = (previous.snapshot_version + 1) if previous else 1
    now = datetime.utcnow()

    snapshot = ExcelSnapshot(
        company_id=company_id,
        year=year,
        month=month,
        snapshot_version=new_version,
        downloaded_at=now,
        downloaded_by=downloaded_by,
        file_name=file_name,
        file_size=file_size,
        dingtalk_sync_timestamp=dingtalk_sync_timestamp,
        data_snapshot=data_snapshot,
        previous_snapshot_id=previous.id if previous else None,
        status="active",
    )
    db.add(snapshot)

    if previous and previous.status == "active":
        previous.status = "superseded"

    db.flush()

    user = db.query(User).filter(User.id == downloaded_by).first()
    if user and record_version_history:
        from app.services.version_service import record_snapshot_version

        record_snapshot_version(
            db,
            snapshot=snapshot,
            user=user,
            employee_count=len(records),
        )

    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(snapshot)

    logger.info(
        "Snapshot created: id=%s company_id=%s period=%s-%02d version=v%s employees=%s",
        snapshot.id,
        company_id,
        year,
        month,
        new_version,
        len(records),
    )
    return snapshot.id


def create_snapshot_from_data(
    db: Session,
    company_id: int,
    year: int,
    month: int,
    downloaded_by: int,
    data_snapshot: Dict[str, Any],
    *,
    dingtalk_sync_timestamp: Optional[datetime] = None,
    file_name: Optional[str] = None,
    file_size: Optional[int] = None,
    commit: bool = True,
) -> int:
    """Persist a pre-built data_snapshot as a new excel_snapshots row."""
    if month < 1 or month > 12:
        raise SnapshotServiceError("Month must be between 1 and 12")

    previous = _get_latest_snapshot_record(db, company_id, year, month)
    new_version = (previous.snapshot_version + 1) if previous else 1
    now = datetime.utcnow()

    snapshot = ExcelSnapshot(
        company_id=company_id,
        year=year,
        month=month,
        snapshot_version=new_version,
        downloaded_at=now,
        downloaded_by=downloaded_by,
        file_name=file_name,
        file_size=file_size,
        dingtalk_sync_timestamp=dingtalk_sync_timestamp,
        data_snapshot=data_snapshot,
        previous_snapshot_id=previous.id if previous else None,
        status="active",
    )
    db.add(snapshot)

    if previous and previous.status == "active":
        previous.status = "superseded"

    db.flush()

    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(snapshot)

    logger.info(
        "Snapshot created from data: id=%s company_id=%s period=%s-%02d version=v%s",
        snapshot.id,
        company_id,
        year,
        month,
        new_version,
    )
    return snapshot.id


def get_latest_snapshot(
    db: Session,
    company_id: int,
    year: int,
    month: int,
) -> Optional[ExcelSnapshot]:
    """Return the most recent active snapshot for the period, or None."""
    return _get_latest_snapshot_record(db, company_id, year, month, active_only=True)


def _get_snapshot(db: Session, snapshot_id: int) -> ExcelSnapshot:
    snapshot = db.query(ExcelSnapshot).filter(ExcelSnapshot.id == snapshot_id).first()
    if not snapshot:
        raise SnapshotServiceError(f"Snapshot {snapshot_id} not found", status_code=404)
    return snapshot


@dataclass
class SnapshotFieldDiff:
    employee_id: int
    employee_name: str
    field_name: str
    value_in_snapshot_1: str
    value_in_snapshot_2: str


@dataclass
class SnapshotEmployeeChange:
    employee_id: int
    employee_name: str


@dataclass
class SnapshotDiffResult:
    snapshot_id_1: int
    snapshot_id_2: int
    year: int
    month: int
    added_employees: List[SnapshotEmployeeChange] = field(default_factory=list)
    removed_employees: List[SnapshotEmployeeChange] = field(default_factory=list)
    changed_fields: List[SnapshotFieldDiff] = field(default_factory=list)

    @property
    def has_differences(self) -> bool:
        return bool(self.added_employees or self.removed_employees or self.changed_fields)

    def to_dict(self) -> Dict[str, Any]:
        added = [
            {"employee_id": item.employee_id, "employee_name": item.employee_name}
            for item in self.added_employees
        ]
        removed = [
            {"employee_id": item.employee_id, "employee_name": item.employee_name}
            for item in self.removed_employees
        ]
        changed = [
            {
                "employee_id": item.employee_id,
                "employee_name": item.employee_name,
                "field": item.field_name,
                "field_name": item.field_name,
                "old_value": item.value_in_snapshot_1,
                "new_value": item.value_in_snapshot_2,
                "value_in_snapshot_1": item.value_in_snapshot_1,
                "value_in_snapshot_2": item.value_in_snapshot_2,
            }
            for item in self.changed_fields
        ]
        return {
            "snapshot_id_1": self.snapshot_id_1,
            "snapshot_id_2": self.snapshot_id_2,
            "year": self.year,
            "month": self.month,
            "has_differences": self.has_differences,
            "added": added,
            "removed": removed,
            "changed": changed,
            "added_employees": added,
            "removed_employees": removed,
            "changed_fields": changed,
        }


def get_snapshot_diff(
    db: Session,
    snapshot_id_1: int,
    snapshot_id_2: int,
) -> SnapshotDiffResult:
    """Compare two snapshots and return field-level differences."""
    snapshot_1 = _get_snapshot(db, snapshot_id_1)
    snapshot_2 = _get_snapshot(db, snapshot_id_2)

    if (
        snapshot_1.company_id != snapshot_2.company_id
        or snapshot_1.year != snapshot_2.year
        or snapshot_1.month != snapshot_2.month
    ):
        raise SnapshotServiceError(
            "Snapshots must belong to the same company, year, and month",
            status_code=400,
        )

    index_1 = snapshot_employee_index(snapshot_1)
    index_2 = snapshot_employee_index(snapshot_2)
    ids_1 = set(index_1)
    ids_2 = set(index_2)

    added_employees = [
        SnapshotEmployeeChange(
            employee_id=employee_id,
            employee_name=str(index_2[employee_id].get("employee_name") or ""),
        )
        for employee_id in sorted(ids_2 - ids_1)
    ]
    removed_employees = [
        SnapshotEmployeeChange(
            employee_id=employee_id,
            employee_name=str(index_1[employee_id].get("employee_name") or ""),
        )
        for employee_id in sorted(ids_1 - ids_2)
    ]

    changed_fields: List[SnapshotFieldDiff] = []
    for employee_id in sorted(ids_1 & ids_2):
        employee_1 = index_1[employee_id]
        employee_2 = index_2[employee_id]
        employee_name = str(employee_1.get("employee_name") or employee_2.get("employee_name") or "")

        for field_name in COMPARABLE_FIELDS:
            value_1 = snapshot_field_value(employee_1, field_name)
            value_2 = snapshot_field_value(employee_2, field_name)

            if field_name == "total_overtime_hours":
                if normalize_numeric_value(value_1) == normalize_numeric_value(value_2):
                    continue
            elif normalize_value(value_1) == normalize_value(value_2):
                continue

            changed_fields.append(
                SnapshotFieldDiff(
                    employee_id=employee_id,
                    employee_name=employee_name,
                    field_name=field_name,
                    value_in_snapshot_1=value_1,
                    value_in_snapshot_2=value_2,
                )
            )

    return SnapshotDiffResult(
        snapshot_id_1=snapshot_id_1,
        snapshot_id_2=snapshot_id_2,
        year=snapshot_1.year,
        month=snapshot_1.month,
        added_employees=added_employees,
        removed_employees=removed_employees,
        changed_fields=changed_fields,
    )


def _summarize_version_changes(changes_summary: dict, version_note: Optional[str]) -> str:
    if version_note:
        return version_note

    event = changes_summary.get("event")
    if event == "conflict_resolution":
        count = changes_summary.get("resolved_count", 0)
        method = changes_summary.get("resolution_method", "")
        return f"Resolved {count} conflict(s)" + (f" ({method})" if method else "")
    if event == "excel_snapshot":
        count = changes_summary.get("employee_count", 0)
        return f"Excel snapshot ({count} employees)"
    if event == "version_restore":
        restored_from = changes_summary.get("restored_from_version")
        return f"Restored from version v{restored_from}" if restored_from else "Restored previous version"
    if event == "version_rollback":
        rolled_back = changes_summary.get("rolled_back_to_version")
        return f"Rollback to version v{rolled_back}" if rolled_back else "Version rollback"
    if event == "month_clone":
        source_year = changes_summary.get("source_year")
        source_month = changes_summary.get("source_month")
        count = changes_summary.get("employees_copied", 0)
        if source_year and source_month:
            return f"Cloned from {source_year}-{int(source_month):02d} ({count} employees)"
        return f"Month clone ({count} employees)"
    return "Attendance update"


def get_version_history(
    db: Session,
    company_id: int,
    year: int,
    month: int,
) -> List[Dict[str, Any]]:
    """
    Query version_history for the month, join user names, sorted by version_number DESC.
    """
    versions = (
        db.query(VersionHistory)
        .filter(
            VersionHistory.company_id == company_id,
            VersionHistory.year == year,
            VersionHistory.month == month,
        )
        .order_by(VersionHistory.version_number.desc(), VersionHistory.id.desc())
        .all()
    )

    user_ids = {version.created_by_user_id for version in versions if version.created_by_user_id}
    user_names = {
        user.id: user.name
        for user in db.query(User).filter(User.id.in_(user_ids)).all()
    } if user_ids else {}

    items: List[Dict[str, Any]] = []
    for version in versions:
        summary = version.changes_summary or {}
        created_by = version.created_by
        if version.created_by_user_id:
            created_by = user_names.get(version.created_by_user_id) or created_by
        items.append(
            {
                "id": version.id,
                "version_number": version.version_number,
                "created_at": version.created_at.isoformat() if version.created_at else None,
                "created_by": created_by,
                "created_by_user_id": version.created_by_user_id,
                "summary": _summarize_version_changes(summary, version.version_note),
                "event_type": summary.get("event"),
                "snapshot_id": version.snapshot_id,
                "can_restore": version.snapshot_id is not None,
                "changes_summary": summary,
                "version_note": version.version_note,
            }
        )

    return items
