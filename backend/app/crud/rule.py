"""Backward-compatible alias — prefer ``app.crud.attendance_rule``."""

from app.crud.attendance_rule import CRUDAttendanceRule, attendance_rule

__all__ = ["CRUDAttendanceRule", "attendance_rule"]
