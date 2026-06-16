import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.webhooks.dingtalk_crypto import DingTalkWebhookError
from app.webhooks.processor import build_webhook_response, get_webhook_crypto, parse_webhook_body, process_webhook_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhooks"])


@router.get("/status")
def webhook_status():
    crypto = get_webhook_crypto()
    return {
        "status": "ok",
        "webhook_configured": crypto is not None,
        "demo_mode": settings.demo_mode,
        "endpoints": [
            "/webhook/dingtalk/attendance",
            "/webhook/dingtalk/leave",
        ],
    }


async def _handle_dingtalk_webhook(
    *,
    event_type: str,
    request: Request,
    db: Session,
    msg_signature: Optional[str],
    timestamp: Optional[str],
    nonce: Optional[str],
) -> Dict[str, Any]:
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body") from exc

    try:
        payload = parse_webhook_body(
            msg_signature=msg_signature,
            timestamp=timestamp,
            nonce=nonce,
            body=body,
        )
        pending = process_webhook_event(db, event_type, payload)
        response = build_webhook_response()
        response["pending_update_id"] = pending.id
        response["pending_status"] = pending.status
        return response
    except DingTalkWebhookError as exc:
        logger.error("DingTalk webhook error: %s", exc.message)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.message)


@router.post("/dingtalk/attendance")
async def dingtalk_attendance_webhook(
    request: Request,
    db: Session = Depends(get_db),
    msg_signature: Optional[str] = Query(None, alias="msg_signature"),
    timestamp: Optional[str] = Query(None),
    nonce: Optional[str] = Query(None),
):
    logger.info("Received DingTalk attendance webhook")
    return await _handle_dingtalk_webhook(
        event_type="attendance",
        request=request,
        db=db,
        msg_signature=msg_signature,
        timestamp=timestamp,
        nonce=nonce,
    )


@router.post("/dingtalk/leave")
async def dingtalk_leave_webhook(
    request: Request,
    db: Session = Depends(get_db),
    msg_signature: Optional[str] = Query(None, alias="msg_signature"),
    timestamp: Optional[str] = Query(None),
    nonce: Optional[str] = Query(None),
):
    logger.info("Received DingTalk leave webhook")
    return await _handle_dingtalk_webhook(
        event_type="leave",
        request=request,
        db=db,
        msg_signature=msg_signature,
        timestamp=timestamp,
        nonce=nonce,
    )
