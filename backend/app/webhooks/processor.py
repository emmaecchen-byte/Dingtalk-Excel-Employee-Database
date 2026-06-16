"""
DingTalk webhook event processing: sync, conflict detection, pending updates.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional, Tuple

from sqlalchemy.orm import Session

from app.config import settings
from app.excel.field_utils import apply_field_value, get_field_value
from app.models import Company, Conflict, Employee, ManualChange, MonthlyAttendance, PendingUpdate
from app.services.conflict_detection import values_conflict
from app.services.webhook_sync import SyncFieldUpdate, sync_attendance, sync_leaves
from app.webhooks.dingtalk_crypto import DingTalkCallbackCrypto, DingTalkWebhookError
from app.webhooks.signature import WebhookSignatureError, verify_webhook_signature

logger = logging.getLogger(__name__)

ATTENDANCE_EVENT_TYPES = frozenset(
    {
        "attendance_check_in",
        "attendance_check_out",
        "check_in",
        "check_out",
        "attendance",
        "punch",
    }
)
LEAVE_EVENT_TYPES = frozenset(
    {
        "leave_approval",
        "leave_approved",
        "leave",
        "leave_apply",
    }
)

ALLOWED_FIELDS = {
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
}
ALLOWED_FIELDS.update({f"day_{day}" for day in range(1, 32)})


@dataclass
class WebhookProcessResult:
    pending: PendingUpdate
    duplicate: bool = False


def get_webhook_crypto() -> Optional[DingTalkCallbackCrypto]:
    if not settings.dingtalk_webhook_token or not settings.dingtalk_webhook_aes_key:
        return None
    owner_key = settings.dingtalk_webhook_owner_key or settings.dingtalk_client_id or settings.dingtalk_corp_id
    if not owner_key:
        return None
    return DingTalkCallbackCrypto(
        settings.dingtalk_webhook_token,
        settings.dingtalk_webhook_aes_key,
        owner_key,
    )


def parse_request_body(
    *,
    raw_body: bytes,
    headers: Mapping[str, str],
    query_msg_signature: Optional[str] = None,
    query_timestamp: Optional[str] = None,
    query_nonce: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Parse and authenticate a webhook request.

    Supports:
    - HMAC header signature via DINGTALK_WEBHOOK_SECRET
    - Legacy DingTalk encrypted callback (query params + encrypt body)
    - Demo plain JSON when DEMO_MODE=true
    """
    logger.info(
        "Parsing DingTalk webhook body (%s bytes), headers=%s",
        len(raw_body),
        {k: v for k, v in headers.items() if k.lower().startswith(("x-dingtalk", "dingtalk", "timestamp", "nonce", "sign"))},
    )

    if settings.dingtalk_webhook_secret:
        verify_webhook_signature(headers=headers, body=raw_body)
    elif not settings.demo_mode:
        crypto = get_webhook_crypto()
        if not crypto:
            raise WebhookSignatureError("Configure DINGTALK_WEBHOOK_SECRET or DingTalk callback crypto keys")

    try:
        body = json.loads(raw_body.decode("utf-8") if raw_body else "{}")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DingTalkWebhookError("Invalid JSON body") from exc

    crypto = get_webhook_crypto()
    if crypto and body.get("encrypt"):
        msg_signature = query_msg_signature
        timestamp = query_timestamp
        nonce = query_nonce
        if not msg_signature or not timestamp or not nonce:
            raise DingTalkWebhookError("Missing webhook signature query parameters for encrypted payload")
        encrypt = body["encrypt"]
        crypto.verify_signature(msg_signature, timestamp, nonce, encrypt)
        decrypted = crypto.decrypt(encrypt)
        logger.info("DingTalk encrypted webhook payload decrypted")
        return json.loads(decrypted)

    if settings.demo_mode or settings.dingtalk_webhook_secret:
        return _normalize_event_payload(body)

    raise DingTalkWebhookError("Webhook encryption required when not in demo plain-json mode")


