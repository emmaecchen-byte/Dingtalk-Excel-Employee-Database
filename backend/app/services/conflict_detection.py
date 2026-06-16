"""
Conflict detection between DingTalk-synced data and manual HR edits.

Backward-compatible re-exports — prefer ``app.services.conflict_detector`` for new code.
"""

from app.services.conflict_detector import (
    PRIORITY_ASK,
    PRIORITY_DINGTALK,
    PRIORITY_MANUAL,
    VALID_PRIORITIES,
    ConflictDetectionResult,
    ConflictDetectorError,
    WebhookConflictCheckResult,
    check_for_conflicts_on_update,
    detect_conflicts,
    dingtalk_is_newer_than_change,
    get_conflict_priority,
    values_conflict,
)

__all__ = [
    "PRIORITY_ASK",
    "PRIORITY_DINGTALK",
    "PRIORITY_MANUAL",
    "VALID_PRIORITIES",
    "ConflictDetectionResult",
    "ConflictDetectorError",
    "WebhookConflictCheckResult",
    "check_for_conflicts_on_update",
    "detect_conflicts",
    "dingtalk_is_newer_than_change",
    "get_conflict_priority",
    "values_conflict",
]
