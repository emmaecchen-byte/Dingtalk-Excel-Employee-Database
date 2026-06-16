"""
Monthly attendance PDF report generation (ReportLab).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from typing import List, Optional, Sequence

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy.orm import Session, joinedload

from app.models import Company, MonthlyAttendance

logger = logging.getLogger(__name__)

# Brand palette aligned with dashboard UI
BRAND_NAVY = colors.HexColor("#001529")
BRAND_BLUE = colors.HexColor("#1677ff")
BRAND_LIGHT = colors.HexColor("#e6f4ff")
BRAND_WARNING = colors.HexColor("#d48806")
BRAND_DANGER = colors.HexColor("#cf1322")
BRAND_MUTED = colors.HexColor("#8c8c8c")
BRAND_BORDER = colors.HexColor("#d9d9d9")

FONT_NAME = "STSong-Light"


class AttendancePdfError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


@dataclass
class AttendancePdfStats:
    total_employees: int
    total_absenteeism_days: int
    total_lateness_days: int
    total_missing_punch_days: int


@dataclass
class AttendancePdfRow:
    name: str
    department: str
    total_attendance_days: int
    absenteeism_count: int
    lateness_count: int
    missing_punch_count: int
    anomaly_summary: str
    notes: str
    status: str


@dataclass
class AttendancePdfResult:
    content: bytes
    filename: str


def _ensure_font() -> None:
    if FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(FONT_NAME))


def _styles() -> dict:
    _ensure_font()
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title",
            parent=base["Heading1"],
            fontName=FONT_NAME,
            fontSize=18,
            textColor=colors.white,
            alignment=TA_LEFT,
            leading=22,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            parent=base["Normal"],
            fontName=FONT_NAME,
            fontSize=11,
            textColor=colors.HexColor("#d6e4ff"),
            alignment=TA_LEFT,
            leading=14,
        ),
        "section": ParagraphStyle(
            "section",
            parent=base["Heading2"],
            fontName=FONT_NAME,
            fontSize=12,
            textColor=BRAND_NAVY,
            spaceBefore=10,
            spaceAfter=6,
            leading=16,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontName=FONT_NAME,
            fontSize=9,
            textColor=colors.black,
            leading=12,
        ),
        "muted": ParagraphStyle(
            "muted",
            parent=base["Normal"],
            fontName=FONT_NAME,
            fontSize=8,
            textColor=BRAND_MUTED,
            leading=10,
        ),
        "footer": ParagraphStyle(
            "footer",
            parent=base["Normal"],
            fontName=FONT_NAME,
            fontSize=8,
            textColor=BRAND_MUTED,
            alignment=TA_CENTER,
            leading=10,
        ),
    }


def _header_table(company_name: str, year: int, month: int, styles: dict) -> Table:
    period = f"{year}年{month:02d}月 考勤月报"
    data = [
        [Paragraph(company_name, styles["title"])],
        [Paragraph(period, styles["subtitle"])],
    ]
    table = Table(data, colWidths=[260 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BRAND_NAVY),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, 0), 12),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 12),
            ]
        )
    )
    return table


def _summary_cards(stats: AttendancePdfStats, styles: dict) -> Table:
    cards = [
        ("员工总数", str(stats.total_employees), BRAND_BLUE),
        ("旷工合计", str(stats.total_absenteeism_days), BRAND_DANGER),
        ("迟到合计", str(stats.total_lateness_days), BRAND_WARNING),
        ("缺卡合计", str(stats.total_missing_punch_days), BRAND_WARNING),
    ]
    row_labels = [Paragraph(label, styles["muted"]) for label, _, _ in cards]
    row_values = [
        Paragraph(f"<b>{value}</b>", styles["body"]) for _, value, _ in cards
    ]
    table = Table([row_labels, row_values], colWidths=[62 * mm, 62 * mm, 62 * mm, 62 * mm])
    style_commands = [
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.5, BRAND_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BRAND_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, -1), BRAND_LIGHT),
    ]
    for index, (_, _, accent) in enumerate(cards):
        style_commands.append(("TEXTCOLOR", (index, 1), (index, 1), accent))
    table.setStyle(TableStyle(style_commands))
    return table


def _employee_table(rows: Sequence[AttendancePdfRow], styles: dict) -> Table:
    header = ["姓名", "部门", "出勤", "旷工", "迟到", "缺卡", "备注"]
    data: List[List] = [[Paragraph(cell, styles["muted"]) for cell in header]]
    for row in rows:
        data.append(
            [
                Paragraph(row.name, styles["body"]),
                Paragraph(row.department, styles["body"]),
                Paragraph(str(row.total_attendance_days), styles["body"]),
                Paragraph(str(row.absenteeism_count), styles["body"]),
                Paragraph(str(row.lateness_count), styles["body"]),
                Paragraph(str(row.missing_punch_count), styles["body"]),
                Paragraph(row.notes or "—", styles["body"]),
            ]
        )

    col_widths = [28 * mm, 32 * mm, 16 * mm, 16 * mm, 16 * mm, 16 * mm, 40 * mm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BRAND_NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("ALIGN", (2, 1), (5, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.25, BRAND_BORDER),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafafa")]),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _anomaly_section(rows: Sequence[AttendancePdfRow], styles: dict) -> List:
    anomalies = [
        row
        for row in rows
        if row.anomaly_summary or row.status == "warning"
    ]
    flow: List = [Paragraph("异常情况汇总", styles["section"])]
    if not anomalies:
        flow.append(Paragraph("本月无异常记录。", styles["body"]))
        return flow

    anomaly_data = [["姓名", "部门", "异常说明"]]
    for row in anomalies:
        summary = row.anomaly_summary or "考勤状态异常"
        anomaly_data.append([row.name, row.department, summary])

    table = Table(anomaly_data, colWidths=[35 * mm, 40 * mm, 115 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BRAND_BLUE),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, BRAND_BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    flow.append(table)
    return flow


def _footer(generated_at: datetime, styles: dict) -> Table:
    date_text = generated_at.strftime("%Y-%m-%d %H:%M UTC")
    left = Paragraph(f"生成时间：{date_text}", styles["muted"])
    right = Paragraph("HR 签字：________________________", styles["muted"])
    table = Table([[left, right]], colWidths=[130 * mm, 130 * mm])
    table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LINEABOVE", (0, 0), (-1, -1), 0.5, BRAND_BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return table


def _employee_status(record: MonthlyAttendance) -> str:
    if record.absenteeism_count or record.lateness_count or record.missing_punch_count:
        return "warning"
    return "ok"


def _load_report_data(
    db: Session,
    company_id: int,
    year: int,
    month: int,
) -> tuple[Company, List[AttendancePdfRow], AttendancePdfStats]:
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise AttendancePdfError("Company not found")

    records = (
        db.query(MonthlyAttendance)
        .options(joinedload(MonthlyAttendance.employee))
        .filter(
            MonthlyAttendance.company_id == company_id,
            MonthlyAttendance.year == year,
            MonthlyAttendance.month == month,
        )
        .order_by(MonthlyAttendance.employee_id)
        .all()
    )
    if not records:
        raise AttendancePdfError(f"No attendance data for {year}-{month:02d}")

    rows = [
        AttendancePdfRow(
            name=record.employee.name,
            department=record.employee.department,
            total_attendance_days=int(record.total_attendance_days or 0),
            absenteeism_count=int(record.absenteeism_count or 0),
            lateness_count=int(record.lateness_count or 0),
            missing_punch_count=int(record.missing_punch_count or 0),
            anomaly_summary=record.anomaly_summary or "",
            notes=record.notes or "",
            status=_employee_status(record),
        )
        for record in records
    ]
    stats = AttendancePdfStats(
        total_employees=len(rows),
        total_absenteeism_days=sum(row.absenteeism_count for row in rows),
        total_lateness_days=sum(row.lateness_count for row in rows),
        total_missing_punch_days=sum(row.missing_punch_count for row in rows),
    )
    return company, rows, stats


def generate_attendance_pdf(
    db: Session,
    *,
    company_id: int,
    year: int,
    month: int,
    generated_by: Optional[str] = None,
) -> AttendancePdfResult:
    if month < 1 or month > 12:
        raise AttendancePdfError("Month must be between 1 and 12")

    company, rows, stats = _load_report_data(db, company_id, year, month)
    generated_at = datetime.utcnow()
    styles = _styles()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=14 * mm,
        title=f"Attendance Report {year}-{month:02d}",
        author=generated_by or "DingTalk Attendance",
    )

    story: List = []
    story.append(_header_table(company.name, year, month, styles))
    story.append(Spacer(1, 8 * mm))
    story.append(_summary_cards(stats, styles))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("员工考勤明细", styles["section"]))
    story.append(_employee_table(rows, styles))
    story.append(Spacer(1, 6 * mm))
    story.extend(_anomaly_section(rows, styles))
    story.append(Spacer(1, 10 * mm))
    story.append(_footer(generated_at, styles))

    doc.build(story)
    content = buffer.getvalue()
    buffer.close()

    filename = f"attendance_{year}_{month:02d}.pdf"
    logger.info(
        "PDF report generated: company_id=%s period=%s-%02d employees=%s bytes=%s",
        company_id,
        year,
        month,
        len(rows),
        len(content),
    )
    return AttendancePdfResult(content=content, filename=filename)
