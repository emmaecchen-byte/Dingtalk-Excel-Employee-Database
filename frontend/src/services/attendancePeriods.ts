import client from "../auth/api";

export type PeriodDisplayStatus = "draft" | "confirmed" | "archived";

export interface AttendancePeriodSummary {
  id: number;
  year: number;
  month: number;
  data_source: string;
  employee_count: number;
  exception_count: number;
  status: string;
  display_status: PeriodDisplayStatus;
  is_editable: boolean;
  is_read_only: boolean;
  created_at: string;
  updated_at: string;
  confirmed_at?: string | null;
  archived_at?: string | null;
  source_filename?: string | null;
}

export interface AttendancePeriodListResponse {
  total: number;
  periods: AttendancePeriodSummary[];
}

export const PERIOD_STATUS_LABELS: Record<PeriodDisplayStatus, string> = {
  draft: "草稿",
  confirmed: "已确认",
  archived: "已归档",
};

export const DATA_SOURCE_LABELS: Record<string, string> = {
  upload: "文件上传",
  api: "API 同步",
};

export async function fetchAttendancePeriod(periodId: number): Promise<AttendancePeriodSummary> {
  const { data } = await client.get<AttendancePeriodSummary>(`/attendance/period/${periodId}`);
  return data;
}

export async function fetchAttendancePeriods(
  status?: PeriodDisplayStatus
): Promise<AttendancePeriodListResponse> {
  const { data } = await client.get<AttendancePeriodListResponse>("/attendance/periods", {
    params: status ? { status } : undefined,
  });
  return data;
}

export async function confirmAttendancePeriod(periodId: number): Promise<AttendancePeriodSummary> {
  const { data } = await client.post<{ period: AttendancePeriodSummary }>(
    `/attendance/period/${periodId}/confirm`
  );
  return data.period;
}

export async function archiveAttendancePeriod(periodId: number): Promise<AttendancePeriodSummary> {
  const { data } = await client.post<{ period: AttendancePeriodSummary }>(
    `/attendance/period/${periodId}/archive`
  );
  return data.period;
}

export async function deleteAttendancePeriodDraft(periodId: number): Promise<void> {
  await client.delete(`/attendance/period/${periodId}`);
}
