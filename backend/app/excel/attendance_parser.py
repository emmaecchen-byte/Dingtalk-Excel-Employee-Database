"""
Parse uploaded attendance workbooks (openpyxl read-only for large files).

Backward-compatible re-exports — prefer ``app.services.excel_parser`` for new code.
"""

from app.services.excel_parser import (
    ExcelParserError,
    ParsedEmployeeRow,
    ParsedWorkbook,
    parse_monthly_summary_sheet,
    parse_uploaded_workbook as parse_attendance_workbook,
)

__all__ = [
    "ExcelParserError",
    "ParsedEmployeeRow",
    "ParsedWorkbook",
    "parse_attendance_workbook",
    "parse_monthly_summary_sheet",
]
