import client from "../auth/api";

export type SupplementStatus = "pending" | "yes" | "no" | "not_required";

export type ExceptionType =
  | "absenteeism"
  | "missing_punch"
  | "late_arrival"
  | "early_departure"
  | "unrecognized"
  | "conflicting";

export interface AbnormalRecordDateEntry {
  day: number;
  date: string;
  morning: string;
  afternoon: string;
  raw_text: string;
  detail: string;
  shift?: string | null;
  daily_id?: number | null;
}

export interface AbnormalRecordEditLog {
  id: number;
  field_name: string;
  old_value?: string | null;
  new_value?: string | null;
  editor_name?: string | null;
  edited_at: string;
}

export interface AbnormalRecord {
  id: number;
  period_id: number;
  employee_attendance_id?: number | null;
  employee_id?: number | null;
  employee_name: string;
  exception_type: ExceptionType;
  summary: string;
  dates: AbnormalRecordDateEntry[];
  supplement_status: SupplementStatus;
  notes?: string | null;
  created_at: string;
  updated_at: string;
  edit_logs: AbnormalRecordEditLog[];
}

export interface AbnormalRecordListResponse {
  period_id: number;
  total: number;
  records: AbnormalRecord[];
}

export const EXCEPTION_TYPE_LABELS: Record<ExceptionType, string> = {
  absenteeism: "旷工",
  missing_punch: "缺卡",
  late_arrival: "迟到",
  early_departure: "早退",
  unrecognized: "未识别",
  conflicting: "冲突",
};

export const SUPPLEMENT_STATUS_LABELS: Record<SupplementStatus, string> = {
  pending: "待处理",
  yes: "是",
  no: "否",
  not_required: "不需要",
};

export async function detectPeriodExceptions(periodId: number) {
  const { data } = await client.post(`/attendance/period/${periodId}/detect-exceptions`);
  return data;
}

export async function fetchPeriodExceptions(
  periodId: number,
  filters?: {
    employee_name?: string;
    exception_type?: string;
    supplement_status?: string;
  }
): Promise<AbnormalRecordListResponse> {
  const { data } = await client.get<AbnormalRecordListResponse>(
    `/attendance/period/${periodId}/exceptions`,
    { params: filters }
  );
  return data;
}

export async function updateAbnormalRecord(
  recordId: number,
  payload: { supplement_status?: SupplementStatus; notes?: string }
): Promise<AbnormalRecord> {
  const { data } = await client.patch<AbnormalRecord>(`/attendance/exception/${recordId}`, payload);
  return data;
}

export async function deleteAbnormalRecord(recordId: number): Promise<void> {
  await client.delete(`/attendance/exception/${recordId}`);
}

export async function createAbnormalRecord(
  periodId: number,
  payload: {
    employee_name: string;
    exception_type: ExceptionType;
    summary: string;
    dates?: AbnormalRecordDateEntry[];
    supplement_status?: SupplementStatus;
    notes?: string;
  }
): Promise<AbnormalRecord> {
  const { data } = await client.post<AbnormalRecord>(
    `/attendance/period/${periodId}/exceptions`,
    payload
  );
  return data;
}
