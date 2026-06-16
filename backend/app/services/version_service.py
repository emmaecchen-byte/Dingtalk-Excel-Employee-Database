"""
Version history listing, comparison, and restore.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.excel.field_utils import get_field_value, normalize_numeric_value, normalize_value, snapshot_field_value
from app.models import ExcelSnapshot, ManualChange, MonthlyAttendance, User, VersionHistory
from app.services.conflict_detection import detect_conflicts, values_conflict
from app.services.snapshot_service import (
    COMPARABLE_FIELDS,
    SnapshotServiceError,
    create_snapshot_from_data,
    get_snapshot_diff,
    get_version_history,
    snapshot_employee_index,
)

logger = logging.getLogger(__name__)


class VersionServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


def _next_version_number(db: Session, company_id: int, year: int, month: int) -> int:
    current = (
        db.query(func.max(VersionHistory.version_number))
        .filter(
            VersionHistory.company_id == company_id,
            VersionHistory.year == year,
            VersionHistory.month == month,
        )
        .scalar()
    )
    return int(current or 0) + 1


def _summarize_changes(changes_summary: dict, version_note: Optional[str]) -> str:
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
        source = changes_summary.get("source_year"), changes_summary.get("source_month")
        count = changes_summary.get("employees_copied", 0)
        if source[0] and source[1]:
            return f"Cloned from {source[0]}-{int(source[1]):02d} ({count} employees)"
        return f"Month clone ({count} employees)"
    return "Attendance update"


def record_snapshot_version(
    db: Session,
    *,
    snapshot: ExcelSnapshot,
    user: User,
    employee_count: int,
) -> VersionHistory:
    version = VersionHistory(
        company_id=snapshot.company_id,
        year=snapshot.year,
        month=snapshot.month,
        version_number=_next_version_number(db, snapshot.company_id, snapshot.year, snapshot.month),
        created_by=user.name,
        created_by_user_id=user.id,
        snapshot_id=snapshot.id,
        changes_summary={
            "event": "excel_snapshot",
            "snapshot_version": snapshot.snapshot_version,
            "employee_count": employee_count,
            "file_name": snapshot.file_name,
        },
        version_note=f"Excel snapshot v{snapshot.snapshot_version}",
    )
    db.add(version)
    db.flush()
    return version


def _version_item_from_history(version: VersionHistory, user_names: Optional[Dict[int, str]] = None) -> Dict[str, Any]:
    summary = version.changes_summary or {}
    created_by = version.created_by
    if user_names and version.created_by_user_id:
        created_by = user_names.get(version.created_by_user_id) or created_by
    return {
        "id": version.id,
        "version_number": version.version_number,
        "created_at": version.created_at.isoformat() if version.created_at else None,
        "created_by": created_by,
        "summary": _summarize_changes(summary, version.version_note),
        "event_type": summary.get("event"),
        "snapshot_id": version.snapshot_id,
        "can_restore": version.snapshot_id is not None,
        "changes_summary": summary,
    }


def _version_item_from_snapshot(snapshot: ExcelSnapshot, downloader_name: str) -> Dict[str, Any]:
    employee_count = len(snapshot_employee_index(snapshot))
    return {
        "id": 0,
        "version_number": snapshot.snapshot_version,
        "created_at": (snapshot.downloaded_at or snapshot.created_at).isoformat()
        if (snapshot.downloaded_at or snapshot.created_at)
        else None,
        "created_by": downloader_name,
        "summary": f"Excel snapshot v{snapshot.snapshot_version} ({employee_count} employees)",
        "event_type": "excel_snapshot",
        "snapshot_id": snapshot.id,
        "can_restore": True,
        "changes_summary": {
            "event": "excel_snapshot",
            "snapshot_version": snapshot.snapshot_version,
            "employee_count": employee_count,
        },
    }


def list_versions(
    db: Session,
    company_id: int,
    year: int,
    month: int,
) -> List[Dict[str, Any]]:
    items = get_version_history(db, company_id, year, month)

    linked_snapshot_ids = {item["snapshot_id"] for item in items if item.get("snapshot_id")}
    orphan_snapshots = (
        db.query(ExcelSnapshot)
        .filter(
            ExcelSnapshot.company_id == company_id,
            ExcelSnapshot.year == year,
            ExcelSnapshot.month == month,
        )
        .order_by(ExcelSnapshot.snapshot_version.desc())
        .all()
    )
    orphan_snapshots = [snapshot for snapshot in orphan_snapshots if snapshot.id not in linked_snapshot_ids]

    downloader_ids = {
        snapshot.downloaded_by
        for snapshot in orphan_snapshots
        if snapshot.downloaded_by is not None
    }
    downloader_names = {
        user.id: user.name
        for user in db.query(User).filter(User.id.in_(downloader_ids)).all()
    } if downloader_ids else {}

    for snapshot in orphan_snapshots:
        name = downloader_names.get(snapshot.downloaded_by, "System") if snapshot.downloaded_by else "System"
        items.append(_version_item_from_snapshot(snapshot, name))

    items.sort(key=lambda item: item["version_number"], reverse=True)
    return items


def _resolve_snapshot_id(
    db: Session,
    company_id: int,
    *,
    version_id: Optional[int],
    snapshot_id: Optional[int],
) -> int:
    if snapshot_id is not None:
        snapshot = (
            db.query(ExcelSnapshot)
            .filter(ExcelSnapshot.id == snapshot_id, ExcelSnapshot.company_id == company_id)
            .first()
        )
        if not snapshot:
            raise VersionServiceError(f"Snapshot {snapshot_id} not found", status_code=404)
        return snapshot.id

    if version_id is None:
        raise VersionServiceError("version_id or snapshot_id is required")

    version = (
        db.query(VersionHistory)
        .filter(VersionHistory.id == version_id, VersionHistory.company_id == company_id)
        .first()
    )
    if not version:
        raise VersionServiceError(f"Version {version_id} not found", status_code=404)
    if not version.snapshot_id:
        raise VersionServiceError(
            f"Version {version_id} has no snapshot data for comparison",
            status_code=400,
        )
    return version.snapshot_id


def compare_versions(
    db: Session,
    company_id: int,
    *,
    version_id_1: Optional[int] = None,
    version_id_2: Optional[int] = None,
    snapshot_id_1: Optional[int] = None,
    snapshot_id_2: Optional[int] = None,
) -> Dict[str, Any]:
    left_snapshot_id = _resolve_snapshot_id(
        db, company_id, version_id=version_id_1, snapshot_id=snapshot_id_1
    )
    right_snapshot_id = _resolve_snapshot_id(
        db, company_id, version_id=version_id_2, snapshot_id=snapshot_id_2
    )

    diff = get_snapshot_diff(db, left_snapshot_id, right_snapshot_id)
    result = diff.to_dict()
    result["snapshot_id_1"] = left_snapshot_id
    result["snapshot_id_2"] = right_snapshot_id
    result["version_id_1"] = version_id_1
    result["version_id_2"] = version_id_2
    result["diff_text_old"] = _build_diff_text(result, side="old")
    result["diff_text_new"] = _build_diff_text(result, side="new")
    return result


def _build_diff_text(diff: Dict[str, Any], side: str) -> str:
    lines: List[str] = []
    value_key = "value_in_snapshot_1" if side == "old" else "value_in_snapshot_2"

    for employee in diff.get("added_employees", []):
        if side == "new":
            lines.append(f"+ Employee added: {employee['employee_name']} (id={employee['employee_id']})")

    for employee in diff.get("removed_employees", []):
        if side == "old":
            lines.append(f"- Employee removed: {employee['employee_name']} (id={employee['employee_id']})")

    for change in diff.get("changed_fields", []):
        value = change.get(value_key, "")
        lines.append(
            f"{change['employee_name']} / {change['field_name']}: {value}"
        )

    return "\n".join(lines) if lines else "(no differences)"


@dataclass
class RollbackFieldChange:
    employee_id: int
    employee_name: str
    field_name: str
    current_value: str
    rollback_value: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "employee_id": self.employee_id,
            "employee_name": self.employee_name,
            "field_name": self.field_name,
            "current_value": self.current_value,
            "rollback_value": self.rollback_value,
        }


def _fields_differ(current_value: str, rollback_value: str, field_name: str) -> bool:
    if field_name == "total_overtime_hours":
        return normalize_numeric_value(current_value) != normalize_numeric_value(rollback_value)
    return normalize_value(current_value) != normalize_value(rollback_value)


def _get_version_record(db: Session, company_id: int, version_id: int) -> VersionHistory:
    version = (
        db.query(VersionHistory)
        .filter(VersionHistory.id == version_id, VersionHistory.company_id == company_id)
        .first()
    )
    if not version:
        raise VersionServiceError(f"Version {version_id} not found", status_code=404)
    return version


def _get_snapshot_for_version(
    db: Session,
    company_id: int,
    version: VersionHistory,
) -> ExcelSnapshot:
    if not version.snapshot_id:
        raise VersionServiceError(
            f"Version {version.id} has no snapshot data",
            status_code=400,
        )
    snapshot = (
        db.query(ExcelSnapshot)
        .filter(ExcelSnapshot.id == version.snapshot_id, ExcelSnapshot.company_id == company_id)
        .first()
    )
    if not snapshot:
        raise VersionServiceError(f"Snapshot {version.snapshot_id} not found", status_code=404)
    return snapshot


def get_version_detail(
    db: Session,
    company_id: int,
    version_id: int,
) -> Dict[str, Any]:
    version = _get_version_record(db, company_id, version_id)
    snapshot = None
    data_snapshot: Optional[Dict[str, Any]] = None

    if version.snapshot_id:
        snapshot = (
            db.query(ExcelSnapshot)
            .filter(ExcelSnapshot.id == version.snapshot_id, ExcelSnapshot.company_id == company_id)
            .first()
        )
        if snapshot:
            data_snapshot = snapshot.data_snapshot or {}

    return {
        "id": version.id,
        "version_number": version.version_number,
        "year": version.year,
        "month": version.month,
        "created_at": version.created_at.isoformat() if version.created_at else None,
        "created_by": version.created_by,
        "changes_summary": version.changes_summary or {},
        "version_note": version.version_note,
        "snapshot_id": version.snapshot_id,
        "snapshot_data": data_snapshot,
        "data_snapshot": data_snapshot,
        "snapshot_version": snapshot.snapshot_version if snapshot else None,
    }


def _compute_rollback_changes(
    db: Session,
    company_id: int,
    snapshot: ExcelSnapshot,
) -> List[RollbackFieldChange]:
    index = snapshot_employee_index(snapshot)
    if not index:
        raise VersionServiceError("Snapshot contains no employee data", status_code=400)

    attendance_records = {
        record.employee_id: record
        for record in db.query(MonthlyAttendance)
        .filter(
            MonthlyAttendance.company_id == company_id,
            MonthlyAttendance.year == snapshot.year,
            MonthlyAttendance.month == snapshot.month,
        )
        .all()
    }

    changes: List[RollbackFieldChange] = []
    for employee_id, employee_data in index.items():
        record = attendance_records.get(employee_id)
        if not record:
            continue

        employee_name = str(employee_data.get("employee_name") or "")
        for field_name in COMPARABLE_FIELDS:
            current_value = get_field_value(record, field_name)
            rollback_value = snapshot_field_value(employee_data, field_name)
            if _fields_differ(current_value, rollback_value, field_name):
                changes.append(
                    RollbackFieldChange(
                        employee_id=int(employee_id),
                        employee_name=employee_name,
                        field_name=field_name,
                        current_value=current_value,
                        rollback_value=rollback_value,
                    )
                )
    return changes


def _snapshot_reference_time(snapshot: ExcelSnapshot) -> Optional[datetime]:
    return snapshot.downloaded_at or snapshot.created_at


def _compute_dingtalk_overwrite_warnings(
    attendance_records: Dict[int, MonthlyAttendance],
    snapshot: ExcelSnapshot,
    pending_changes: List[RollbackFieldChange],
) -> List[Dict[str, Any]]:
    """Fields where rollback would replace values newer than the target snapshot's DingTalk sync."""
    snapshot_time = _snapshot_reference_time(snapshot)
    warnings: List[Dict[str, Any]] = []

    for change in pending_changes:
        record = attendance_records.get(change.employee_id)
        if not record or not record.last_sync_from_dingtalk:
            continue
        if snapshot_time and record.last_sync_from_dingtalk <= snapshot_time:
            continue

        current_value = get_field_value(record, change.field_name)
        if not values_conflict(current_value, change.rollback_value, old_value=change.current_value):
            continue

        warnings.append(
            {
                "employee_id": change.employee_id,
                "employee_name": change.employee_name,
                "field_name": change.field_name,
                "current_value": current_value,
                "rollback_value": change.rollback_value,
                "last_sync_from_dingtalk": record.last_sync_from_dingtalk.isoformat(),
            }
        )
    return warnings


