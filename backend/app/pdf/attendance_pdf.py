"""Backward-compatible re-exports — prefer ``app.services.pdf_generator`` for new code."""

from app.services.pdf_generator import (
    AttendancePdfError,
    AttendancePdfResult,
    AttendancePdfRow,
    AttendancePdfStats,
    generate_attendance_pdf,
)

__all__ = [
    "AttendancePdfError",
    "AttendancePdfResult",
    "AttendancePdfRow",
    "AttendancePdfStats",
    "generate_attendance_pdf",
]
