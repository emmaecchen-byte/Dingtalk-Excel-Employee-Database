"""
Compare uploaded Excel data against the latest excel_snapshots row and record changes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session, joinedload

from app.excel.field_utils import normalize_value, snapshot_field_value
from app.models import ManualChange, MonthlyAttendance, User
from app.services.change_tracker import track_manual_change
from app.services.conflict_detector import detect_conflicts
from app.services.excel_parser import ParsedWorkbook
from app.services.snapshot_service import (
    SNAPSHOT_REQUIRED_MESSAGE,
    get_latest_snapshot,
    snapshot_employee_index,
)

logger = logging.getLogger(__name__)

COMPARISON_FIELDS = [f"day_{day}" for day in range(1, 32)] + [
    "supplement_submitted",
    "notes",
]


class ChangeDetectorError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass
class DetectedChange:
    employee_id: int
    employee_name: str
    field_name: str
    old_value: str
    new_value: str
    conflict: bool = False
    conflict_id: Optional[int] = None


@dataclass
class ChangeDetectionResult:
    year: int
    month: int
    snapshot_id: int
    total_changes: int
    employees_affected: int
    changes: List[DetectedChange] = field(default_factory=list)
    conflicts_created: int = 0
    pending_conflicts_count: int = 0
    auto_merged: int = 0
    has_conflicts: bool = False
    conflicts_list: List[dict] = field(default_factory=list)


def get_latest_snapshot_or_raise(
    db: Session,
    company_id: int,
    year: int,
    month: int,
):
    snapshot = get_latest_snapshot(db, company_id, year, month)
    if not snapshot:
        raise ChangeDetectorError(SNAPSHOT_REQUIRED_MESSAGE, status_code=404)
    return snapshot


def _build_snapshot_index(snapshot) -> Dict[int, dict]:
    return snapshot_employee_index(snapshot)


def _build_name_to_id(snapshot_index: Dict[int, dict]) -> Dict[str, int]:
    mapping: Dict[str, int] = {}
    for employee_id, payload in snapshot_index.items():
        name = payload.get("employee_name")
        if name:
            mapping[str(name)] = employee_id
    return mapping


def _uploaded_field_value(uploaded_employee: dict, field_name: str) -> str:
    if field_name.startswith("day_"):
        daily = uploaded_employee.get("daily_status") or {}
        return normalize_value(daily.get(field_name, ""))
    return normalize_value(uploaded_employee.get(field_name, ""))


def diff_employee_against_snapshot(
    snapshot_employee: dict,
    uploaded_employee: dict,
    employee_id: int,
    employee_name: str,
) -> List[DetectedChange]:
    """Return field-level differences for one employee."""
    changes: List[DetectedChange] = []
    for field_name in COMPARISON_FIELDS:
        old_value = snapshot_field_value(snapshot_employee, field_name)
        new_value = _uploaded_field_value(uploaded_employee, field_name)
        if old_value == new_value:
            continue
        changes.append(
            DetectedChange(
                employee_id=employee_id,
                employee_name=employee_name,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
            )
        )
    return changes


def detect_and_record_changes(
    db: Session,
    user: User,
    year: int,
    month: int,
    parsed: ParsedWorkbook,
    *,
    snapshot=None,
) -> ChangeDetectionResult:
    """
    Compare uploaded workbook data with the latest snapshot and persist manual_changes.
    """
    if month < 1 or month > 12:
        raise ChangeDetectorError("Month must be between 1 and 12")

    snapshot = snapshot or get_latest_snapshot_or_raise(db, user.company_id, year, month)
    snapshot_index = _build_snapshot_index(snapshot)
    name_to_id = _build_name_to_id(snapshot_index)
    uploaded_by_name = parsed.employees_by_name()

    attendance_records = (
        db.query(MonthlyAttendance)
        .options(joinedload(MonthlyAttendance.employee))
        .filter(
            MonthlyAttendance.company_id == user.company_id,
            MonthlyAttendance.year == year,
            MonthlyAttendance.month == month,
        )
        .all()
    )
    records_by_employee_id = {record.employee_id: record for record in attendance_records}

    all_changes: List[DetectedChange] = []
    manual_changes_batch: List[ManualChange] = []
    change_pairs: List[Tuple[ManualChange, DetectedChange]] = []
    modified_employees: Set[int] = set()
    baseline_timestamp = snapshot.downloaded_at or snapshot.created_at

    for employee_name, uploaded_row in uploaded_by_name.items():
        employee_id = name_to_id.get(employee_name)
        if not employee_id:
            logger.warning("Skipping unknown employee in upload: %s", employee_name)
            continue

        snapshot_employee = snapshot_index.get(employee_id)
        if not snapshot_employee:
            continue

        if employee_id not in records_by_employee_id:
            logger.warning("No attendance record for employee_id=%s", employee_id)
            continue

        uploaded_payload = uploaded_row.as_comparison_payload()
        employee_changes = diff_employee_against_snapshot(
            snapshot_employee,
            uploaded_payload,
            employee_id,
            employee_name,
        )
        if not employee_changes:
            continue

        modified_employees.add(employee_id)

        for change in employee_changes:
            manual_change = track_manual_change(
                db,
                company_id=user.company_id,
                year=year,
                month=month,
                employee_id=employee_id,
                field_name=change.field_name,
                old_value=change.old_value,
                new_value=change.new_value,
                snapshot_id=snapshot.id,
                change_source="excel_upload",
                changed_by=user.id,
                merged_to_truth=False,
            )
            manual_changes_batch.append(manual_change)
            change_pairs.append((manual_change, change))
            all_changes.append(change)

    db.flush()

    conflict_result = detect_conflicts(
        db,
        user.company_id,
        year,
        month,
        manual_changes_batch,
        attendance_by_employee_id=records_by_employee_id,
        baseline_timestamp=baseline_timestamp,
        auto_apply_resolutions=True,
        respect_user_priority=False,
    )

    conflict_keys = {
        (conflict.employee_id, conflict.field_name) for conflict in conflict_result.conflicts
    }
    conflict_id_by_key = {
        (conflict.employee_id, conflict.field_name): conflict.id
        for conflict in conflict_result.conflicts
    }

    for manual_change, change in change_pairs:
        key = (manual_change.employee_id, manual_change.field_name)
        if key in conflict_keys:
            change.conflict = True
            change.conflict_id = conflict_id_by_key.get(key)

    db.commit()

    logger.info(
        "Excel upload changes recorded: user_id=%s company_id=%s period=%s-%02d "
        "snapshot_id=%s total_changes=%s employees_affected=%s conflicts=%s",
        user.id,
        user.company_id,
        year,
        month,
        snapshot.id,
        len(all_changes),
        len(modified_employees),
        conflict_result.conflicts_created,
    )

    return ChangeDetectionResult(
        year=year,
        month=month,
        snapshot_id=snapshot.id,
        total_changes=len(all_changes),
        employees_affected=len(modified_employees),
        changes=all_changes,
        conflicts_created=conflict_result.conflicts_created,
        pending_conflicts_count=conflict_result.pending_conflicts_count,
        auto_merged=conflict_result.auto_merged,
        has_conflicts=conflict_result.conflicts_created > 0,
        conflicts_list=conflict_result.conflicts_list,
    )
