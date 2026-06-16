"""
Master attendance Excel template generator (openpyxl).

Sheets:
  1. 签字           — Daily sign-off grid with COUNTIF summary formulas (AJ–AR, AT)
  2. 情况说明       — Anomaly explanations (populated by backend, no formulas)
  3. 月度汇总       — Monthly summary with daily columns AJ–BN
  4. 加班结算加班工资 — Daily overtime D–AH and rate columns AJ–AP
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Tuple, Union

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

COMPANY_NAME = "创崎新能源技术（上海）有限公司"

TEMPLATE_SHEETS = ("签字", "情况说明", "月度汇总", "加班结算加班工资")

# 签字 sheet layout
SIGN_HEADER_ROW = 3
SIGN_DATE_ROW = 4
SIGN_LEGEND_ROW = 5
SIGN_DATA_START_ROW = 6

SIGN_DAY_START_COL = 4  # D
SIGN_DAY_END_COL = 34  # AH (31 days)
SIGN_DAY_COUNT = 31

SIGN_SUMMARY_START_COL = 36  # AJ
SIGN_SUMMARY_END_COL = 44  # AR
SIGN_ABSENT_COL = 46  # AT = 应出勤 - 出勤

# Legend symbols in AJ5–AS5 (symbol only in cell; label in comment / adjacent doc)
SIGN_LEGEND_SYMBOLS: Tuple[Tuple[str, str], ...] = (
    ("√", "出勤"),
    ("◇", "事假"),
    ("✬", "调休"),
    ("▼", "出差"),
    ("※", "病假"),
    ("●", "福利假"),
    ("AL", "年假"),
    ("○", "产假/陪产假"),
    ("FL", "丧假"),
    ("ML", "婚假"),
)

SIGN_COUNT_SYMBOLS: Tuple[str, ...] = tuple(symbol for symbol, _ in SIGN_LEGEND_SYMBOLS[:9])

# 月度汇总
MONTHLY_DATE_ROW = 1
MONTHLY_SECTION_ROW = 3
MONTHLY_HEADER_ROW = 4
MONTHLY_DATA_START_ROW = 5
MONTHLY_DAILY_START_COL = 36  # AJ
MONTHLY_DAILY_END_COL = 66  # BN
MONTHLY_META_ANOMALY_COL = 67  # BO — backend only, no formulas
MONTHLY_META_SUPPLEMENT_COL = 68  # BP
MONTHLY_META_NOTES_COL = 69  # BQ

# 情况说明
SITUATION_DATA_START_ROW = 2

# 加班结算
OVERTIME_TITLE_ROW = 1
OVERTIME_HEADER_ROW = 4
OVERTIME_DATA_START_ROW = 5
OVERTIME_DAY_START_COL = 4  # D
OVERTIME_DAY_COUNT = 31
OVERTIME_CALC_START_COL = 36  # AJ

# 1.5x / 2x / 3x overtime day column groups (within D–AH)
OVERTIME_15X_RANGES = ("J:M", "O:S", "V:Z", "AC:AG")
OVERTIME_2X_RANGES = ("G:I", "N:N", "T:U", "AA:AB", "AH:AI")
OVERTIME_3X_RANGES = ("E:F",)

THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)
HEADER_FILL = PatternFill("solid", fgColor="D9E1F2")
TITLE_FONT = Font(name="宋体", size=14, bold=True)
HEADER_FONT = Font(name="宋体", size=10, bold=True)
BODY_FONT = Font(name="宋体", size=10)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)

DEFAULT_BLANK_EMPLOYEE_SLOTS = 15
DEFAULT_WORK_DAYS = 21


@dataclass
class TemplateEmployee:
    name: str
    department: str = ""
    position: str = ""
    employee_code: str = ""
    attendance_group: str = "默认考勤组"
    overtime_settlement: str = "调休"


def _col_letter(col: int) -> str:
    return get_column_letter(col)


def _day_col_sign(day: int) -> str:
    return _col_letter(SIGN_DAY_START_COL + day - 1)


def _summary_col_sign(index: int) -> str:
    return _col_letter(SIGN_SUMMARY_START_COL + index)


def _monthly_daily_col(day: int) -> str:
    return _col_letter(MONTHLY_DAILY_START_COL + day - 1)


def _overtime_day_col(day: int) -> str:
    return _col_letter(OVERTIME_DAY_START_COL + day - 1)


def _apply_border_range(ws, min_row: int, max_row: int, min_col: int, max_col: int) -> None:
    for row in range(min_row, max_row + 1):
        for col in range(min_col, max_col + 1):
            ws.cell(row=row, column=col).border = THIN_BORDER


def _merge_title(ws, row: int, min_col: int, max_col: int, text: str) -> None:
    ws.merge_cells(start_row=row, start_column=min_col, end_row=row, end_column=max_col)
    cell = ws.cell(row=row, column=min_col, value=text)
    cell.font = TITLE_FONT
    cell.alignment = CENTER


def _sign_countif_formula(am_row: int, symbol: str) -> str:
    day_start = _day_col_sign(1)
    day_end = _day_col_sign(SIGN_DAY_COUNT)
    legend_col = _summary_col_sign(SIGN_COUNT_SYMBOLS.index(symbol))
    return f"=COUNTIF({day_start}{am_row}:{day_end}{am_row},${legend_col}$5)"


def _overtime_sum_formula(row: int, ranges: Tuple[str, ...]) -> str:
    parts = []
    for rng in ranges:
        if ":" not in rng:
            parts.append(f"{rng}{row}")
            continue
        start, end = rng.split(":", 1)
        if start == end:
            parts.append(f"{start}{row}")
        else:
            parts.append(f"{start}{row}:{end}{row}")
    return f"=SUM({','.join(parts)})"


def _blank_employees(count: int) -> Tuple[TemplateEmployee, ...]:
    return tuple(TemplateEmployee(name="") for _ in range(count))


def _resolve_employees(employees: Optional[Sequence[TemplateEmployee]]) -> Sequence[TemplateEmployee]:
    if not employees:
        return _blank_employees(DEFAULT_BLANK_EMPLOYEE_SLOTS)
    if len(employees) < DEFAULT_BLANK_EMPLOYEE_SLOTS:
        return tuple(employees) + _blank_employees(DEFAULT_BLANK_EMPLOYEE_SLOTS - len(employees))
    return employees


def _build_sign_sheet(ws, year: int, month: int, employees: Sequence[TemplateEmployee]) -> None:
    days_in_month = calendar.monthrange(year, month)[1]
    last_col = max(SIGN_ABSENT_COL, SIGN_SUMMARY_END_COL + 6)

    _merge_title(ws, 1, 1, last_col, f"{COMPANY_NAME}员工{year}年{month}月考勤表")
    ws.row_dimensions[1].height = 28

    for col, label in ((1, "签名"), (2, "姓名"), (3, "时间")):
        cell = ws.cell(row=SIGN_HEADER_ROW, column=col, value=label)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER

    for day in range(1, SIGN_DAY_COUNT + 1):
        col = SIGN_DAY_START_COL + day - 1
        value = day if day <= days_in_month else f"{day}*"
        cell = ws.cell(row=SIGN_DATE_ROW, column=col, value=value)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER
        if day > days_in_month:
            cell.font = Font(name="宋体", size=10, bold=True, color="999999")

    for idx, (symbol, label) in enumerate(SIGN_LEGEND_SYMBOLS):
        col = SIGN_SUMMARY_START_COL + idx
        cell = ws.cell(row=SIGN_LEGEND_ROW, column=col, value=symbol)
        cell.font = HEADER_FONT
        cell.alignment = CENTER
        cell.fill = HEADER_FILL
    absent_header = ws.cell(row=SIGN_DATE_ROW, column=SIGN_ABSENT_COL, value="缺勤")
    absent_header.font = HEADER_FONT
    absent_header.fill = HEADER_FILL
    absent_header.alignment = CENTER

    current_row = SIGN_DATA_START_ROW
    for employee in employees:
        am_row = current_row
        pm_row = current_row + 1

        ws.merge_cells(start_row=am_row, start_column=1, end_row=pm_row, end_column=1)
        ws.cell(row=am_row, column=1).alignment = CENTER

        ws.merge_cells(start_row=am_row, start_column=2, end_row=pm_row, end_column=2)
        name_cell = ws.cell(row=am_row, column=2, value=employee.name or None)
        name_cell.font = BODY_FONT
        name_cell.alignment = CENTER

        ws.cell(row=am_row, column=3, value="上午").alignment = CENTER
        ws.cell(row=pm_row, column=3, value="下午").alignment = CENTER

        for day in range(1, SIGN_DAY_COUNT + 1):
            col = SIGN_DAY_START_COL + day - 1
            if day > days_in_month:
                for row in (am_row, pm_row):
                    ws.cell(row=row, column=col, value="")
                    ws.cell(row=row, column=col).fill = PatternFill("solid", fgColor="F2F2F2")
            else:
                ws.cell(row=am_row, column=col, value="")
                ws.cell(row=pm_row, column=col, value="")

        for idx, symbol in enumerate(SIGN_COUNT_SYMBOLS):
            col = SIGN_SUMMARY_START_COL + idx
            ws.cell(row=am_row, column=col, value=_sign_countif_formula(am_row, symbol))
            ws.cell(row=am_row, column=col).alignment = CENTER

        aj_col = _summary_col_sign(0)
        ws.cell(row=am_row, column=SIGN_ABSENT_COL, value=f"={DEFAULT_WORK_DAYS}-{aj_col}{am_row}")
        ws.cell(row=am_row, column=SIGN_ABSENT_COL).alignment = CENTER

        current_row += 2

    last_data_row = max(current_row - 1, SIGN_LEGEND_ROW)
    _apply_border_range(ws, SIGN_HEADER_ROW, last_data_row, 1, SIGN_ABSENT_COL)
    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 8
    for col in range(SIGN_DAY_START_COL, SIGN_ABSENT_COL + 1):
        ws.column_dimensions[_col_letter(col)].width = 4


def _build_situation_sheet(ws) -> None:
    headers = ("姓名", "日期", "异常情况", "是否补单", "备注")
    for idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=idx, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER
        cell.border = THIN_BORDER
        ws.column_dimensions[_col_letter(idx)].width = 18 if idx == 3 else 14

    for row in range(SITUATION_DATA_START_ROW, SITUATION_DATA_START_ROW + 50):
        for col in range(1, len(headers) + 1):
            ws.cell(row=row, column=col, value="")
            ws.cell(row=row, column=col).border = THIN_BORDER


def _build_monthly_summary_sheet(
    ws,
    year: int,
    month: int,
    employees: Sequence[TemplateEmployee],
) -> None:
    days_in_month = calendar.monthrange(year, month)[1]
    last_col = MONTHLY_META_NOTES_COL

    _merge_title(ws, 2, 1, MONTHLY_DAILY_START_COL - 1, f"{COMPANY_NAME}{year}年{month}月考勤月度汇总")

    for day in range(1, SIGN_DAY_COUNT + 1):
        col = MONTHLY_DAILY_START_COL + day - 1
        value = day if day <= days_in_month else f"{day}*"
        cell = ws.cell(row=MONTHLY_DATE_ROW, column=col, value=value)
        cell.font = HEADER_FONT
        cell.alignment = CENTER
        cell.fill = HEADER_FILL
        if day > days_in_month:
            cell.font = Font(name="宋体", size=10, bold=True, color="999999")

    ws.merge_cells(start_row=MONTHLY_SECTION_ROW, start_column=1, end_row=MONTHLY_SECTION_ROW, end_column=5)
    section = ws.cell(row=MONTHLY_SECTION_ROW, column=1, value="员工信息")
    section.font = HEADER_FONT
    section.fill = HEADER_FILL
    section.alignment = CENTER

    ws.merge_cells(
        start_row=MONTHLY_SECTION_ROW,
        start_column=MONTHLY_DAILY_START_COL,
        end_row=MONTHLY_SECTION_ROW,
        end_column=MONTHLY_DAILY_END_COL,
    )
    daily_section = ws.cell(row=MONTHLY_SECTION_ROW, column=MONTHLY_DAILY_START_COL, value="每日考勤状态")
    daily_section.font = HEADER_FONT
    daily_section.fill = HEADER_FILL
    daily_section.alignment = CENTER

    base_headers = ("姓名", "考勤组", "部门", "工号", "职位")
    for idx, header in enumerate(base_headers, start=1):
        cell = ws.cell(row=MONTHLY_HEADER_ROW, column=idx, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER

    for day in range(1, SIGN_DAY_COUNT + 1):
        col = MONTHLY_DAILY_START_COL + day - 1
        cell = ws.cell(row=MONTHLY_HEADER_ROW, column=col, value=day if day <= days_in_month else f"{day}*")
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER

    meta_headers = ((MONTHLY_META_ANOMALY_COL, "异常汇总"), (MONTHLY_META_SUPPLEMENT_COL, "是否补单"), (MONTHLY_META_NOTES_COL, "备注"))
    for col, label in meta_headers:
        cell = ws.cell(row=MONTHLY_HEADER_ROW, column=col, value=label)
        cell.font = Font(name="宋体", size=9, bold=True, color="666666")
        cell.fill = HEADER_FILL
        cell.alignment = CENTER

    for offset, employee in enumerate(employees):
        row = MONTHLY_DATA_START_ROW + offset
        ws.cell(row=row, column=1, value=employee.name or None)
        ws.cell(row=row, column=2, value=employee.attendance_group)
        ws.cell(row=row, column=3, value=employee.department)
        ws.cell(row=row, column=4, value=employee.employee_code)
        ws.cell(row=row, column=5, value=employee.position)

        for day in range(1, SIGN_DAY_COUNT + 1):
            col = MONTHLY_DAILY_START_COL + day - 1
            if day > days_in_month:
                ws.cell(row=row, column=col, value="")
                ws.cell(row=row, column=col).fill = PatternFill("solid", fgColor="F2F2F2")
            else:
                ws.cell(row=row, column=col, value="")

        for col in (MONTHLY_META_ANOMALY_COL, MONTHLY_META_SUPPLEMENT_COL, MONTHLY_META_NOTES_COL):
            ws.cell(row=row, column=col, value="")

    last_row = MONTHLY_DATA_START_ROW + len(employees) - 1
    _apply_border_range(ws, MONTHLY_SECTION_ROW, last_row, 1, last_col)
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["C"].width = 14
    for col in range(MONTHLY_DAILY_START_COL, MONTHLY_DAILY_END_COL + 1):
        ws.column_dimensions[_col_letter(col)].width = 4


def _build_overtime_sheet(ws, year: int, month: int, employees: Sequence[TemplateEmployee]) -> None:
    day_end_col = OVERTIME_DAY_START_COL + OVERTIME_DAY_COUNT - 1
    calc_end_col = OVERTIME_CALC_START_COL + 6  # AJ–AP
    last_col = max(day_end_col, calc_end_col)

    _merge_title(ws, OVERTIME_TITLE_ROW, 1, last_col, f"{COMPANY_NAME}{year}年{month}月加班结算及加班工资")

    for col, label in ((1, "姓名"), (2, "部门"), (3, "加班兑换方式")):
        cell = ws.cell(row=OVERTIME_HEADER_ROW, column=col, value=label)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER

    days_in_month = calendar.monthrange(year, month)[1]
    for day in range(1, OVERTIME_DAY_COUNT + 1):
        col = OVERTIME_DAY_START_COL + day - 1
        value = day if day <= days_in_month else f"{day}*"
        cell = ws.cell(row=OVERTIME_HEADER_ROW, column=col, value=value)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER

    calc_headers = ("1.5倍工时", "2倍工时", "3倍工时", "1.5倍合计", "2倍合计", "3倍合计", "加班工资合计")
    for idx, header in enumerate(calc_headers):
        col = OVERTIME_CALC_START_COL + idx
        cell = ws.cell(row=OVERTIME_HEADER_ROW, column=col, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER

    for offset, employee in enumerate(employees):
        row = OVERTIME_DATA_START_ROW + offset
        ws.cell(row=row, column=1, value=employee.name or None)
        ws.cell(row=row, column=2, value=employee.department)
        ws.cell(row=row, column=3, value=employee.overtime_settlement)

        for day in range(1, OVERTIME_DAY_COUNT + 1):
            col = OVERTIME_DAY_START_COL + day - 1
            if day > days_in_month:
                ws.cell(row=row, column=col, value="")
                ws.cell(row=row, column=col).fill = PatternFill("solid", fgColor="F2F2F2")
            else:
                ws.cell(row=row, column=col, value=0)

        ws.cell(row=row, column=OVERTIME_CALC_START_COL, value=_overtime_sum_formula(row, OVERTIME_15X_RANGES))
        ws.cell(row=row, column=OVERTIME_CALC_START_COL + 1, value=_overtime_sum_formula(row, OVERTIME_2X_RANGES))
        ws.cell(row=row, column=OVERTIME_CALC_START_COL + 2, value=_overtime_sum_formula(row, OVERTIME_3X_RANGES))
        ws.cell(row=row, column=OVERTIME_CALC_START_COL + 3, value=f"=AJ{row}*1.5")
        ws.cell(row=row, column=OVERTIME_CALC_START_COL + 4, value=f"=AK{row}*2")
        ws.cell(row=row, column=OVERTIME_CALC_START_COL + 5, value=f"=AL{row}*3")
        ws.cell(row=row, column=OVERTIME_CALC_START_COL + 6, value=f"=SUM(AM{row}:AO{row})")

    last_row = OVERTIME_DATA_START_ROW + len(employees) - 1
    _apply_border_range(ws, OVERTIME_HEADER_ROW, last_row, 1, calc_end_col)
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 16
    for col in range(OVERTIME_DAY_START_COL, day_end_col + 1):
        ws.column_dimensions[_col_letter(col)].width = 4


def build_attendance_workbook(
    year: int,
    month: int,
    employees: Optional[Sequence[TemplateEmployee]] = None,
) -> Workbook:
    resolved = _resolve_employees(employees)
    workbook = Workbook()
    sign_ws = workbook.active
    sign_ws.title = TEMPLATE_SHEETS[0]

    situation_ws = workbook.create_sheet(TEMPLATE_SHEETS[1])
    monthly_ws = workbook.create_sheet(TEMPLATE_SHEETS[2])
    overtime_ws = workbook.create_sheet(TEMPLATE_SHEETS[3])

    _build_sign_sheet(sign_ws, year, month, resolved)
    _build_situation_sheet(situation_ws)
    _build_monthly_summary_sheet(monthly_ws, year, month, resolved)
    _build_overtime_sheet(overtime_ws, year, month, resolved)
    return workbook


def generate_attendance_template(
    output_path: Union[str, Path],
    year: int,
    month: int,
    employees: Optional[Sequence[TemplateEmployee]] = None,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = build_attendance_workbook(year, month, employees)
    workbook.save(path)
    return path
