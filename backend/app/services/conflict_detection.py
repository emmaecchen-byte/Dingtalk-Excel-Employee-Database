"""
Conflict detection between DingTalk-synced data and manual HR edits.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.excel.field_utils import apply_field_value, get_field_value, normalize_value
from app.models import Conflict, ManualChange, MonthlyAttendance, User
from app.services.sync_counts import count_pending_conflicts

logger = logging.getLogger(__name__)

PRIORITY_MANUAL = "manual"
PRIORITY_DINGTALK = "dingtalk"
PRIORITY_ASK = "ask"
VALID_PRIORITIES = frozenset({PRIORITY_MANUAL, PRIORITY_DINGTALK, PRIORITY_ASK})


@dataclass
class ConflictDetectionResult:
    conflicts: List[Conflict] = field(default_factory=list)
    conflicts_created: int = 0
    pending_conflicts_count: int = 0
    auto_resolved_manual: int = 0
    auto_resolved_dingtalk: int = 0
    ignored_by_priority: int = 0


def get_conflict_priority(user: Optional[User], field_name: str) -> str:
    """Resolve effective conflict priority from user preferences."""
    if not user:
        return PRIORITY_ASK

    preferences = user.preferences or {}
    field_rules = preferences.get("conflict_field_rules") or {}
    field_priority = field_rules.get(field_name)
    if field_priority in VALID_PRIORITIES:
        return field_priority

    default_priority = preferences.get("conflict_priority", PRIORITY_ASK)
    if default_priority in VALID_PRIORITIES:
        return default_priority
    return PRIORITY_ASK


def dingtalk_is_newer_than_change(
    record: MonthlyAttendance,
    manual_change: ManualChange,
    *,
    baseline_timestamp: Optional[datetime] = None,
) -> bool:
    """
    Return True when DingTalk synced after the manual change timestamp.

    An optional *baseline_timestamp* (e.g. snapshot download time) is used when
    the manual change was captured before a DingTalk sync that landed afterward.
    """
    if not record.last_sync_from_dingtalk:
        return False

    reference_time = manual_change.change_timestamp
    if baseline_timestamp and baseline_timestamp > reference_time:
        reference_time = baseline_timestamp

    return record.last_sync_from_dingtalk > reference_time


def values_conflict(
    dingtalk_value: str,
    manual_value: str,
    *,
    old_value: Optional[str] = None,
) -> bool:
    normalized_dingtalk = normalize_value(dingtalk_value)
    normalized_manual = normalize_value(manual_value)
    if normalized_dingtalk == normalized_manual:
        return False
    if old_value is not None and normalized_dingtalk == normalize_value(old_value):
        return False
    return True


def _find_pending_conflict(
    db: Session,
    *,
    company_id: int,
    year: int,
    month: int,
    employee_id: int,
    field_name: str,
) -> Optional[Conflict]:
    return (
        db.query(Conflict)
        .filter(
            Conflict.company_id == company_id,
            Conflict.year == year,
            Conflict.month == month,
            Conflict.employee_id == employee_id,
            Conflict.field_name == field_name,
            Conflict.status == "pending",
        )
        .first()
    )


def _create_conflict_record(
    db: Session,
    *,
    company_id: int,
    year: int,
    month: int,
    employee_id: int,
    field_name: str,
    dingtalk_value: str,
    manual_value: str,
) -> Conflict:
    existing = _find_pending_conflict(
        db,
        company_id=company_id,
        year=year,
        month=month,
        employee_id=employee_id,
        field_name=field_name,
    )
    if existing:
        existing.dingtalk_value = dingtalk_value
        existing.manual_value = manual_value
        db.flush()
        return existing

    conflict = Conflict(
        company_id=company_id,
        year=year,
        month=month,
        employee_id=employee_id,
        field_name=field_name,
        dingtalk_value=dingtalk_value,
        manual_value=manual_value,
        status="pending",
    )
    db.add(conflict)
    db.flush()
    return conflict


def _load_attendance_index(
    db: Session,
    company_id: int,
    year: int,
    month: int,
) -> Dict[int, MonthlyAttendance]:
    records = (
        db.query(MonthlyAttendance)
        .filter(
            MonthlyAttendance.company_id == company_id,
            MonthlyAttendance.year == year,
            MonthlyAttendance.month == month,
        )
        .all()
    )
    return {record.employee_id: record for record in records}


def detect_conflicts(
    db: Session,
    company_id: int,
    year: int,
    month: int,
    manual_changes_list: Sequence[ManualChange],
    *,
    user: Optional[User] = None,
    attendance_by_employee_id: Optional[Dict[int, MonthlyAttendance]] = None,
    baseline_timestamp: Optional[datetime] = None,
    auto_apply_resolutions: bool = True,
) -> ConflictDetectionResult:
    """
    Compare manual edits against current DingTalk-backed attendance values.

    For each manual change, if DingTalk synced after the change timestamp and the
    values differ, either create a pending conflict or auto-resolve per user
    preference rules (manual wins / dingtalk wins / ask).
    """
    result = ConflictDetectionResult()
    if not manual_changes_list:
        result.pending_conflicts_count = count_pending_conflicts(db, company_id)
        return result

    attendance_index = attendance_by_employee_id or _load_attendance_index(
        db, company_id, year, month
    )
    now = datetime.utcnow()

    for manual_change in manual_changes_list:
        record = attendance_index.get(manual_change.employee_id)
        if not record:
            logger.warning(
                "Conflict detection skipped: no attendance for employee_id=%s",
                manual_change.employee_id,
            )
            continue

        if not dingtalk_is_newer_than_change(
            record,
            manual_change,
            baseline_timestamp=baseline_timestamp,
        ):
            continue

        dingtalk_value = get_field_value(record, manual_change.field_name)
        manual_value = manual_change.new_value or ""
        if not values_conflict(
            dingtalk_value,
            manual_value,
            old_value=manual_change.old_value,
        ):
            continue

        priority = get_conflict_priority(user, manual_change.field_name)

        if priority == PRIORITY_MANUAL:
            if auto_apply_resolutions:
                apply_field_value(record, manual_change.field_name, manual_value)
                record.last_manual_edit = now
                record.updated_at = now
                manual_change.merged_to_truth = True
                manual_change.merged_at = now
            result.auto_resolved_manual += 1
            result.ignored_by_priority += 1
            logger.info(
                "Conflict auto-resolved (manual priority): employee_id=%s field=%s",
                manual_change.employee_id,
                manual_change.field_name,
            )
            continue

        if priority == PRIORITY_DINGTALK:
            manual_change.merged_to_truth = False
            result.auto_resolved_dingtalk += 1
            result.ignored_by_priority += 1
            logger.info(
                "Conflict auto-resolved (dingtalk priority): employee_id=%s field=%s",
                manual_change.employee_id,
                manual_change.field_name,
            )
            continue

        conflict = _create_conflict_record(
            db,
            company_id=company_id,
            year=year,
            month=month,
            employee_id=manual_change.employee_id,
            field_name=manual_change.field_name,
            dingtalk_value=dingtalk_value,
            manual_value=manual_value,
        )
        manual_change.merged_to_truth = False
        result.conflicts.append(conflict)
        result.conflicts_created += 1

    result.pending_conflicts_count = count_pending_conflicts(db, company_id)

    logger.info(
        "Conflict detection complete: company_id=%s period=%s-%02d "
        "created=%s pending_total=%s auto_manual=%s auto_dingtalk=%s",
        company_id,
        year,
        month,
        result.conflicts_created,
        result.pending_conflicts_count,
        result.auto_resolved_manual,
        result.auto_resolved_dingtalk,
    )

    return result
