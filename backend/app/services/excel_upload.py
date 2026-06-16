"""
Excel upload: diff against last snapshot, record manual changes, resolve conflicts.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from fastapi import UploadFile
from sqlalchemy.orm import Session, joinedload

from app.excel.attendance_parser import ParsedWorkbook, parse_attendance_workbook
from app.excel.field_utils import (
    apply_field_value,
    normalize_numeric_value,
    normalize_value,
    snapshot_field_value,
)
from app.services.conflict_detection import (
    PRIORITY_DINGTALK,
    dingtalk_is_newer_than_change,
    detect_conflicts,
    get_conflict_priority,
)
from app.models import ExcelSnapshot, ManualChange, MonthlyAttendance, User

logger = logging.getLogger(__name__)

TRACKED_FIELDS = [f"day_{day}" for day in range(1, 32)] + [
    "anomaly_summary",
    "supplement_submitted",
    "notes",
    "total_overtime_hours",
]

UPLOAD_CHUNK_SIZE = 1024 * 1024


class ExcelUploadError(Exception):
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
class ExcelUploadResult:
    year: int
    month: int
    snapshot_id: int
    changes_detected: int
    conflicts_created: int
    employees_modified: int
    pending_conflicts_count: int
    changes: List[DetectedChange] = field(default_factory=list)


async def _save_upload_to_tempfile(upload: UploadFile) -> str:
    suffix = ".xlsx"
    if upload.filename and upload.filename.lower().endswith(".xlsm"):
        suffix = ".xlsm"

    fd, temp_path = tempfile.mkstemp(prefix="excel_upload_", suffix=suffix)
    os.close(fd)
    try:
        with open(temp_path, "wb") as handle:
            while True:
                chunk = await upload.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                handle.write(chunk)
        return temp_path
    except Exception:
        os.unlink(temp_path)
        raise


def _get_latest_snapshot(
    db: Session,
    company_id: int,
    year: int,
    month: int,
) -> ExcelSnapshot:
    snapshot = (
        db.query(ExcelSnapshot)
        .filter(
            ExcelSnapshot.company_id == company_id,
            ExcelSnapshot.year == year,
            ExcelSnapshot.month == month,
        )
        .order_by(ExcelSnapshot.snapshot_version.desc(), ExcelSnapshot.id.desc())
        .first()
    )
    if not snapshot:
        raise ExcelUploadError(
            "No Excel snapshot found for this period. Download the template first.",
            status_code=404,
        )
    return snapshot


def _build_snapshot_index(snapshot: ExcelSnapshot) -> Dict[int, dict]:
    employees = (snapshot.data_snapshot or {}).get("employees") or []
    return {
        int(employee["employee_id"]): employee
        for employee in employees
        if employee.get("employee_id") is not None
    }


def _build_name_to_id(snapshot_index: Dict[int, dict]) -> Dict[str, int]:
    mapping: Dict[str, int] = {}
    for employee_id, payload in snapshot_index.items():
        name = payload.get("employee_name")
        if name:
            mapping[str(name)] = employee_id
    return mapping


def _diff_employee(
    snapshot_employee: dict,
    uploaded_employee: dict,
    employee_id: int,
    employee_name: str,
) -> List[DetectedChange]:
    changes: List[DetectedChange] = []
    for field_name in TRACKED_FIELDS:
        old_value = snapshot_field_value(snapshot_employee, field_name)
        if field_name.startswith("day_"):
            daily = uploaded_employee.get("daily_status") or {}
            new_value = normalize_value(daily.get(field_name, ""))
        elif field_name == "total_overtime_hours":
            new_value = normalize_numeric_value(uploaded_employee.get(field_name, ""))
        else:
            new_value = normalize_value(uploaded_employee.get(field_name, ""))

        if old_value != new_value:
            if field_name in {"notes", "anomaly_summary"} and new_value == "false" and not old_value:
                continue
            if field_name == "total_overtime_hours" and normalize_numeric_value(old_value) == normalize_numeric_value(new_value):
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


def process_excel_upload(
    db: Session,
    user: User,
    year: int,
    month: int,
    parsed: ParsedWorkbook,
    *,
    snapshot: Optional[ExcelSnapshot] = None,
) -> ExcelUploadResult:
    if month < 1 or month > 12:
        raise ExcelUploadError("Month must be between 1 and 12")

    snapshot = snapshot or _get_latest_snapshot(db, user.company_id, year, month)
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
    modified_employees = set()
    now = datetime.utcnow()
    baseline_timestamp = snapshot.downloaded_at or snapshot.created_at

    for employee_name, uploaded_row in uploaded_by_name.items():
        employee_id = name_to_id.get(employee_name)
        if not employee_id:
            logger.warning("Skipping unknown employee in upload: %s", employee_name)
            continue

        snapshot_employee = snapshot_index.get(employee_id)
        if not snapshot_employee:
            continue

        record = records_by_employee_id.get(employee_id)
        if not record:
            logger.warning("No attendance record for employee_id=%s", employee_id)
            continue

        uploaded_payload = uploaded_row.as_snapshot_shape()
        employee_changes = _diff_employee(
            snapshot_employee,
            uploaded_payload,
            employee_id,
            employee_name,
        )
        if not employee_changes:
            continue

        modified_employees.add(employee_id)

        for change in employee_changes:
            manual_change = ManualChange(
                company_id=user.company_id,
                year=year,
                month=month,
                employee_id=employee_id,
                snapshot_id=snapshot.id,
                field_name=change.field_name,
                old_value=change.old_value,
                new_value=change.new_value,
                change_source="excel_upload",
                change_timestamp=now,
                changed_by=user.id,
            )
            db.add(manual_change)
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
        user=user,
        attendance_by_employee_id=records_by_employee_id,
        baseline_timestamp=baseline_timestamp,
    )

    conflict_keys = {
        (conflict.employee_id, conflict.field_name) for conflict in conflict_result.conflicts
    }
    conflict_id_by_key = {
        (conflict.employee_id, conflict.field_name): conflict.id
        for conflict in conflict_result.conflicts
    }

    for manual_change, change in change_pairs:
        record = records_by_employee_id[manual_change.employee_id]
        key = (manual_change.employee_id, manual_change.field_name)

        if key in conflict_keys:
            change.conflict = True
            change.conflict_id = conflict_id_by_key.get(key)
            continue

        if manual_change.merged_to_truth:
            continue

        priority = get_conflict_priority(user, manual_change.field_name)
        if priority == PRIORITY_DINGTALK and dingtalk_is_newer_than_change(
            record,
            manual_change,
            baseline_timestamp=baseline_timestamp,
        ):
            continue

        apply_field_value(record, manual_change.field_name, manual_change.new_value)
        manual_change.merged_to_truth = True
        manual_change.merged_at = now
        record.last_manual_edit = now
        record.updated_at = now

    db.commit()

    logger.info(
        "Excel upload processed: user_id=%s company_id=%s period=%s-%02d "
        "snapshot_id=%s changes=%s conflicts=%s employees_modified=%s",
        user.id,
        user.company_id,
        year,
        month,
        snapshot.id,
        len(all_changes),
        conflict_result.conflicts_created,
        len(modified_employees),
    )

    return ExcelUploadResult(
        year=year,
        month=month,
        snapshot_id=snapshot.id,
        changes_detected=len(all_changes),
        conflicts_created=conflict_result.conflicts_created,
        employees_modified=len(modified_employees),
        pending_conflicts_count=conflict_result.pending_conflicts_count,
        changes=all_changes,
    )


async def handle_excel_upload(
    db: Session,
    user: User,
    year: int,
    month: int,
    upload: UploadFile,
) -> ExcelUploadResult:
    if not upload.filename or not upload.filename.lower().endswith((".xlsx", ".xlsm")):
        raise ExcelUploadError("File must be an Excel workbook (.xlsx)")

    temp_path = await _save_upload_to_tempfile(upload)
    try:
        parsed = parse_attendance_workbook(temp_path, year=year, month=month)
        if not parsed.employees:
            raise ExcelUploadError("No employee rows found in uploaded workbook")
        return process_excel_upload(db, user, year, month, parsed)
    except ValueError as exc:
        raise ExcelUploadError(str(exc)) from exc
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            logger.warning("Failed to remove upload temp file: %s", temp_path)
