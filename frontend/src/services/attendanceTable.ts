import client from "../auth/api";

export interface AttendanceRowTotals {
  present: number;
  personal_leave: number;
  compensatory_leave: number;
  business_trip: number;
  sick_leave: number;
  welfare_leave: number;
  annual_leave: number;
  maternity_leave: number;
  funeral_leave: number;
  marriage_leave: number;
  absenteeism: number;
  lateness: number;
  missing_punch: number;
  work_days: number;
  absent_days: number;
}

export interface AttendanceDayCell {
  daily_id: number | null;
  day: number | null;
  raw_text: string;
  status: string;
  symbol: string;
  requires_review: boolean;
}

export interface AttendanceShiftRow {
  shift: "morning" | "afternoon";
  shift_label: string;
  days: AttendanceDayCell[];
  totals: AttendanceRowTotals;
}

export interface AttendanceTableEmployee {
  employee_attendance_id: number;
  employee_id: number | null;
  employee_name: string;
  department: string;
  requires_review: boolean;
  rows: AttendanceShiftRow[];
  totals: AttendanceRowTotals;
}

export interface AttendanceStatusOption {
  value: string;
  symbol: string;
}

export interface AttendancePeriodTableResponse {
  period_id: number;
  year: number;
  month: number;
  days_in_month: number;
  status: string;
  is_editable: boolean;
  is_read_only: boolean;
  total_employees: number;
  page: number;
  page_size: number;
  status_options: AttendanceStatusOption[];
  employees: AttendanceTableEmployee[];
}

export interface DailyAttendancePatchResponse {
  daily_id: number;
  day: number;
  shift: string;
  status: string;
  symbol: string;
  morning_status: string;
  afternoon_status: string;
  morning_symbol: string;
  afternoon_symbol: string;
  raw_text: string;
  requires_review: boolean;
  employee_attendance_id: number;
  employee_requires_review: boolean;
  row_totals: AttendanceRowTotals;
  employee_totals: AttendanceRowTotals;
}

export async function fetchAttendancePeriodTable(
  periodId: number,
  page = 1,
  pageSize = 50
): Promise<AttendancePeriodTableResponse> {
  const { data } = await client.get<AttendancePeriodTableResponse>(
    `/attendance/period/${periodId}/table`,
    { params: { page, page_size: pageSize } }
  );
  return data;
}

export async function patchDailyAttendanceCell(
  dailyId: number,
  shift: "morning" | "afternoon",
  status: string
): Promise<DailyAttendancePatchResponse> {
  const { data } = await client.patch<DailyAttendancePatchResponse>(
    `/attendance/daily/${dailyId}`,
    { shift, status }
  );
  return data;
}

export interface FlatGridRow {
  key: string;
  employee_attendance_id: number;
  employee_name: string;
  department: string;
  shift: "morning" | "afternoon";
  shift_label: string;
  days: AttendanceDayCell[];
  totals: AttendanceRowTotals;
  employee_totals: AttendanceRowTotals;
  requires_review: boolean;
  show_name: boolean;
}

export function flattenEmployeesToGridRows(
  employees: AttendanceTableEmployee[]
): FlatGridRow[] {
  const rows: FlatGridRow[] = [];
  for (const employee of employees) {
    employee.rows.forEach((shiftRow, index) => {
      rows.push({
        key: `${employee.employee_attendance_id}-${shiftRow.shift}`,
        employee_attendance_id: employee.employee_attendance_id,
        employee_name: employee.employee_name,
        department: employee.department,
        shift: shiftRow.shift,
        shift_label: shiftRow.shift_label,
        days: shiftRow.days,
        totals: shiftRow.totals,
        employee_totals: employee.totals,
        requires_review: employee.requires_review,
        show_name: index === 0,
      });
    });
  }
  return rows;
}

export function applyDailyPatch(
  data: AttendancePeriodTableResponse,
  patch: DailyAttendancePatchResponse
): AttendancePeriodTableResponse {
  return {
    ...data,
    employees: data.employees.map((employee) => {
      if (employee.employee_attendance_id !== patch.employee_attendance_id) {
        return employee;
      }
      return {
        ...employee,
        requires_review: patch.employee_requires_review,
        totals: patch.employee_totals,
        rows: employee.rows.map((shiftRow) => ({
          ...shiftRow,
          totals: shiftRow.shift === patch.shift ? patch.row_totals : shiftRow.totals,
          days: shiftRow.days.map((dayCell) => {
            if (dayCell.daily_id !== patch.daily_id) {
              return dayCell;
            }
            const status =
              shiftRow.shift === "morning" ? patch.morning_status : patch.afternoon_status;
            const symbol =
              shiftRow.shift === "morning" ? patch.morning_symbol : patch.afternoon_symbol;
            return {
              ...dayCell,
              status,
              symbol,
              raw_text: patch.raw_text,
              requires_review: patch.requires_review,
            };
          }),
        })),
      };
    }),
  };
}

export function formatStatusOptionLabel(option: AttendanceStatusOption): string {
  if (option.value === "产假") {
    return option.symbol ? `产假/陪产假(${option.symbol})` : "产假/陪产假";
  }
  if (option.symbol) {
    return `${option.value}(${option.symbol})`;
  }
  return option.value;
}

export function isWeekendDay(year: number, month: number, day: number): boolean {
  const weekday = new Date(year, month - 1, day).getDay();
  return weekday === 0 || weekday === 6;
}

export function dayHeaderLabel(year: number, month: number, day: number): string {
  const weekday = new Date(year, month - 1, day).getDay();
  if (weekday === 6) return "六";
  if (weekday === 0) return "日";
  return String(day);
}
