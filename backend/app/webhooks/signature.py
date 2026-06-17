"""DingTalk webhook HMAC signature verification."""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Mapping, Optional

from app.config import settings

logger = logging.getLogger(__name__)


class WebhookSignatureError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _header_value(headers: Mapping[str, str], *names: str) -> Optional[str]:
    lowered = {key.lower(): value for key, value in headers.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value:
            return value
    return None


def extract_signature_headers(headers: Mapping[str, str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Read timestamp, nonce, and signature from request headers."""
    timestamp = _header_value(
        headers,
        "x-dingtalk-timestamp",
        "dingtalk-timestamp",
        "timestamp",
        "x-timestamp",
    )
    nonce = _header_value(
        headers,
        "x-dingtalk-nonce",
        "dingtalk-nonce",
        "nonce",
        "x-nonce",
    )
    signature = _header_value(
        headers,
        "x-dingtalk-signature",
        "dingtalk-signature",
        "signature",
        "x-signature",
        "sign",
    )
    return timestamp, nonce, signature


def compute_webhook_signature(secret: str, timestamp: str, nonce: str, body: bytes) -> str:
    """HMAC-SHA256 hex digest used to verify DingTalk webhook callbacks."""
    message = f"{timestamp}\n{nonce}\n".encode("utf-8") + body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _timestamp_to_epoch_seconds(timestamp: str) -> int:
    try:
        value = int(timestamp.strip())
    except (TypeError, ValueError) as exc:
        raise WebhookSignatureError("Invalid webhook timestamp") from exc
    if value >= 1_000_000_000_000:
        return value // 1000
    return value


def verify_webhook_timestamp(
    timestamp: str,
    *,
    max_skew_seconds: Optional[int] = None,
) -> None:
    """Reject replayed webhooks when timestamp is outside the allowed window."""
    skew_limit = max_skew_seconds if max_skew_seconds is not None else settings.webhook_timestamp_max_skew_seconds
    if skew_limit <= 0:
        return

    event_epoch = _timestamp_to_epoch_seconds(timestamp)
    now_epoch = int(time.time())
    if abs(now_epoch - event_epoch) > skew_limit:
        logger.warning(
            "Webhook timestamp rejected: event=%s now=%s skew_limit=%s",
            event_epoch,
            now_epoch,
            skew_limit,
        )
        raise WebhookSignatureError("Webhook timestamp outside allowed window")


def verify_webhook_signature(
    *,
    headers: Mapping[str, str],
    body: bytes,
    secret: Optional[str] = None,
) -> None:
    """
    Verify webhook signature from headers.

    Skips verification when DEMO_MODE is enabled and no secret is configured.
    """
    webhook_secret = secret or settings.dingtalk_webhook_secret
    if not webhook_secret:
        if settings.demo_mode:
            logger.debug("Webhook signature verification skipped (demo mode, no secret)")
            return
        raise WebhookSignatureError("DINGTALK_WEBHOOK_SECRET is not configured")

    timestamp, nonce, signature = extract_signature_headers(headers)
    if not timestamp or not nonce or not signature:
        raise WebhookSignatureError("Missing webhook signature headers (timestamp, nonce, signature)")

    verify_webhook_timestamp(timestamp)

    expected = compute_webhook_signature(webhook_secret, timestamp, nonce, body)
    if not hmac.compare_digest(expected, signature):
        logger.warning(
            "Webhook signature mismatch: timestamp=%s nonce=%s",
            timestamp,
            nonce,
        )
        raise WebhookSignatureError("Invalid webhook signature")

    logger.debug("Webhook signature verified for timestamp=%s", timestamp)
