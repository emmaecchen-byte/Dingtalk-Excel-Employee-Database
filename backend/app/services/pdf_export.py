"""
Period attendance PDF export (ReportLab, landscape).

Produces a print-ready report with:
- Monthly attendance grid (Figure 2)
- Exception / supplement notes table (Figure 3)
- Company name, month, and generation date on every page
"""

from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from typing import List, Sequence

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.crud.abnormal_record import abnormal_record
from app.crud.attendance_period import attendance_period
from app.excel.template_generator import COMPANY_NAME, is_calendar_weekend, monthly_day_header_label
from app.models import AbnormalRecord, EmployeeAttendance
from app.services.attendance_period_table import compute_row_totals
from app.services.attendance_rule_engine import load_company_rules
from app.services.exception_detection import EXCEPTION_LABELS
from app.services.export import (
    PeriodExportError,
    SITUATION_HEADERS,
    _format_dates_column,
    _half_day_symbol,
    _load_employees,
    _load_period,
    _supplement_label,
)
from app.services.pdf_generator import (
    BRAND_BLUE,
    BRAND_BORDER,
    BRAND_LIGHT,
    BRAND_MUTED,
    BRAND_NAVY,
    FONT_NAME,
    _make_page_footer,
    _styles,
)

logger = logging.getLogger(__name__)

PDF_FONT_SIZE = 8
PDF_DAY_COL_WIDTH = 5.0 * mm
PDF_NAME_COL_WIDTH = 14 * mm
PDF_SHIFT_COL_WIDTH = 8 * mm
PDF_TOTAL_COL_WIDTH = 8 * mm
WEEKEND_FILL_COLOR = colors.HexColor("#f0f0f0")
HEADER_BAND_HEIGHT = 20 * mm
EMPLOYEES_PER_ATTENDANCE_CHUNK = 35


@dataclass
class PeriodPdfExportResult:
    content: bytes
    filename: str
    period_id: int
    year: int
    month: int
    employee_count: int
    exception_count: int


def _resolve_company_name(db: Session, company_id: int) -> str:
    from app.models import Company

    company = db.query(Company).filter(Company.id == company_id).first()
    if company and company.name and company.name not in {"Demo Company", "demo"}:
        return company.name
    return COMPANY_NAME


def _pdf_cell_styles(base_styles: dict) -> dict:
    return {
        **base_styles,
        "cell": ParagraphStyle(
            "pdf_cell",
            parent=base_styles["body"],
            fontName=FONT_NAME,
            fontSize=PDF_FONT_SIZE,
            leading=PDF_FONT_SIZE + 2,
            alignment=TA_CENTER,
        ),
        "header": ParagraphStyle(
            "pdf_header",
            parent=base_styles["body"],
            fontName=FONT_NAME,
            fontSize=PDF_FONT_SIZE,
            leading=PDF_FONT_SIZE + 2,
            alignment=TA_CENTER,
            textColor=colors.white,
        ),
        "left_cell": ParagraphStyle(
            "pdf_left_cell",
            parent=base_styles["body"],
            fontName=FONT_NAME,
            fontSize=PDF_FONT_SIZE,
            leading=PDF_FONT_SIZE + 3,
            alignment=TA_LEFT,
        ),
    }


def _make_page_header_and_footer(
    company_name: str,
    year: int,
    month: int,
    generated_at: datetime,
):
    period_label = f"{year}年{month:02d}月 考勤报表"
    generated_label = generated_at.strftime("%Y-%m-%d %H:%M")
    footer = _make_page_footer(generated_at)

    def _draw_page(canvas, doc) -> None:
        canvas.saveState()
        page_width, page_height = landscape(A4)
        left = 14 * mm
        right = page_width - 14 * mm
        top = page_height - 10 * mm
        band_bottom = top - HEADER_BAND_HEIGHT

        canvas.setFillColor(BRAND_NAVY)
        canvas.rect(left, band_bottom, right - left, HEADER_BAND_HEIGHT, fill=1, stroke=0)

        canvas.setFillColor(colors.white)
        canvas.setFont(FONT_NAME, 14)
        canvas.drawString(left + 4 * mm, band_bottom + 11 * mm, company_name)

        canvas.setFont(FONT_NAME, 10)
        canvas.setFillColor(colors.HexColor("#d6e4ff"))
        canvas.drawString(left + 4 * mm, band_bottom + 5 * mm, period_label)

        canvas.setFont(FONT_NAME, PDF_FONT_SIZE)
        canvas.drawRightString(right - 4 * mm, band_bottom + 5 * mm, f"生成时间：{generated_label}")

        canvas.restoreState()
        footer(canvas, doc)

    return _draw_page


