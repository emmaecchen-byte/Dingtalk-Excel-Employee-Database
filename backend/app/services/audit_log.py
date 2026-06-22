"""
Central audit logging for attendance and exception edits.

Writes to the unified ``edit_logs`` table and keeps legacy per-entity logs
in sync for backward-compatible API responses.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.crud.abnormal_record import abnormal_record_edit_log
from app.crud.attendance_period_edit_log import attendance_period_edit_log
from app.crud.edit_log import edit_log
from app.models import User


def _normalize_value(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def record_edit(
    db: Session,
    *,
    period_id: int,
    company_id: int,
    user: Optional[User],
    entity_type: str,
    entity_id: int,
    field_name: str,
    old_value: Optional[str],
    new_value: Optional[str],
    action: str = "update",
) -> None:
    """Persist a unified audit log entry when a value actually changed."""
    old_text = _normalize_value(old_value)
    new_text = _normalize_value(new_value)
    if action == "update" and old_text == new_text:
        return

    edit_log.log_change(
        db,
        period_id=period_id,
        company_id=company_id,
        user=user,
        entity_type=entity_type,
        entity_id=entity_id,
        field_name=field_name,
        old_value=old_text,
        new_value=new_text,
        action=action,
    )


def log_daily_attendance_change(
    db: Session,
    *,
    period_id: int,
    company_id: int,
    daily_attendance_id: int,
    employee_name: Optional[str],
    user: Optional[User],
    field_name: str,
    old_value: Optional[str],
    new_value: Optional[str],
) -> None:
    """Log a daily attendance cell edit to unified and legacy audit tables."""
    old_text = _normalize_value(old_value)
    new_text = _normalize_value(new_value)
    if old_text == new_text:
        return

    attendance_period_edit_log.log_change(
        db,
        period_id=period_id,
        daily_attendance_id=daily_attendance_id,
        employee_name=employee_name,
        edited_by=user.id if user else None,
        editor_name=user.name if user else None,
        field_name=field_name,
        old_value=old_text,
        new_value=new_text,
    )
    record_edit(
        db,
        period_id=period_id,
        company_id=company_id,
        user=user,
        entity_type="daily_attendance",
        entity_id=daily_attendance_id,
        field_name=field_name,
        old_value=old_text,
        new_value=new_text,
        action="update",
    )


def log_abnormal_record_change(
    db: Session,
    *,
    period_id: int,
    company_id: int,
    abnormal_record_id: int,
    user: Optional[User],
    field_name: str,
    old_value: Optional[str],
    new_value: Optional[str],
    action: str = "update",
) -> None:
    """Log an abnormal record field change to unified and legacy audit tables."""
    old_text = _normalize_value(old_value)
    new_text = _normalize_value(new_value)
    if action == "update" and old_text == new_text:
        return

    if action == "update":
        abnormal_record_edit_log.log_change(
            db,
            abnormal_record_id=abnormal_record_id,
            edited_by=user.id if user else None,
            editor_name=user.name if user else None,
            field_name=field_name,
            old_value=old_text,
            new_value=new_text,
        )

    record_edit(
        db,
        period_id=period_id,
        company_id=company_id,
        user=user,
        entity_type="abnormal_record",
        entity_id=abnormal_record_id,
        field_name=field_name,
        old_value=old_text,
        new_value=new_text,
        action=action,
    )


def log_abnormal_record_created(
    db: Session,
    *,
    period_id: int,
    company_id: int,
    abnormal_record_id: int,
    user: Optional[User],
    summary: str,
) -> None:
    record_edit(
        db,
        period_id=period_id,
        company_id=company_id,
        user=user,
        entity_type="abnormal_record",
        entity_id=abnormal_record_id,
        field_name="record",
        old_value=None,
        new_value=summary,
        action="create",
    )


def log_abnormal_record_deleted(
    db: Session,
    *,
    period_id: int,
    company_id: int,
    abnormal_record_id: int,
    user: Optional[User],
    summary: str,
) -> None:
    record_edit(
        db,
        period_id=period_id,
        company_id=company_id,
        user=user,
        entity_type="abnormal_record",
        entity_id=abnormal_record_id,
        field_name="record",
        old_value=summary,
        new_value=None,
        action="delete",
    )
