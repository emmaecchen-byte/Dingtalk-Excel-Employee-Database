import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.webhooks.dingtalk_crypto import DingTalkWebhookError
from app.webhooks.processor import build_webhook_response, parse_request_body, process_webhook_event
from app.webhooks.signature import WebhookSignatureError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhooks"])


def _webhook_error_response(exc: Exception, status_code: int) -> HTTPException:
    message = getattr(exc, "message", str(exc))
    logger.error("DingTalk webhook error: %s", message)
    return HTTPException(status_code=status_code, detail=message)


@router.get("/status")
def webhook_status():
    return {
        "status": "ok",
        "webhook_secret_configured": bool(settings.dingtalk_webhook_secret),
        "webhook_crypto_configured": settings.dingtalk_webhook_configured,
        "demo_mode": settings.demo_mode,
        "endpoints": [
            "/webhook/dingtalk/attendance",
            "/webhook/dingtalk/leave",
        ],
    }


async def _handle_dingtalk_webhook(
    *,
    request: Request,
    db: Session,
    default_event_type: Optional[str],
    msg_signature: Optional[str],
    timestamp: Optional[str],
    nonce: Optional[str],
) -> Dict[str, Any]:
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

    result = process_webhook_event(db, payload)
    response = build_webhook_response()
    response["pending_update_id"] = result.pending.id
    response["pending_status"] = result.pending.status
    response["duplicate"] = result.duplicate
    return response


@router.post("/dingtalk/attendance", status_code=status.HTTP_200_OK)
async def dingtalk_attendance_webhook(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    msg_signature: Optional[str] = Query(None, alias="msg_signature"),
    timestamp: Optional[str] = Query(None),
    nonce: Optional[str] = Query(None),
):
    """
    Real-time DingTalk attendance webhook listener.

    Expects JSON body: ``{ user_id, event_type, event_time, data }``.
    Verifies HMAC signature from headers using ``DINGTALK_WEBHOOK_SECRET``.
    """
    result = await _handle_dingtalk_webhook(
        request=request,
        db=db,
        default_event_type=None,
        msg_signature=msg_signature,
        timestamp=timestamp,
        nonce=nonce,
    )
    response.status_code = status.HTTP_200_OK
    return result


@router.post("/dingtalk/leave", status_code=status.HTTP_200_OK)
async def dingtalk_leave_webhook(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    msg_signature: Optional[str] = Query(None, alias="msg_signature"),
    timestamp: Optional[str] = Query(None),
    nonce: Optional[str] = Query(None),
):
    """Legacy leave webhook route; delegates to the shared processor."""
    result = await _handle_dingtalk_webhook(
        request=request,
        db=db,
        default_event_type="leave_approval",
        msg_signature=msg_signature,
        timestamp=timestamp,
        nonce=nonce,
    )
    response.status_code = status.HTTP_200_OK
    return result
