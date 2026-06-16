import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Company, Conflict, Employee, ManualChange, MonthlyAttendance, PendingUpdate
from app.webhooks.dingtalk_crypto import DingTalkCallbackCrypto, DingTalkWebhookError

logger = logging.getLogger(__name__)

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


def parse_webhook_body(
    *,
    msg_signature: Optional[str],
    timestamp: Optional[str],
    nonce: Optional[str],
    body: Dict[str, Any],
) -> Dict[str, Any]:
    crypto = get_webhook_crypto()
    if crypto and body.get("encrypt"):
        if not msg_signature or not timestamp or not nonce:
            raise DingTalkWebhookError("Missing webhook signature parameters")
        encrypt = body["encrypt"]
        crypto.verify_signature(msg_signature, timestamp, nonce, encrypt)
        decrypted = crypto.decrypt(encrypt)
        logger.info("DingTalk webhook payload decrypted")
        return json.loads(decrypted)

    if settings.demo_mode and not body.get("encrypt"):
        return body

    raise DingTalkWebhookError("Webhook encryption required when not in demo plain-json mode")


def build_webhook_response() -> Dict[str, Any]:
    crypto = get_webhook_crypto()
    if crypto:
        return crypto.get_encrypted_response("success")
    return {"success": True}


def _resolve_company(db: Session, corp_id: Optional[str]) -> Optional[Company]:
    if not corp_id:
        return db.query(Company).first()
    return db.query(Company).filter(Company.dingtalk_corp_id == corp_id).first()


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


def _get_current_field_value(record: MonthlyAttendance, field_name: str) -> Optional[str]:
    value = getattr(record, field_name, None)
    if value is None:
        overrides = record.manual_overrides or {}
        if field_name in overrides:
            return str(overrides[field_name])
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _has_manual_edit(
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
        )
        .order_by(ManualChange.change_timestamp.desc())
        .first()
    )
    if manual_change:
        return True, manual_change.new_value

    overrides = record.manual_overrides or {}
    if field_name in overrides:
        return True, str(overrides[field_name])

    return False, None


def _apply_field_value(record: MonthlyAttendance, field_name: str, raw_value: Any) -> None:
    if field_name == "supplement_submitted":
        setattr(record, field_name, str(raw_value).lower() in {"true", "1", "y", "yes"})
        return
    if field_name in {
        "total_attendance_days",
        "absenteeism_count",
        "lateness_count",
        "missing_punch_count",
    }:
        setattr(record, field_name, int(float(raw_value)))
        return
    if field_name in {
        "total_personal_leave",
        "total_sick_leave",
        "total_annual_leave",
        "total_compensatory_leave",
        "total_overtime_hours",
    }:
        setattr(record, field_name, round(float(raw_value), 1))
        return
    setattr(record, field_name, str(raw_value))


def process_webhook_event(db: Session, event_type: str, payload: Dict[str, Any]) -> PendingUpdate:
    dingtalk_user_id = (
        payload.get("userid")
        or payload.get("userId")
        or payload.get("dingtalk_user_id")
    )
    field_name = payload.get("field_name") or payload.get("fieldName")
    dingtalk_value = payload.get("dingtalk_value") or payload.get("value") or payload.get("new_value")
    corp_id = payload.get("corp_id") or payload.get("corpId") or settings.dingtalk_corp_id

    now = datetime.utcnow()
    year = int(payload.get("year") or now.year)
    month = int(payload.get("month") or now.month)

    if not dingtalk_user_id or not field_name:
        raise DingTalkWebhookError("Webhook payload must include userid and field_name")

    if field_name not in ALLOWED_FIELDS:
        raise DingTalkWebhookError(f"Unsupported field_name: {field_name}")

    company = _resolve_company(db, corp_id)
    if not company:
        raise DingTalkWebhookError("Company not found for webhook event")

    employee = _resolve_employee(db, company.id, dingtalk_user_id)
    pending = PendingUpdate(
        company_id=company.id,
        year=year,
        month=month,
        employee_id=employee.id if employee else None,
        dingtalk_user_id=dingtalk_user_id,
        event_type=event_type,
        field_name=field_name,
        dingtalk_value=str(dingtalk_value) if dingtalk_value is not None else None,
        status="pending",
        payload=payload,
    )
    db.add(pending)
    db.flush()

    if not employee:
        pending.status = "pending"
        logger.warning("Webhook employee not found: %s", dingtalk_user_id)
        db.commit()
        return pending

    record = _get_or_create_attendance(db, company.id, employee.id, year, month)
    previous_value = _get_current_field_value(record, field_name)
    pending.previous_value = previous_value
    pending.employee_id = employee.id

    has_manual, manual_value = _has_manual_edit(
        db,
        company_id=company.id,
        employee_id=employee.id,
        year=year,
        month=month,
        field_name=field_name,
        record=record,
    )

    if has_manual and str(manual_value) != str(dingtalk_value):
        conflict = Conflict(
            company_id=company.id,
            year=year,
            month=month,
            employee_id=employee.id,
            field_name=field_name,
            dingtalk_value=str(dingtalk_value) if dingtalk_value is not None else None,
            manual_value=manual_value,
            status="pending",
        )
        db.add(conflict)
        db.flush()
        pending.status = "conflicted"
        pending.conflict_id = conflict.id
        logger.info(
            "Webhook conflict created for employee=%s field=%s",
            employee.name,
            field_name,
        )
    else:
        if dingtalk_value is not None:
            _apply_field_value(record, field_name, dingtalk_value)
        record.last_sync_from_dingtalk = now
        record.updated_at = now
        pending.status = "processed"
        pending.processed_at = now
        logger.info(
            "Webhook auto-updated employee=%s field=%s value=%s",
            employee.name,
            field_name,
            dingtalk_value,
        )

    db.commit()
    db.refresh(pending)
    return pending