def _normalize_event_payload(body: Dict[str, Any]) -> Dict[str, Any]:
    """Map legacy flat payloads and new structured events to a common shape."""
    if body.get("user_id") or body.get("event_type"):
        return body

    user_id = body.get("userid") or body.get("userId") or body.get("dingtalk_user_id")
    field_name = body.get("field_name") or body.get("fieldName")
    value = body.get("dingtalk_value") or body.get("value") or body.get("new_value")
    now = datetime.utcnow()

    if user_id and field_name:
        return {
            "user_id": user_id,
            "event_type": body.get("event_type") or "attendance",
            "event_time": body.get("event_time") or now.isoformat(),
            "data": {
                "field_name": field_name,
                "value": value,
                "year": body.get("year") or now.year,
                "month": body.get("month") or now.month,
                "corp_id": body.get("corp_id") or body.get("corpId"),
            },
            "event_id": body.get("event_id"),
        }
    return body


def build_webhook_response() -> Dict[str, Any]:
    crypto = get_webhook_crypto()
    if crypto and not settings.dingtalk_webhook_secret:
        return crypto.get_encrypted_response("success")
    return {"success": True, "status": "ok"}


def _resolve_company(db: Session, corp_id: Optional[str]) -> Optional[Company]:
    if corp_id:
        company = db.query(Company).filter(Company.dingtalk_corp_id == corp_id).first()
        if company:
            return company
    if settings.dingtalk_corp_id:
        company = db.query(Company).filter(Company.dingtalk_corp_id == settings.dingtalk_corp_id).first()
        if company:
            return company
    return db.query(Company).first()


def _resolve_employee(db: Session, company_id: int, dingtalk_user_id: str) -> Optional[Employee]:
    return (
        db.query(Employee)
        .filter(
            Employee.company_id == company_id,
            Employee.dingtalk_user_id == dingtalk_user_id,
            Employee.is_active.is_(True),
        )
        .first()
    )


