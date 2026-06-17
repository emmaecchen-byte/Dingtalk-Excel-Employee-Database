"""DingTalk webhook API: receive callbacks, admin management, and test endpoints."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.config import settings
from app.database import get_db
from app.models import User, WebhookEvent
from app.schemas import (
    WebhookConfigResponse,
    WebhookEventListResponse,
    WebhookEventResponse,
    WebhookReplayResponse,
    WebhookTestRequest,
    WebhookTestResponse,
)
from app.services.webhook_event_service import (
    create_webhook_event,
    get_webhook_event,
    list_webhook_events,
    reset_webhook_event_for_replay,
)
from app.webhooks.dingtalk_crypto import DingTalkWebhookError
from app.webhooks.processor import (
    build_webhook_response,
    parse_request_body,
    process_webhook_event,
    run_webhook_background,
)
from app.webhooks.signature import WebhookSignatureError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])
ADMIN_ROLES = ["hr_admin"]


def _webhook_error_response(exc: Exception, status_code: int) -> HTTPException:
    message = getattr(exc, "message", str(exc))
    logger.error("DingTalk webhook error: %s", message)
    return HTTPException(status_code=status_code, detail=message)


def _verify_webhook_ip(request: Request) -> None:
    allowed = [ip.strip() for ip in settings.webhook_allowed_ips.split(",") if ip.strip()]
    if not allowed:
        return
    client_ip = request.client.host if request.client else ""
    if client_ip not in allowed:
        logger.warning("Webhook rejected from non-whitelisted IP: %s", client_ip)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Webhook source IP is not allowed",
        )


def _serialize_webhook_event(event: WebhookEvent) -> WebhookEventResponse:
    return WebhookEventResponse(
        id=event.id,
        company_id=event.company_id,
        source=event.source,
        endpoint=event.endpoint,
        event_type=event.event_type,
        dingtalk_user_id=event.dingtalk_user_id,
        event_id=event.event_id,
        status=event.status,
        payload=event.payload or {},
        error_message=event.error_message,
        pending_update_id=event.pending_update_id,
        processed_at=event.processed_at,
        created_at=event.created_at,
    )


def _public_base_url(request: Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if forwarded_host:
        scheme = forwarded_proto or request.url.scheme
        return f"{scheme}://{forwarded_host}".rstrip("/")
    return str(request.base_url).rstrip("/")


async def _receive_dingtalk_webhook(
    *,
    request: Request,
    db: Session,
    background_tasks: BackgroundTasks,
    endpoint: str,
    default_event_type: Optional[str] = None,
    msg_signature: Optional[str] = None,
    timestamp: Optional[str] = None,
    nonce: Optional[str] = None,
) -> Dict[str, Any]:
    _verify_webhook_ip(request)
    raw_body = await request.body()
    logger.info(
        "Received DingTalk webhook on %s (%s bytes)",
        request.url.path,
        len(raw_body),
    )

    try:
        payload = parse_request_body(
            raw_body=raw_body,
            headers=request.headers,
            query_msg_signature=msg_signature,
            query_timestamp=timestamp,
            query_nonce=nonce,
        )
    except WebhookSignatureError as exc:
        raise _webhook_error_response(exc, status.HTTP_401_UNAUTHORIZED)
    except DingTalkWebhookError as exc:
        raise _webhook_error_response(exc, status.HTTP_400_BAD_REQUEST)

    if default_event_type and not payload.get("event_type"):
        payload["event_type"] = default_event_type

    event = create_webhook_event(
        db,
        endpoint=endpoint,
        payload=payload,
        headers=dict(request.headers),
    )
    db.commit()
    db.refresh(event)

    background_tasks.add_task(run_webhook_background, event.id)

    response = build_webhook_response()
    response["webhook_event_id"] = event.id
    response["status"] = "queued"
    return response


@router.post("/dingtalk/attendance", status_code=status.HTTP_200_OK)
async def dingtalk_attendance_webhook(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    msg_signature: Optional[str] = Query(None, alias="msg_signature"),
    timestamp: Optional[str] = Query(None),
    nonce: Optional[str] = Query(None),
):
    """
    Receive DingTalk attendance webhooks (check-in, leave approved, overtime approved).

    Returns 200 immediately and processes the event in a background task.
    """
    result = await _receive_dingtalk_webhook(
        request=request,
        db=db,
        background_tasks=background_tasks,
        endpoint="attendance",
        default_event_type=None,
        msg_signature=msg_signature,
        timestamp=timestamp,
        nonce=nonce,
    )
    response.status_code = status.HTTP_200_OK
    return result


@router.post("/dingtalk/employee", status_code=status.HTTP_200_OK)
async def dingtalk_employee_webhook(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    msg_signature: Optional[str] = Query(None, alias="msg_signature"),
    timestamp: Optional[str] = Query(None),
    nonce: Optional[str] = Query(None),
):
    """Receive DingTalk employee change webhooks (joined, left, profile updated)."""
    result = await _receive_dingtalk_webhook(
        request=request,
        db=db,
        background_tasks=background_tasks,
        endpoint="employee",
        default_event_type=None,
        msg_signature=msg_signature,
        timestamp=timestamp,
        nonce=nonce,
    )
    response.status_code = status.HTTP_200_OK
    return result


@router.get("/config", response_model=WebhookConfigResponse)
def webhook_config(
    request: Request,
    current_user: User = Depends(require_roles(ADMIN_ROLES)),
):
    """Registration URLs and security settings for DingTalk webhook setup."""
    base_url = _public_base_url(request)
    return WebhookConfigResponse(
        attendance_url=f"{base_url}/api/webhooks/dingtalk/attendance",
        employee_url=f"{base_url}/api/webhooks/dingtalk/employee",
        legacy_attendance_url=f"{base_url}/webhook/dingtalk/attendance",
        webhook_secret_configured=bool(settings.dingtalk_webhook_secret),
        webhook_crypto_configured=settings.dingtalk_webhook_configured,
        timestamp_max_skew_seconds=settings.webhook_timestamp_max_skew_seconds,
        allowed_ips=[
            ip.strip() for ip in settings.webhook_allowed_ips.split(",") if ip.strip()
        ],
        demo_mode=settings.demo_mode,
        supported_event_types=[
            "attendance_check",
            "leave_approved",
            "overtime_approved",
            "employee_joined",
            "employee_left",
            "employee_changed",
        ],
    )


@router.get("/events", response_model=WebhookEventListResponse)
def list_events(
    limit: int = Query(50, ge=1, le=200),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ADMIN_ROLES)),
):
    events = list_webhook_events(
        db,
        company_id=current_user.company_id,
        limit=limit,
        status=status_filter,
    )
    return WebhookEventListResponse(
        events=[_serialize_webhook_event(event) for event in events],
        total=len(events),
    )


@router.post("/events/{event_id}/replay", response_model=WebhookReplayResponse)
def replay_event(
    event_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ADMIN_ROLES)),
):
    event = get_webhook_event(db, event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook event not found")
    if event.company_id and event.company_id != current_user.company_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    reset_webhook_event_for_replay(db, event)
    db.commit()
    background_tasks.add_task(run_webhook_background, event.id, skip_duplicate_check=True)

    return WebhookReplayResponse(
        success=True,
        webhook_event_id=event.id,
        status="queued",
        message="Webhook replay queued for background processing",
    )


@router.post("/test", response_model=WebhookTestResponse)
def test_webhook(
    body: WebhookTestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ADMIN_ROLES)),
):
    """
    Process a synthetic webhook payload synchronously (admin debugging).

    Skips signature verification when demo mode is enabled.
    """
    if not settings.demo_mode and not settings.dingtalk_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook test requires DEMO_MODE or DINGTALK_WEBHOOK_SECRET",
        )

    now = datetime.utcnow()
    payload: Dict[str, Any] = {
        "user_id": body.user_id,
        "event_type": body.event_type,
        "event_time": body.event_time or now.isoformat(),
        "event_id": body.event_id or f"test-{now.timestamp()}",
        "data": {
            **(body.data or {}),
            "year": body.year or now.year,
            "month": body.month or now.month,
            "work_date": body.work_date or now.strftime("%Y-%m-%d"),
        },
    }

    event = create_webhook_event(
        db,
        endpoint="test",
        payload=payload,
        headers={"x-test": "true"},
        company_id=current_user.company_id,
    )
    db.commit()

    try:
        result = process_webhook_event(
            db,
            payload,
            webhook_event=event,
            skip_duplicate_check=True,
        )
    except DingTalkWebhookError as exc:
        mark_failed = event
        mark_failed.status = "failed"
        mark_failed.error_message = exc.message if hasattr(exc, "message") else str(exc)
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    db.refresh(event)
    return WebhookTestResponse(
        success=True,
        webhook_event_id=event.id,
        pending_update_id=result.pending.id,
        pending_status=result.pending.status,
        duplicate=result.duplicate,
        message="Test webhook processed",
    )
