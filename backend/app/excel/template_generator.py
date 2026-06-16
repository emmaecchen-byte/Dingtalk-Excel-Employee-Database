"""
Master attendance Excel template generator (openpyxl).

Sheets:
  1. 签字           — Daily sign-off grid with COUNTIF summary formulas
  2. 情况说明       — Anomaly explanations (populated by backend)
  3. 月度汇总       — Monthly summary with daily columns AJ–BN and helpers BO–BT
  4. 加班结算加班工资 — Overtime pay calculation structure
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

# (symbol, Chinese label)
ATTENDANCE_SYMBOLS: Tuple[Tuple[str, str], ...] = (
    ("√", "出勤"),
    ("◇", "事假"),
    ("○", "病假"),
    ("△", "年假"),
    ("☆", "调休"),
    ("×", "旷工"),
    ("迟", "迟到"),
    ("缺", "缺卡"),
)

SIGN_DAY_START_COL = 4  # D
SIGN_DAY_COUNT = 31
SIGN_DATA_START_ROW = 6
MONTHLY_DATA_START_ROW = 5
OVERTIME_DATA_START_ROW = 4
SITUATION_DATA_START_ROW = 2
SIGN_SUMMARY_HEADERS: Tuple[Tuple[str, str], ...] = (
    ("出勤天数", "√"),
    ("事假", "◇"),
    ("病假", "○"),
    ("年假", "△"),
    ("调休", "☆"),
    ("旷工", "×"),
    ("迟到", "迟"),
    ("缺卡", "缺"),
)

MONTHLY_DAILY_START_COL = 36  # AJ
MONTHLY_DAILY_END_COL = 66  # BN
MONTHLY_HELPER_START_COL = 67  # BO
MONTHLY_HELPER_HEADERS = ("异常汇总", "旷工次数", "迟到次数", "缺卡次数", "是否补单", "备注")

MONTHLY_SUMMARY_HEADERS: Tuple[str, ...] = (
    "应出勤天数",
    "实际出勤天数",
    "事假(天)",
    "病假(天)",
    "年假(天)",
    "调休(天)",
    "加班(小时)",
    "旷工(次)",
    "迟到(次)",
    "缺卡(次)",
    "出勤率",
    "异常情况",
    "是否补单",
    "备注",
    "签字表出勤",
    "签字表事假",
    "签字表病假",
    "签字表年假",
    "签字表调休",
    "签字表旷工",
    "签字表迟到",
    "签字表缺卡",
    "事假(小时)",
    "病假(小时)",
    "年假(小时)",
    "调休(小时)",
    "平日加班",
    "周末加班",
    "节假日加班",
    "加班合计",
)

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


@dataclass
class TemplateEmployee:
    name: str
    department: str = ""
    position: str = ""
    employee_code: str = ""
    attendance_group: str = "默认考勤组"


def _day_col_sign(day: int) -> str:
    return get_column_letter(SIGN_DAY_START_COL + day - 1)


def _summary_col_sign(index: int) -> str:
    return get_column_letter(SIGN_DAY_START_COL + SIGN_DAY_COUNT + index)


def _monthly_daily_col(day: int) -> str:
    return get_column_letter(MONTHLY_DAILY_START_COL + day - 1)


def _monthly_helper_col(index: int) -> str:
    return get_column_letter(MONTHLY_HELPER_START_COL + index)


def _apply_border_range(ws, min_row: int, max_row: int, min_col: int, max_col: int) -> None:
    for row in range(min_row, max_row + 1):
        for col in range(min_col, max_col + 1):
            ws.cell(row=row, column=col).border = THIN_BORDER


def _merge_title(ws, row: int, min_col: int, max_col: int, text: str) -> None:
    ws.merge_cells(
        start_row=row,
        start_column=min_col,
        end_row=row,
        end_column=max_col,
    )
    cell = ws.cell(row=row, column=min_col, value=text)
    cell.font = TITLE_FONT
    cell.alignment = CENTER


def _sign_countif_formula(am_row: int, pm_row: int, symbol: str, half_day: bool = False) -> str:
    day_start = _day_col_sign(1)
    day_end = _day_col_sign(SIGN_DAY_COUNT)
    expr = f'COUNTIF({day_start}{am_row}:{day_end}{pm_row},"{symbol}")'
    if half_day:
        return f"={expr}/2"
    return f"={expr}"


def _build_sign_sheet(
    ws,
    year: int,
    month: int,
    employees: Sequence[TemplateEmployee],
) -> None:
    days_in_month = calendar.monthrange(year, month)[1]
    last_summary_col = SIGN_DAY_START_COL + SIGN_DAY_COUNT + len(SIGN_SUMMARY_HEADERS) - 1

    _merge_title(
        ws,
        1,
        1,
        last_summary_col,
        f"{COMPANY_NAME}员工{year}年{month}月考勤表",
    )

    ws.row_dimensions[1].height = 28

    # Row 4 — column headers
    ws.cell(row=4, column=1, value="签名").font = HEADER_FONT
    ws.cell(row=4, column=2, value="姓名").font = HEADER_FONT
    ws.cell(row=4, column=3, value="时间").font = HEADER_FONT
    for day in range(1, SIGN_DAY_COUNT + 1):
        col = SIGN_DAY_START_COL + day - 1
        value = day if day <= days_in_month else f"{day}*"
        cell = ws.cell(row=4, column=col, value=value)
        cell.font = HEADER_FONT
        cell.alignment = CENTER
        if day > days_in_month:
            cell.font = Font(name="宋体", size=10, bold=True, color="999999")
    for idx, (label, _) in enumerate(SIGN_SUMMARY_HEADERS):
        col = SIGN_DAY_START_COL + SIGN_DAY_COUNT + idx
        cell = ws.cell(row=4, column=col, value=label)
        cell.font = HEADER_FONT
        cell.alignment = CENTER

    # Row 5 — symbol legend
    legend_parts = [f"{symbol}={label}" for symbol, label in ATTENDANCE_SYMBOLS]
    ws.merge_cells(start_row=5, start_column=SIGN_DAY_START_COL, end_row=5, end_column=last_summary_col)
    legend_cell = ws.cell(row=5, column=SIGN_DAY_START_COL, value="  ".join(legend_parts))
    legend_cell.font = Font(name="宋体", size=9)
    legend_cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    ws.row_dimensions[5].height = 22

    # Employee rows — two rows per employee (上午 / 下午)
    current_row = 6
    for employee in employees:
        am_row = current_row
        pm_row = current_row + 1

        ws.merge_cells(start_row=am_row, start_column=1, end_row=pm_row, end_column=1)
        ws.cell(row=am_row, column=1).alignment = CENTER

        ws.merge_cells(start_row=am_row, start_column=2, end_row=pm_row, end_column=2)
        name_cell = ws.cell(row=am_row, column=2, value=employee.name)
        name_cell.font = BODY_FONT
        name_cell.alignment = CENTER

        ws.cell(row=am_row, column=3, value="上午").alignment = CENTER
        ws.cell(row=pm_row, column=3, value="下午").alignment = CENTER

        for day in range(1, SIGN_DAY_COUNT + 1):
            col = SIGN_DAY_START_COL + day - 1
            if day > days_in_month:
                for r in (am_row, pm_row):
                    cell = ws.cell(row=r, column=col, value="")
                    cell.fill = PatternFill("solid", fgColor="F2F2F2")
            else:
                ws.cell(row=am_row, column=col, value="")
                ws.cell(row=pm_row, column=col, value="")

        for idx, (_, symbol) in enumerate(SIGN_SUMMARY_HEADERS):
            col = SIGN_DAY_START_COL + SIGN_DAY_COUNT + idx
            half_day = symbol == "√"
            formula = _sign_countif_formula(am_row, pm_row, symbol, half_day=half_day)
            summary_cell = ws.cell(row=am_row, column=col, value=formula)
            summary_cell.alignment = CENTER
            ws.merge_cells(start_row=am_row, start_column=col, end_row=pm_row, end_column=col)
            ws.cell(row=am_row, column=col).alignment = CENTER

        current_row += 2

    last_data_row = current_row - 1
    _apply_border_range(ws, 4, last_data_row, 1, last_summary_col)
    for col in range(1, last_summary_col + 1):
        ws.column_dimensions[get_column_letter(col)].width = 4 if col >= SIGN_DAY_START_COL else 10
    ws.column_dimensions["B"].width = 12


def _build_situation_sheet(ws) -> None:
    headers = ("姓名", "日期", "异常情况", "是否补单", "备注")
    for idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=idx, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER
        cell.border = THIN_BORDER
        ws.column_dimensions[get_column_letter(idx)].width = 18 if idx == 3 else 14

    for row in range(2, 52):
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
    daily_start = get_column_letter(MONTHLY_DAILY_START_COL)
    daily_end = get_column_letter(MONTHLY_DAILY_END_COL)
    helper_end = get_column_letter(MONTHLY_HELPER_START_COL + len(MONTHLY_HELPER_HEADERS) - 1)

    _merge_title(ws, 1, 1, MONTHLY_HELPER_START_COL + len(MONTHLY_HELPER_HEADERS) - 1, f"{COMPANY_NAME}")
    _merge_title(ws, 2, 1, MONTHLY_HELPER_START_COL + len(MONTHLY_HELPER_HEADERS) - 1, f"{year}年{month}月考勤月度汇总")

    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=5)
    ws.cell(row=3, column=1, value="员工信息").font = HEADER_FONT
    ws.cell(row=3, column=1).alignment = CENTER
    ws.cell(row=3, column=1).fill = HEADER_FILL

    summary_end_col = MONTHLY_DAILY_START_COL - 1
    ws.merge_cells(start_row=3, start_column=6, end_row=3, end_column=summary_end_col)
    ws.cell(row=3, column=6, value="月度统计").font = HEADER_FONT
    ws.cell(row=3, column=6).alignment = CENTER
    ws.cell(row=3, column=6).fill = HEADER_FILL

    ws.merge_cells(start_row=3, start_column=MONTHLY_DAILY_START_COL, end_row=3, end_column=MONTHLY_DAILY_END_COL)
    ws.cell(row=3, column=MONTHLY_DAILY_START_COL, value="每日考勤状态").font = HEADER_FONT
    ws.cell(row=3, column=MONTHLY_DAILY_START_COL).alignment = CENTER
    ws.cell(row=3, column=MONTHLY_DAILY_START_COL).fill = HEADER_FILL

    helper_end_col = MONTHLY_HELPER_START_COL + len(MONTHLY_HELPER_HEADERS) - 1
    ws.merge_cells(start_row=3, start_column=MONTHLY_HELPER_START_COL, end_row=3, end_column=helper_end_col)
    ws.cell(row=3, column=MONTHLY_HELPER_START_COL, value="辅助计算列").font = HEADER_FONT
    ws.cell(row=3, column=MONTHLY_HELPER_START_COL).alignment = CENTER
    ws.cell(row=3, column=MONTHLY_HELPER_START_COL).fill = HEADER_FILL

    # Row 4 — column headers
    base_headers = ("姓名", "考勤组", "部门", "工号", "职位")
    for idx, header in enumerate(base_headers, start=1):
        cell = ws.cell(row=4, column=idx, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER

    for idx, header in enumerate(MONTHLY_SUMMARY_HEADERS, start=6):
        cell = ws.cell(row=4, column=idx, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER

    for day in range(1, SIGN_DAY_COUNT + 1):
        col = MONTHLY_DAILY_START_COL + day - 1
        value = day if day <= days_in_month else f"{day}*"
        cell = ws.cell(row=4, column=col, value=value)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER

    for idx, header in enumerate(MONTHLY_HELPER_HEADERS):
        col = MONTHLY_HELPER_START_COL + idx
        cell = ws.cell(row=4, column=col, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER

    data_start_row = 5
    for offset, employee in enumerate(employees):
        row = data_start_row + offset
        sign_am_row = 6 + offset * 2
        sign_pm_row = sign_am_row + 1

        ws.cell(row=row, column=1, value=employee.name)
        ws.cell(row=row, column=2, value=employee.attendance_group)
        ws.cell(row=row, column=3, value=employee.department)
        ws.cell(row=row, column=4, value=employee.employee_code)
        ws.cell(row=row, column=5, value=employee.position)

        # F: 应出勤天数 (weekdays in month, simplified as days_in_month for template)
        ws.cell(row=row, column=6, value=days_in_month)
        # G: 实际出勤天数 — COUNT √ in daily columns (each = 1 day if both halves present)
        ws.cell(
            row=row,
            column=7,
            value=f'=COUNTIF({daily_start}{row}:{daily_end}{row},"√")',
        )
        # H–K: leave days from daily symbols
        leave_map = (
            (8, "◇"),
            (9, "○"),
            (10, "△"),
            (11, "☆"),
        )
        for col, symbol in leave_map:
            ws.cell(
                row=row,
                column=col,
                value=f'=COUNTIF({daily_start}{row}:{daily_end}{row},"{symbol}")/2',
            )
        # L: overtime hours — link to overtime sheet column H
        overtime_row = row
        ws.cell(row=row, column=12, value=f"='加班结算加班工资'!H{overtime_row}")
        # M–O: anomaly counts
        ws.cell(row=row, column=13, value=f'=COUNTIF({daily_start}{row}:{daily_end}{row},"×")')
        ws.cell(row=row, column=14, value=f'=COUNTIF({daily_start}{row}:{daily_end}{row},"迟")')
        ws.cell(row=row, column=15, value=f'=COUNTIF({daily_start}{row}:{daily_end}{row},"缺")')
        # P: attendance rate
        ws.cell(row=row, column=16, value=f"=IF(F{row}=0,0,G{row}/F{row})")
        ws.cell(row=row, column=16).number_format = "0.0%"
        # Q–R: pulled from 情况说明 (placeholder INDEX; backend fills or HR edits)
        ws.cell(row=row, column=17, value="")
        ws.cell(row=row, column=18, value="")
        ws.cell(row=row, column=19, value="")

        # T–Z: cross-reference 签字 sheet summary columns
        sign_refs = (
            (20, _summary_col_sign(0)),
            (21, _summary_col_sign(1)),
            (22, _summary_col_sign(2)),
            (23, _summary_col_sign(3)),
            (24, _summary_col_sign(4)),
            (25, _summary_col_sign(5)),
            (26, _summary_col_sign(6)),
            (27, _summary_col_sign(7)),
        )
        for col, sign_col in sign_refs:
            ws.cell(row=row, column=col, value=f"=签字!{sign_col}{sign_am_row}")

        # AA–AD: leave hours (days * 8)
        for col, src_col in ((28, "H"), (29, "I"), (30, "J"), (31, "K")):
            ws.cell(row=row, column=col, value=f"={src_col}{row}*8")

        # AE–AH: overtime breakdown from sheet 4
        ws.cell(row=row, column=32, value=f"='加班结算加班工资'!E{overtime_row}")
        ws.cell(row=row, column=33, value=f"='加班结算加班工资'!F{overtime_row}")
        ws.cell(row=row, column=34, value=f"='加班结算加班工资'!G{overtime_row}")
        ws.cell(row=row, column=35, value=f"='加班结算加班工资'!H{overtime_row}")

        # Daily columns AJ–BN (blank for backend population)
        for day in range(1, SIGN_DAY_COUNT + 1):
            col = MONTHLY_DAILY_START_COL + day - 1
            if day > days_in_month:
                ws.cell(row=row, column=col, value="")
                ws.cell(row=row, column=col).fill = PatternFill("solid", fgColor="F2F2F2")
            else:
                ws.cell(row=row, column=col, value="")

        # Helper columns BO–BT
        ws.cell(
            row=row,
            column=MONTHLY_HELPER_START_COL,
            value=(
                f'=IF(M{row}+N{row}+O{row}>0,'
                f'"旷工"&M{row}&"次 迟到"&N{row}&"次 缺卡"&O{row}&"次","正常")'
            ),
        )
        ws.cell(row=row, column=MONTHLY_HELPER_START_COL + 1, value=f"=M{row}")
        ws.cell(row=row, column=MONTHLY_HELPER_START_COL + 2, value=f"=N{row}")
        ws.cell(row=row, column=MONTHLY_HELPER_START_COL + 3, value=f"=O{row}")
        ws.cell(row=row, column=MONTHLY_HELPER_START_COL + 4, value=f"=R{row}")
        ws.cell(row=row, column=MONTHLY_HELPER_START_COL + 5, value=f"=S{row}")

    last_row = data_start_row + len(employees) - 1
    _apply_border_range(ws, 3, last_row, 1, helper_end_col)
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["C"].width = 14
    for col in range(MONTHLY_DAILY_START_COL, MONTHLY_DAILY_END_COL + 1):
        ws.column_dimensions[get_column_letter(col)].width = 4


def _build_overtime_sheet(
    ws,
    year: int,
    month: int,
    employees: Sequence[TemplateEmployee],
) -> None:
    _merge_title(ws, 1, 1, 11, f"{COMPANY_NAME}{year}年{month}月加班结算及加班工资")

    headers = (
        "姓名",
        "工号",
        "部门",
        "职位",
        "平日加班(小时)",
        "周末加班(小时)",
        "节假日加班(小时)",
        "加班总时长",
        "加班单价(元/小时)",
        "加班工资(元)",
        "备注",
    )
    for idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=idx, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER
        cell.border = THIN_BORDER
        ws.column_dimensions[get_column_letter(idx)].width = 16

    data_start = 4
    for offset, employee in enumerate(employees):
        row = data_start + offset
        ws.cell(row=row, column=1, value=employee.name)
        ws.cell(row=row, column=2, value=employee.employee_code)
        ws.cell(row=row, column=3, value=employee.department)
        ws.cell(row=row, column=4, value=employee.position)
        ws.cell(row=row, column=5, value=0)
        ws.cell(row=row, column=6, value=0)
        ws.cell(row=row, column=7, value=0)
        ws.cell(row=row, column=8, value=f"=E{row}+F{row}+G{row}")
        ws.cell(row=row, column=9, value=0)
        ws.cell(row=row, column=10, value=f"=H{row}*I{row}*1.5")
        ws.cell(row=row, column=11, value="")

    last_row = data_start + len(employees) - 1
    _apply_border_range(ws, 3, last_row, 1, len(headers))

    total_row = last_row + 2
    ws.cell(row=total_row, column=4, value="合计").font = HEADER_FONT
    for col, letter in ((5, "E"), (6, "F"), (7, "G"), (8, "H"), (10, "J")):
        ws.cell(row=total_row, column=col, value=f"=SUM({letter}{data_start}:{letter}{last_row})")
        ws.cell(row=total_row, column=col).font = HEADER_FONT


def build_attendance_workbook(
    year: int,
    month: int,
    employees: Sequence[TemplateEmployee],
) -> Workbook:
    """Build the attendance workbook in memory (master template structure)."""
    workbook = Workbook()
    sign_ws = workbook.active
    sign_ws.title = TEMPLATE_SHEETS[0]

    situation_ws = workbook.create_sheet(TEMPLATE_SHEETS[1])
    monthly_ws = workbook.create_sheet(TEMPLATE_SHEETS[2])
    overtime_ws = workbook.create_sheet(TEMPLATE_SHEETS[3])

    _build_sign_sheet(sign_ws, year, month, employees)
    _build_situation_sheet(situation_ws)
    _build_monthly_summary_sheet(monthly_ws, year, month, employees)
    _build_overtime_sheet(overtime_ws, year, month, employees)
    return workbook


def generate_attendance_template(
    output_path: Union[str, Path],
    year: int,
    month: int,
    employees: Optional[Sequence[TemplateEmployee]] = None,
) -> Path:
    """Build the master attendance workbook and save it to *output_path*."""
    if employees is None:
        employees = [
            TemplateEmployee("陈鹏", "朋创", "工程师", "E001"),
            TemplateEmployee("芮超杰", "电机部", "技术员", "E002"),
            TemplateEmployee("张成", "项目推进部", "项目经理", "E003"),
            TemplateEmployee("李明", "品质部", "质检员", "E004"),
            TemplateEmployee("王芳", "行政部", "人事专员", "E005"),
        ]

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    workbook = build_attendance_workbook(year, month, employees)
    workbook.save(path)
    return path