def _get_or_create_attendance(
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


def _parse_event_time(event_time: Optional[str]) -> datetime:
    if not event_time:
        return datetime.utcnow()
    text = event_time.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(event_time[: len(fmt)], fmt)
        except ValueError:
            continue
    return datetime.utcnow()


def _event_dedup_key(payload: Dict[str, Any], user_id: str, event_type: str) -> str:
    return str(
        payload.get("event_id")
        or payload.get("EventId")
        or f"{user_id}:{event_type}:{payload.get('event_time', '')}"
    )


def _find_duplicate_pending(
    db: Session,
    *,
    company_id: int,
    dingtalk_user_id: str,
    event_type: str,
    event_id: str,
) -> Optional[PendingUpdate]:
    cutoff = datetime.utcnow() - timedelta(hours=24)
    candidates = (
        db.query(PendingUpdate)
        .filter(
            PendingUpdate.company_id == company_id,
            PendingUpdate.dingtalk_user_id == dingtalk_user_id,
            PendingUpdate.event_type == event_type,
            PendingUpdate.created_at >= cutoff,
        )
        .order_by(PendingUpdate.id.desc())
        .limit(20)
        .all()
    )
    for pending in candidates:
        stored_id = (pending.payload or {}).get("event_id")
        if stored_id == event_id:
            return pending
    return None


def _pending_manual_value(
    db: Session,
    *,
    company_id: int,
    employee_id: int,
    year: int,
    month: int,
    field_name: str,
    record: MonthlyAttendance,
) -> Tuple[bool, Optional[str]]:
    manual_change = (
        db.query(ManualChange)
        .filter(
            ManualChange.company_id == company_id,
            ManualChange.employee_id == employee_id,
            ManualChange.year == year,
            ManualChange.month == month,
            ManualChange.field_name == field_name,
            ManualChange.merged_to_truth.is_(False),
        )
        .order_by(ManualChange.change_timestamp.desc())
        .first()
    )
    if manual_change and manual_change.new_value is not None:
        return True, manual_change.new_value

    manual_change = (
        db.query(ManualChange)
        .filter(
            ManualChange.company_id == company_id,
            ManualChange.employee_id == employee_id,
            ManualChange.year == year,
            ManualChange.month == month,
            ManualChange.field_name == field_name,
        )
        .order_by(ManualChange.change_timestamp.desc())
        .first()
    )
    if manual_change and manual_change.new_value is not None:
        return True, manual_change.new_value

    overrides = record.manual_overrides or {}
    if field_name in overrides:
        return True, str(overrides[field_name])

    return False, None


def _apply_field_updates(
    db: Session,
    *,
    company: Company,
    employee: Employee,
    year: int,
    month: int,
    field_updates: List[SyncFieldUpdate],
    now: datetime,
) -> Tuple[List[Dict[str, Any]], List[Conflict], int]:
    record = _get_or_create_attendance(db, company.id, employee.id, year, month)
    applied: List[Dict[str, Any]] = []
    conflicts: List[Conflict] = []

    for update in field_updates:
        if update.field_name not in ALLOWED_FIELDS:
            logger.warning("Skipping unsupported field from webhook sync: %s", update.field_name)
            continue

        previous_value = update.previous_value
        if previous_value is None:
            previous_value = get_field_value(record, update.field_name)

        has_manual, manual_value = _pending_manual_value(
            db,
            company_id=company.id,
            employee_id=employee.id,
            year=year,
            month=month,
            field_name=update.field_name,
            record=record,
        )

        if has_manual and values_conflict(
            update.dingtalk_value,
            manual_value or "",
            old_value=previous_value,
        ):
            conflict = Conflict(
                company_id=company.id,
                year=year,
                month=month,
                employee_id=employee.id,
                field_name=update.field_name,
                dingtalk_value=update.dingtalk_value,
                manual_value=manual_value,
                status="pending",
            )
            db.add(conflict)
            db.flush()
            conflicts.append(conflict)
            logger.info(
                "Webhook conflict: employee=%s field=%s dingtalk=%s manual=%s",
                employee.name,
                update.field_name,
                update.dingtalk_value,
                manual_value,
            )
            continue

        apply_field_value(record, update.field_name, update.dingtalk_value)
        applied.append(
            {
                "field_name": update.field_name,
                "previous_value": previous_value,
                "dingtalk_value": update.dingtalk_value,
            }
        )

    if applied:
        record.last_sync_from_dingtalk = now
        record.updated_at = now

    return applied, conflicts, len(applied)


def _resolve_field_updates(
    db: Session,
    *,
    company: Company,
    employee: Optional[Employee],
    event_type: str,
    data: Dict[str, Any],
    event_time: datetime,
) -> Tuple[int, int, List[SyncFieldUpdate]]:
    year = int(data.get("year") or event_time.year)
    month = int(data.get("month") or event_time.month)

    if not employee:
        return year, month, []

    normalized_type = event_type.lower().strip()

    if normalized_type in ATTENDANCE_EVENT_TYPES:
        work_date = (
            data.get("work_date")
            or data.get("date")
            or event_time.strftime("%Y-%m-%d")
        )
        return year, month, sync_attendance(
            db,
            company=company,
            employee=employee,
            work_date=str(work_date),
            webhook_data=data,
        )

    if normalized_type in LEAVE_EVENT_TYPES:
        return year, month, sync_leaves(
            db,
            company=company,
            employee=employee,
            year=year,
            month=month,
            webhook_data=data,
        )

    if data.get("field_name") or data.get("fieldName"):
        field_name = data.get("field_name") or data.get("fieldName")
        value = data.get("value") or data.get("dingtalk_value") or data.get("new_value")
        if field_name and value is not None:
            return year, month, [SyncFieldUpdate(field_name=str(field_name), dingtalk_value=str(value))]

    logger.warning("Unhandled webhook event_type=%s for user=%s", event_type, employee.dingtalk_user_id)
    return year, month, []


def process_webhook_event(db: Session, payload: Dict[str, Any]) -> WebhookProcessResult:
    """Process a normalized DingTalk webhook event."""
    user_id = (
        payload.get("user_id")
        or payload.get("userid")
        or payload.get("userId")
        or payload.get("dingtalk_user_id")
    )
    event_type = str(payload.get("event_type") or payload.get("EventType") or "attendance")
    event_time_raw = payload.get("event_time") or payload.get("EventTime")
    data = payload.get("data") or payload.get("Data") or {}
    if not isinstance(data, dict):
        data = {}

    corp_id = (
        data.get("corp_id")
        or data.get("corpId")
        or payload.get("corp_id")
        or payload.get("corpId")
        or settings.dingtalk_corp_id
    )

    if not user_id:
        raise DingTalkWebhookError("Webhook payload must include user_id")

    event_time = _parse_event_time(str(event_time_raw) if event_time_raw else None)
    event_id = _event_dedup_key(payload, user_id, event_type)

    logger.info(
        "Processing DingTalk webhook: user_id=%s event_type=%s event_time=%s event_id=%s",
        user_id,
        event_type,
        event_time.isoformat(),
        event_id,
    )

    company = _resolve_company(db, corp_id)
    if not company:
        raise DingTalkWebhookError("Company not found for webhook event")

    duplicate = _find_duplicate_pending(
        db,
        company_id=company.id,
        dingtalk_user_id=user_id,
        event_type=event_type,
        event_id=event_id,
    )
    if duplicate:
        logger.info("Duplicate webhook event ignored: event_id=%s pending_id=%s", event_id, duplicate.id)
        return WebhookProcessResult(pending=duplicate, duplicate=True)

    employee = _resolve_employee(db, company.id, user_id)
    year, month, field_updates = _resolve_field_updates(
        db,
        company=company,
        employee=employee,
        event_type=event_type,
        data=data,
        event_time=event_time,
    )

    primary_field = field_updates[0].field_name if field_updates else "webhook_event"
    primary_value = field_updates[0].dingtalk_value if field_updates else None

    pending = PendingUpdate(
        company_id=company.id,
        year=year,
        month=month,
        employee_id=employee.id if employee else None,
        dingtalk_user_id=user_id,
        event_type=event_type,
        field_name=primary_field,
        dingtalk_value=primary_value,
        status="pending",
        payload={
            **payload,
            "event_id": event_id,
            "normalized_at": datetime.utcnow().isoformat(),
            "field_updates": [item.to_dict() for item in field_updates],
        },
    )
    db.add(pending)
    db.flush()

    if not employee:
        logger.warning("Webhook employee not found: %s", user_id)
        db.commit()
        db.refresh(pending)
        return WebhookProcessResult(pending=pending)

    now = datetime.utcnow()
    applied, conflicts, applied_count = _apply_field_updates(
        db,
        company=company,
        employee=employee,
        year=year,
        month=month,
        field_updates=field_updates,
        now=now,
    )

    pending.payload = {
        **(pending.payload or {}),
        "applied_fields": applied,
        "conflicts_created": len(conflicts),
    }

    if conflicts:
        pending.status = "conflicted"
        pending.conflict_id = conflicts[0].id
        pending.previous_value = applied[0]["previous_value"] if applied else None
    elif applied_count > 0:
        pending.status = "processed"
        pending.processed_at = now
        pending.previous_value = applied[0].get("previous_value")
    else:
        pending.status = "processed"
        pending.processed_at = now

    db.commit()
    db.refresh(pending)

    logger.info(
        "Webhook processed: pending_id=%s status=%s applied=%s conflicts=%s",
        pending.id,
        pending.status,
        applied_count,
        len(conflicts),
    )
    return WebhookProcessResult(pending=pending)


# Backward-compatible aliases used by older imports.
def parse_webhook_body(
    *,
    msg_signature: Optional[str],
    timestamp: Optional[str],
    nonce: Optional[str],
    body: Dict[str, Any],
) -> Dict[str, Any]:
    raw = json.dumps(body).encode("utf-8")
    headers: Dict[str, str] = {}
    return parse_request_body(
        raw_body=raw,
        headers=headers,
        query_msg_signature=msg_signature,
        query_timestamp=timestamp,
        query_nonce=nonce,
    )