def _attendance_pdf_col_widths(days_in_month: int) -> List[float]:
    widths = [PDF_NAME_COL_WIDTH, PDF_SHIFT_COL_WIDTH]
    widths.extend([PDF_DAY_COL_WIDTH] * days_in_month)
    widths.extend([PDF_TOTAL_COL_WIDTH] * 4)
    return widths


def _build_attendance_pdf_table(
    employees: Sequence[EmployeeAttendance],
    *,
    year: int,
    month: int,
    styles: dict,
    rules,
) -> Table:
    days_in_month = calendar.monthrange(year, month)[1]
    day_headers = [monthly_day_header_label(year, month, day) for day in range(1, days_in_month + 1)]
    summary_headers = ["出勤", "旷工", "迟到", "缺卡"]
    header_labels = ["姓名", "班次"] + day_headers + summary_headers
    data: List[List] = [[Paragraph(label, styles["header"]) for label in header_labels]]

    for employee_row in employees:
        daily_by_day = {item.day: item for item in employee_row.daily_records}
        name = employee_row.employee_name or ""
        for shift, shift_label in (("morning", "上午"), ("afternoon", "下午")):
            row: List = [
                Paragraph(name, styles["cell"]),
                Paragraph(shift_label, styles["cell"]),
            ]
            for day in range(1, days_in_month + 1):
                record = daily_by_day.get(day)
                if shift == "morning":
                    symbol = _half_day_symbol(record.morning_status if record else None, rules)
                else:
                    symbol = _half_day_symbol(record.afternoon_status if record else None, rules)
                row.append(Paragraph(symbol or "·", styles["cell"]))
            totals = compute_row_totals(
                daily_by_day,
                year=year,
                month=month,
                shift=shift,
                rules=rules,
            )
            row.extend(
                [
                    Paragraph(str(totals["present"]), styles["cell"]),
                    Paragraph(str(totals["absenteeism"]), styles["cell"]),
                    Paragraph(str(totals["lateness"]), styles["cell"]),
                    Paragraph(str(totals["missing_punch"]), styles["cell"]),
                ]
            )
            data.append(row)

    table = Table(data, colWidths=_attendance_pdf_col_widths(days_in_month), repeatRows=1)
    style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_NAVY),
        ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
        ("FONTSIZE", (0, 0), (-1, -1), PDF_FONT_SIZE),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.35, BRAND_BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafafa")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]
    day_col_start = 2
    for day in range(1, days_in_month + 1):
        if is_calendar_weekend(year, month, day):
            col = day_col_start + day - 1
            style_commands.append(("BACKGROUND", (col, 0), (col, -1), WEEKEND_FILL_COLOR))
    summary_start = day_col_start + days_in_month
    style_commands.append(("BACKGROUND", (summary_start, 0), (-1, 0), BRAND_BLUE))
    table.setStyle(TableStyle(style_commands))
    return table


def _attendance_table_flow(
    employees: Sequence[EmployeeAttendance],
    *,
    year: int,
    month: int,
    styles: dict,
    base_styles: dict,
    rules,
) -> List:
    if not employees:
        return [Paragraph("暂无考勤数据。", base_styles["body"])]

    flow: List = []
    chunks = [
        employees[index : index + EMPLOYEES_PER_ATTENDANCE_CHUNK]
        for index in range(0, len(employees), EMPLOYEES_PER_ATTENDANCE_CHUNK)
    ]
    for index, chunk in enumerate(chunks):
        if index > 0:
            flow.append(PageBreak())
            flow.append(Paragraph("考勤签字表（续）", base_styles["section"]))
            flow.append(Spacer(1, 2 * mm))
        flow.append(
            _build_attendance_pdf_table(
                chunk,
                year=year,
                month=month,
                styles=styles,
                rules=rules,
            )
        )
    return flow


