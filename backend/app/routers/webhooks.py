import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.routers.webhooks_api import _receive_dingtalk_webhook, _webhook_error_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhooks-legacy"])


@router.get("/status")
def webhook_status():
    return {
        "status": "ok",
        "webhook_secret_configured": bool(settings.dingtalk_webhook_secret),
        "webhook_crypto_configured": settings.dingtalk_webhook_configured,
        "demo_mode": settings.demo_mode,
        "endpoints": [
            "/api/webhooks/dingtalk/attendance",
            "/api/webhooks/dingtalk/employee",
            "/webhook/dingtalk/attendance",
            "/webhook/dingtalk/leave",
        ],
    }


async def _handle_dingtalk_webhook_legacy(
    *,
    request: Request,
    db: Session,
    background_tasks: BackgroundTasks,
    endpoint: str,
    default_event_type: Optional[str],
    msg_signature: Optional[str],
    timestamp: Optional[str],
    nonce: Optional[str],
) -> Dict[str, Any]:
    try:
        return await _receive_dingtalk_webhook(
            request=request,
            db=db,
            background_tasks=background_tasks,
            endpoint=endpoint,
            default_event_type=default_event_type,
            msg_signature=msg_signature,
            timestamp=timestamp,
            nonce=nonce,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _webhook_error_response(exc, status.HTTP_500_INTERNAL_SERVER_ERROR)


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
    """Legacy attendance webhook route; delegates to /api/webhooks handler."""
    result = await _handle_dingtalk_webhook_legacy(
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


@router.post("/dingtalk/leave", status_code=status.HTTP_200_OK)
async def dingtalk_leave_webhook(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    msg_signature: Optional[str] = Query(None, alias="msg_signature"),
    timestamp: Optional[str] = Query(None),
    nonce: Optional[str] = Query(None),
):
    """Legacy leave webhook route."""
    result = await _handle_dingtalk_webhook_legacy(
        request=request,
        db=db,
        background_tasks=background_tasks,
        endpoint="attendance",
        default_event_type="leave_approved",
        msg_signature=msg_signature,
        timestamp=timestamp,
        nonce=nonce,
    )
    response.status_code = status.HTTP_200_OK
    return result
