"""
Populate the master attendance Excel template from database records.

Backward-compatible re-exports — prefer ``app.services.excel_generator`` for new code.
"""

from app.services.excel_generator import (
    ANOMALY_SYMBOLS,
    ExcelExportResult,
    ExcelGeneratorError as AttendanceExcelError,
    MASTER_TEMPLATE_PATH as DEFAULT_TEMPLATE_PATH,
    combined_day_status,
    ensure_master_template,
    first_anomaly_date,
    generate_attendance_excel,
    get_day_value,
    populate_workbook,
    resolve_day_value,
    split_day_halves,
)

__all__ = [
    "ANOMALY_SYMBOLS",
    "AttendanceExcelError",
    "DEFAULT_TEMPLATE_PATH",
    "ExcelExportResult",
    "combined_day_status",
    "ensure_master_template",
    "first_anomaly_date",
    "generate_attendance_excel",
    "get_day_value",
    "populate_workbook",
    "resolve_day_value",
    "split_day_halves",
]
