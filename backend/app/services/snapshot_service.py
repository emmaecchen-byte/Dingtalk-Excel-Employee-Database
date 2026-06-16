"""
Excel snapshot creation and comparison for change tracking.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from app.excel.attendance_export import get_day_value
from app.excel.field_utils import normalize_numeric_value, normalize_value, snapshot_field_value
from app.models import ExcelSnapshot, MonthlyAttendance, User

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
    }


def build_attendance_data_snapshot(
    records: List[MonthlyAttendance],
    year: int,
    month: int,
    *,
    dingtalk_sync_timestamp: Optional[datetime] = None,
) -> Dict[str, Any]:
    last_sync = dingtalk_sync_timestamp or max(
        (record.last_sync_from_dingtalk for record in records if record.last_sync_from_dingtalk),
        default=None,
    )
    return {
        "year": year,
        "month": month,
        "exported_at": datetime.utcnow().isoformat(),
        "employee_count": len(records),
        "last_sync_from_dingtalk": last_sync.isoformat() if last_sync else None,
        "employees": [serialize_attendance_record(record) for record in records],
    }


def _get_latest_snapshot(
    db: Session,
    company_id: int,
    year: int,
    month: int,
) -> Optional[ExcelSnapshot]:
    return (
        db.query(ExcelSnapshot)
        .filter(
            ExcelSnapshot.company_id == company_id,
            ExcelSnapshot.year == year,
            ExcelSnapshot.month == month,
        )
        .order_by(ExcelSnapshot.snapshot_version.desc(), ExcelSnapshot.id.desc())
        .first()
    )


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

    previous = _get_latest_snapshot(db, company_id, year, month)
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
    """
    Persist a pre-built data_snapshot as a new excel_snapshots row.

    Used when restoring a known snapshot payload (e.g. version rollback) while
    incrementing snapshot_version and linking previous_snapshot_id.
    """
    if month < 1 or month > 12:
        raise SnapshotServiceError("Month must be between 1 and 12")

    previous = _get_latest_snapshot(db, company_id, year, month)
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
        return {
            "snapshot_id_1": self.snapshot_id_1,
            "snapshot_id_2": self.snapshot_id_2,
            "year": self.year,
            "month": self.month,
            "has_differences": self.has_differences,
            "added_employees": [
                {"employee_id": item.employee_id, "employee_name": item.employee_name}
                for item in self.added_employees
            ],
            "removed_employees": [
                {"employee_id": item.employee_id, "employee_name": item.employee_name}
                for item in self.removed_employees
            ],
            "changed_fields": [
                {
                    "employee_id": item.employee_id,
                    "employee_name": item.employee_name,
                    "field_name": item.field_name,
                    "value_in_snapshot_1": item.value_in_snapshot_1,
                    "value_in_snapshot_2": item.value_in_snapshot_2,
                }
                for item in self.changed_fields
            ],
        }


def _snapshot_employee_index(snapshot: ExcelSnapshot) -> Dict[int, dict]:
    employees = (snapshot.data_snapshot or {}).get("employees") or []
    return {
        int(employee["employee_id"]): employee
        for employee in employees
        if employee.get("employee_id") is not None
    }


def _get_snapshot(db: Session, snapshot_id: int) -> ExcelSnapshot:
    snapshot = db.query(ExcelSnapshot).filter(ExcelSnapshot.id == snapshot_id).first()
    if not snapshot:
        raise SnapshotServiceError(f"Snapshot {snapshot_id} not found", status_code=404)
    return snapshot


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

    index_1 = _snapshot_employee_index(snapshot_1)
    index_2 = _snapshot_employee_index(snapshot_2)
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
