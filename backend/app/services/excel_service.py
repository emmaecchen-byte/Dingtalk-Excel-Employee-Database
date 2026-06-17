"""
Excel export service — four-sheet attendance workbook generation.

Sheets:
  1. 签字           — AM/PM sign-off grid with COUNTIF summaries
  2. 情况说明       — Per-employee anomaly summaries (matches web UI)
  3. 月度汇总       — DingTalk daily status text with color fills
  4. 加班结算加班工资 — Overtime pay + 调休 sections with formulas

Implementation lives in ``app.services.excel_generator`` and
``app.excel.template_generator``; this module is the public entry point.
"""

from app.services.excel_generator import (
    ExcelExportResult,
    ExcelGeneratorError,
    ensure_master_template,
    generate_attendance_excel,
    populate_workbook,
)

__all__ = [
    "ExcelExportResult",
    "ExcelGeneratorError",
    "ensure_master_template",
    "generate_attendance_excel",
    "populate_workbook",
]
