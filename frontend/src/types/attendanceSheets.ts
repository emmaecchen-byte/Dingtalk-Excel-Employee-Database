import type { MonthlyStats } from "../api";

export interface EmployeeSheetRow {
  id: number;
  name: string;
  department: string;
  position?: string;
  employee_code?: string;
  days: string[];
  morning: string[];
  afternoon: string[];
  overtime_days: number[];
  sign_counts: Record<string, number>;
  absent_days: number;
  work_days: number;
  total_attendance_days: number;
  absenteeism_count: number;
  lateness_count: number;
  missing_punch_count: number;
  anomaly_summary?: string;
  supplement_submitted: boolean;
  notes?: string;
  first_anomaly_date?: string;
}

export interface AttendanceSheetsResponse {
  company_name: string;
  year: number;
  month: number;
  generated_at: string;
  last_sync?: string;
  work_days: number;
  stats: MonthlyStats;
  employees: EmployeeSheetRow[];
}