def preview_rollback(
    db: Session,
    company_id: int,
    version_id: int,
) -> Dict[str, Any]:
    version = _get_version_record(db, company_id, version_id)
    snapshot = _get_snapshot_for_version(db, company_id, version)
    changes = _compute_rollback_changes(db, company_id, snapshot)
    affected_employees = len({change.employee_id for change in changes})
    attendance_records = {
        record.employee_id: record
        for record in db.query(MonthlyAttendance)
        .filter(
            MonthlyAttendance.company_id == company_id,
            MonthlyAttendance.year == snapshot.year,
            MonthlyAttendance.month == snapshot.month,
        )
        .all()
    }
    dingtalk_warnings = _compute_dingtalk_overwrite_warnings(
        attendance_records,
        snapshot,
        changes,
    )

    return {
        "version_id": version.id,
        "version_number": version.version_number,
        "requires_confirmation": bool(changes),
        "requires_dingtalk_confirmation": bool(dingtalk_warnings),
        "fields_would_change": len(changes),
        "employees_affected": affected_employees,
        "dingtalk_overwrite_warnings": dingtalk_warnings,
        "changes": [change.to_dict() for change in changes],
    }


def rollback_to_version(
    db: Session,
    company_id: int,
    user: User,
    version_id: int,
    *,
    confirm_data_loss: bool = False,
    confirm_dingtalk_overwrite: bool = False,
) -> Dict[str, Any]:
    version = _get_version_record(db, company_id, version_id)
    snapshot = _get_snapshot_for_version(db, company_id, version)
    pending_changes = _compute_rollback_changes(db, company_id, snapshot)

    attendance_records = {
        record.employee_id: record
        for record in db.query(MonthlyAttendance)
        .filter(
            MonthlyAttendance.company_id == company_id,
            MonthlyAttendance.year == snapshot.year,
            MonthlyAttendance.month == snapshot.month,
        )
        .all()
    }
    dingtalk_warnings = _compute_dingtalk_overwrite_warnings(
        attendance_records,
        snapshot,
        pending_changes,
    )

    if pending_changes and not confirm_data_loss:
        raise VersionServiceError(
            "Rollback would overwrite current attendance data. "
            "Set confirm_data_loss=true to proceed.",
            status_code=409,
            details={
                "requires_confirmation": True,
                "fields_would_change": len(pending_changes),
                "employees_affected": len({change.employee_id for change in pending_changes}),
                "dingtalk_overwrite_warnings": dingtalk_warnings,
                "changes": [change.to_dict() for change in pending_changes],
            },
        )

    if dingtalk_warnings and not confirm_dingtalk_overwrite:
        raise VersionServiceError(
            "Rollback would overwrite newer DingTalk data. "
            "Set confirm_dingtalk_overwrite=true to proceed.",
            status_code=409,
            details={
                "requires_dingtalk_confirmation": True,
                "dingtalk_overwrite_warnings": dingtalk_warnings,
                "fields_would_change": len(pending_changes),
                "employees_affected": len({change.employee_id for change in pending_changes}),
            },
        )

    if not pending_changes:
        raise VersionServiceError(
            "Current data already matches the selected version; nothing to rollback.",
            status_code=400,
        )

    now = datetime.utcnow()
    manual_changes_batch: List[ManualChange] = []

    for change in pending_changes:
        manual_change = ManualChange(
            company_id=company_id,
            year=snapshot.year,
            month=snapshot.month,
            employee_id=change.employee_id,
            snapshot_id=snapshot.id,
            field_name=change.field_name,
            old_value=change.current_value,
            new_value=change.rollback_value,
            change_source="rollback",
            change_timestamp=now,
            changed_by=user.id,
        )
        db.add(manual_change)
        manual_changes_batch.append(manual_change)

    db.flush()

    baseline_timestamp = _snapshot_reference_time(snapshot)
    conflict_result = detect_conflicts(
        db,
        company_id,
        snapshot.year,
        snapshot.month,
        manual_changes_batch,
        user=user,
        attendance_by_employee_id=attendance_records,
        baseline_timestamp=baseline_timestamp,
        auto_apply_resolutions=True,
        respect_user_priority=False,
    )

    applied_changes: List[Dict[str, Any]] = []
    for change, manual_change in zip(pending_changes, manual_changes_batch):
        if not manual_change.merged_to_truth:
            continue
        applied_changes.append(
            {
                "employee_id": change.employee_id,
                "employee_name": change.employee_name,
                "field_name": change.field_name,
                "old_value": change.current_value,
                "new_value": change.rollback_value,
            }
        )

    rollback_data = copy.deepcopy(snapshot.data_snapshot or {})
    rollback_data["exported_at"] = now.isoformat()
    rollback_data["rollback_from_snapshot_id"] = snapshot.id
    rollback_data["rollback_from_version"] = version.version_number

    new_snapshot_id = create_snapshot_from_data(
        db,
        company_id,
        snapshot.year,
        snapshot.month,
        user.id,
        rollback_data,
        dingtalk_sync_timestamp=snapshot.dingtalk_sync_timestamp,
        file_name=f"rollback_v{version.version_number}.xlsx",
        commit=False,
    )
    for manual_change in manual_changes_batch:
        manual_change.snapshot_id = new_snapshot_id

    new_version_number = _next_version_number(db, company_id, snapshot.year, snapshot.month)
    rollback_version_row = VersionHistory(
        company_id=company_id,
        year=snapshot.year,
        month=snapshot.month,
        version_number=new_version_number,
        created_by="rollback",
        created_by_user_id=user.id,
        snapshot_id=new_snapshot_id,
        changes_summary={
            "event": "version_rollback",
            "rolled_back_to_version": version.version_number,
            "rolled_back_to_version_id": version.id,
            "rolled_back_from_snapshot_id": snapshot.id,
            "fields_changed": len(applied_changes),
            "employees_affected": len({item["employee_id"] for item in applied_changes}),
            "manual_changes_created": len(manual_changes_batch),
            "conflicts_created": conflict_result.conflicts_created,
            "dingtalk_overwrite_count": len(dingtalk_warnings),
            "changes": applied_changes,
        },
        version_note=f"Rolled back to version {version.version_number}",
    )
    db.add(rollback_version_row)
    db.commit()
    db.refresh(rollback_version_row)

    logger.info(
        "Version rollback complete: user_id=%s target_version_id=%s fields=%s conflicts=%s",
        user.id,
        version_id,
        len(applied_changes),
        conflict_result.conflicts_created,
    )

    return {
        "success": True,
        "new_version": rollback_version_row.version_number,
        "version_id": rollback_version_row.id,
        "snapshot_id": new_snapshot_id,
        "rolled_back_to_version": version.version_number,
        "rolled_back_to_version_id": version.id,
        "fields_changed": len(applied_changes),
        "employees_affected": len({item["employee_id"] for item in applied_changes}),
        "manual_changes_created": len(manual_changes_batch),
        "conflicts_created": conflict_result.conflicts_created,
        "pending_conflicts_count": conflict_result.pending_conflicts_count,
        "changes": applied_changes,
    }


def restore_version(
    db: Session,
    company_id: int,
    user: User,
    *,
    version_id: Optional[int] = None,
    snapshot_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Backward-compatible restore alias that performs a confirmed rollback."""
    if version_id is None and snapshot_id is not None:
        version = (
            db.query(VersionHistory)
            .filter(
                VersionHistory.company_id == company_id,
                VersionHistory.snapshot_id == snapshot_id,
            )
            .order_by(VersionHistory.id.desc())
            .first()
        )
        if version:
            version_id = version.id

    if version_id is None:
        raise VersionServiceError("version_id or snapshot_id is required")

    result = rollback_to_version(
        db,
        company_id,
        user,
        version_id,
        confirm_data_loss=True,
        confirm_dingtalk_overwrite=True,
    )
    return {
        "success": True,
        "restored_version_id": result["version_id"],
        "restored_from_version": result["rolled_back_to_version"],
        "employees_restored": result["employees_affected"],
        "snapshot_id": result["snapshot_id"],
    }
