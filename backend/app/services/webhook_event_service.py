"""Persist and query DingTalk webhook audit events."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional

from sqlalchemy.orm import Session

from app.models import WebhookEvent

logger = logging.getLogger(__name__)


def create_webhook_event(
    db: Session,
    *,
    endpoint: str,
    payload: Dict[str, Any],
    headers: Mapping[str, str],
    company_id: Optional[int] = None,
) -> WebhookEvent:
    user_id = (
        payload.get("user_id")
        or payload.get("userid")
        or payload.get("userId")
        or payload.get("dingtalk_user_id")
    )
    event_type = str(payload.get("event_type") or payload.get("EventType") or "unknown")
    event_id = str(
        payload.get("event_id")
        or payload.get("EventId")
        or f"{user_id or 'system'}:{event_type}:{payload.get('event_time', '')}"
    )
    safe_headers = {
        key: value
        for key, value in headers.items()
        if key.lower().startswith(("x-dingtalk", "dingtalk", "timestamp", "nonce", "sign", "content-type"))
    }

    event = WebhookEvent(
        company_id=company_id,
        source="dingtalk",
        endpoint=endpoint,
        event_type=event_type,
        dingtalk_user_id=str(user_id) if user_id else None,
        event_id=event_id,
        status="queued",
        payload=payload,
        headers=safe_headers,
    )
    db.add(event)
    db.flush()
    logger.info(
        "Queued webhook event id=%s endpoint=%s event_type=%s event_id=%s",
        event.id,
        endpoint,
        event_type,
        event_id,
    )
    return event


def list_webhook_events(
    db: Session,
    *,
    company_id: Optional[int] = None,
    limit: int = 50,
    status: Optional[str] = None,
) -> List[WebhookEvent]:
    query = db.query(WebhookEvent).order_by(WebhookEvent.id.desc())
    if company_id is not None:
        query = query.filter(WebhookEvent.company_id == company_id)
    if status:
        query = query.filter(WebhookEvent.status == status)
    return query.limit(limit).all()


def get_webhook_event(db: Session, event_id: int) -> Optional[WebhookEvent]:
    return db.query(WebhookEvent).filter(WebhookEvent.id == event_id).first()


def mark_webhook_event_processing(db: Session, event: WebhookEvent) -> None:
    event.status = "processing"
    db.flush()


def mark_webhook_event_result(
    db: Session,
    event: WebhookEvent,
    *,
    status: str,
    pending_update_id: Optional[int] = None,
    error_message: Optional[str] = None,
) -> None:
    event.status = status
    event.pending_update_id = pending_update_id
    event.error_message = error_message
    if status in {"processed", "duplicate", "failed"}:
        event.processed_at = datetime.utcnow()
    db.flush()


def reset_webhook_event_for_replay(db: Session, event: WebhookEvent) -> WebhookEvent:
    event.status = "queued"
    event.error_message = None
    event.processed_at = None
    event.pending_update_id = None
    db.flush()
    logger.info("Webhook event id=%s reset for replay", event.id)
    return event