def _build_exception_pdf_table(
    records: Sequence[AbnormalRecord],
    styles: dict,
) -> Table:
    headers = list(SITUATION_HEADERS)
    data: List[List] = [[Paragraph(h, styles["header"]) for h in headers]]
    if not records:
        data.append(
            [
                Paragraph("本月无异常记录", styles["cell"]),
                Paragraph("", styles["cell"]),
                Paragraph("", styles["cell"]),
                Paragraph("", styles["cell"]),
                Paragraph("", styles["cell"]),
            ]
        )
    else:
        for record in records:
            data.append(
                [
                    Paragraph(record.employee_name, styles["cell"]),
                    Paragraph(_format_dates_column(record) or record.summary, styles["cell"]),
                    Paragraph(
                        record.summary
                        or EXCEPTION_LABELS.get(record.exception_type, record.exception_type),
                        styles["left_cell"],
                    ),
                    Paragraph(_supplement_label(record.supplement_status), styles["cell"]),
                    Paragraph(record.notes or "", styles["left_cell"]),
                ]
            )

    page_width = landscape(A4)[0] - 28 * mm
    col_widths = [20 * mm, 30 * mm, 64 * mm, 20 * mm, page_width - 134 * mm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BRAND_NAVY),
                ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
                ("FONTSIZE", (0, 0), (-1, -1), PDF_FONT_SIZE),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("ALIGN", (2, 1), (2, -1), "LEFT"),
                ("ALIGN", (4, 1), (4, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.35, BRAND_BORDER),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BRAND_LIGHT]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def generate_period_pdf(
    db: Session,
    period_id: int,
    company_id: int,
) -> PeriodPdfExportResult:
    """Build a landscape PDF for one attendance period."""
    period = _load_period(db, period_id, company_id)
    employees = _load_employees(db, period_id)
    if not employees:
        raise PeriodExportError("No attendance data found for this period", status_code=404)

    exceptions = abnormal_record.list_for_period(
        db,
        period_id=period_id,
        company_id=company_id,
    )

    rules = load_company_rules(db, company_id)
    generated_at = datetime.utcnow()
    company_name = _resolve_company_name(db, company_id)
    base_styles = _styles()
    styles = _pdf_cell_styles(base_styles)
    page_decorator = _make_page_header_and_footer(
        company_name,
        period.year,
        period.month,
        generated_at,
    )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=10 * mm + HEADER_BAND_HEIGHT + 4 * mm,
        bottomMargin=16 * mm,
        title=f"Attendance Period {period.year}-{period.month:02d}",
        author="DingTalk Attendance System",
    )

    story: List = [
        Paragraph("考勤签字表", base_styles["section"]),
        Spacer(1, 2 * mm),
        *_attendance_table_flow(
            employees,
            year=period.year,
            month=period.month,
            styles=styles,
            base_styles=base_styles,
            rules=rules,
        ),
        PageBreak(),
        Paragraph("情况说明 / 异常处理", base_styles["section"]),
        Spacer(1, 2 * mm),
        _build_exception_pdf_table(exceptions, styles),
    ]

    doc.build(story, onFirstPage=page_decorator, onLaterPages=page_decorator)
    content = buffer.getvalue()
    buffer.close()

    filename = f"attendance_period_{period.year}_{period.month:02d}_{period_id}.pdf"
    logger.info(
        "Period PDF export generated period_id=%s company_id=%s employees=%s exceptions=%s bytes=%s",
        period_id,
        company_id,
        len(employees),
        len(exceptions),
        len(content),
    )

    return PeriodPdfExportResult(
        content=content,
        filename=filename,
        period_id=period_id,
        year=period.year,
        month=period.month,
        employee_count=len(employees),
        exception_count=len(exceptions),
    )


def generate_period_pdf_for_month(
    db: Session,
    company_id: int,
    year: int,
    month: int,
) -> PeriodPdfExportResult:
    """Resolve the latest period for a calendar month and export its PDF."""
    period = attendance_period.get_by_company_period(db, company_id, year, month)
    if not period:
        raise PeriodExportError(
            f"No attendance period found for {year}-{month:02d}",
            status_code=404,
        )
    return generate_period_pdf(db, period.id, company_id)
