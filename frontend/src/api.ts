import client from "./auth/api";
import type { AttendanceSheetsResponse } from "./types/attendanceSheets";

export {
  downloadExcel,
  getApiErrorMessage,
  syncAll,
  uploadExcel,
  type ExcelFieldChange,
  type ExcelUploadConflictPreview,
  type ExcelUploadResponse,
  type SyncResultResponse,
} from "./services/api";

export interface EmployeeSummary {
  id: number;
  name: string;
  department: string;
  position?: string;
  total_attendance_days: number;
  absenteeism_count: number;
  lateness_count: number;
  missing_punch_count: number;
  anomaly_summary?: string;
  supplement_submitted: boolean;
  notes?: string;
  status: string;
  manual_override_fields?: string[];
}

export interface AttendancePatchResponse {
  success: boolean;
  conflict_detected: boolean;
  conflict_id?: number | null;
  field_name: string;
  old_value?: string;
  new_value?: string;
  manual_override_fields: string[];
}

export async function patchAttendance(
  year: number,
  month: number,
  employeeId: number,
  payload: { field_name: string; new_value: string }
) {
  const { data } = await client.patch<AttendancePatchResponse>(
    `/attendance/${year}/${month}/${employeeId}`,
    payload
  );
  return data;
}

export interface MonthlyStats {
  total_employees: number;
  total_absenteeism_days: number;
  total_lateness_days: number;
  total_missing_punch_days: number;
  pending_conflicts: number;
  pending_updates: number;
}

export interface MonthlyAttendanceResponse {
  year: number;
  month: number;
  stats: MonthlyStats;
  employees: EmployeeSummary[];
  last_sync?: string;
}

export interface AttendanceSummaryResponse {
  year: number;
  month: number;
  stats: MonthlyStats;
  last_sync?: string;
}

export async function fetchAttendanceSummary(year: number, month: number) {
  const { data } = await client.get<AttendanceSummaryResponse>(
    `/attendance/summary/${year}/${month}`
  );
  return data;
}

export interface PendingUpdateListItem {
  employee_name: string;
  field_name: string;
  new_value?: string;
}

export interface SyncStatusResponse {
  last_sync_timestamp?: string;
  pending_updates_count: number;
  pending_conflicts_count: number;
  pending_updates_list: PendingUpdateListItem[];
  employees_synced_at?: string;
  attendance_synced_at?: string;
  leaves_synced_at?: string;
  overtime_synced_at?: string;
  pending_updates: number;
  pending_conflicts: number;
  demo_mode: boolean;
}

export async function fetchSyncStatus() {
  const { data } = await client.get<SyncStatusResponse>("/sync/status");
  return data;
}

export async function fetchAttendance(year: number, month: number) {
  const { data } = await client.get<MonthlyAttendanceResponse>(`/attendance/${year}/${month}`);
  return data;
}

export async function fetchAttendanceSheets(year: number, month: number) {
  const { data } = await client.get<AttendanceSheetsResponse>(`/attendance/${year}/${month}/sheets`);
  return data;
}

export async function downloadPdf(
  year: number,
  month: number,
  options: { openInNewTab?: boolean } = {}
) {
  const response = await client.get(`/attendance/export/pdf/${year}/${month}`, {
    responseType: "blob",
  });
  const blob = new Blob([response.data], { type: "application/pdf" });
  const url = window.URL.createObjectURL(blob);
  const filename = `attendance_${year}_${String(month).padStart(2, "0")}.pdf`;

  if (options.openInNewTab) {
    window.open(url, "_blank", "noopener,noreferrer");
  } else {
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
  }

  window.setTimeout(() => window.URL.revokeObjectURL(url), 60_000);
}

export interface MonthCloneCopyOptions {
  copy_employees: boolean;
  keep_attendance_data: boolean;
  keep_formulas: boolean;
  keep_manual_notes: boolean;
  reset_anomalies: boolean;
}

export interface MonthCloneRequest {
  source_year: number;
  source_month: number;
  target_year: number;
  target_month: number;
  copy_options: MonthCloneCopyOptions;
}

export interface MonthCloneResponse {
  success: boolean;
  target_month_id: number;
  employees_copied: number;
  snapshot_id?: number;
  version_number?: number;
  target_year: number;
  target_month: number;
}

export async function cloneMonth(payload: MonthCloneRequest) {
  const { data } = await client.post<MonthCloneResponse>("/excel/clone", payload);
  return data;
}

export interface ConflictItem {
  id: number;
  employee_id: number;
  employee_name: string;
  department: string;
  field_name: string;
  manual_value?: string;
  dingtalk_value?: string;
  manual_edit_at?: string;
  dingtalk_sync_at?: string;
  created_at?: string;
  status: string;
}

export interface ConflictListResponse {
  year: number;
  month: number;
  total: number;
  pending_conflicts_count: number;
  conflicts: ConflictItem[];
}

export type ConflictResolutionMethod = "manual" | "dingtalk_priority" | "manual_priority";

export interface ConflictSingleResolveResponse {
  success: boolean;
  conflict_id: number;
  status: string;
  resolution_method: string;
  resolved_value?: string;
  pending_conflicts_count: number;
}

export interface ConflictResolveResponse {
  success: boolean;
  resolved_count: number;
  pending_conflicts_count: number;
  conflict_ids: number[];
}

export async function fetchConflicts(year: number, month: number) {
  const { data } = await client.get<ConflictListResponse>(`/conflicts/${year}/${month}`);
  return data;
}

export async function resolveConflict(
  conflictId: number,
  payload: { resolution_method: ConflictResolutionMethod; resolved_value?: string }
) {
  const { data } = await client.post<ConflictSingleResolveResponse>(
    `/conflicts/${conflictId}/resolve`,
    payload
  );
  return data;
}

export async function batchResolveConflicts(payload: {
  conflict_ids: number[];
  resolution_method: ConflictResolutionMethod;
  resolved_value?: string;
}) {
  const { data } = await client.post<ConflictResolveResponse>("/conflicts/batch-resolve", payload);
  return data;
}

export async function autoResolveConflicts(payload?: { year?: number; month?: number }) {
  const { data } = await client.post<ConflictResolveResponse>("/conflicts/auto-resolve", payload ?? {});
  return data;
}

export interface VersionListItem {
  id: number;
  version_number: number;
  created_at?: string;
  created_by: string;
  summary: string;
  event_type?: string;
  snapshot_id?: number;
  can_restore: boolean;
  changes_summary: Record<string, unknown>;
}

export interface VersionListResponse {
  year: number;
  month: number;
  total: number;
  versions: VersionListItem[];
}

export interface VersionFieldDiff {
  employee_id: number;
  employee_name: string;
  field_name: string;
  value_in_snapshot_1: string;
  value_in_snapshot_2: string;
}

export interface VersionCompareResponse {
  snapshot_id_1: number;
  snapshot_id_2: number;
  version_id_1?: number;
  version_id_2?: number;
  year: number;
  month: number;
  has_differences: boolean;
  added_employees: { employee_id: number; employee_name: string }[];
  removed_employees: { employee_id: number; employee_name: string }[];
  changed_fields: VersionFieldDiff[];
  diff_text_old: string;
  diff_text_new: string;
}

export interface VersionRestoreResponse {
  success: boolean;
  restored_version_id: number;
  restored_from_version: number;
  employees_restored: number;
  snapshot_id: number;
}

export interface VersionDetailResponse {
  id: number;
  version_number: number;
  year: number;
  month: number;
  created_at?: string;
  created_by: string;
  changes_summary: Record<string, unknown>;
  version_note?: string;
  snapshot_id?: number;
  snapshot_version?: number;
  data_snapshot?: Record<string, unknown>;
}

export interface VersionRollbackDingtalkWarning {
  employee_id: number;
  employee_name: string;
  field_name: string;
  current_value: string;
  rollback_value: string;
  last_sync_from_dingtalk?: string;
}

export interface VersionRollbackPreviewResponse {
  version_id: number;
  version_number: number;
  requires_confirmation: boolean;
  requires_dingtalk_confirmation: boolean;
  fields_would_change: number;
  employees_affected: number;
  dingtalk_overwrite_warnings: VersionRollbackDingtalkWarning[];
  changes: {
    employee_id: number;
    employee_name: string;
    field_name: string;
    current_value: string;
    rollback_value: string;
  }[];
}

export interface VersionRollbackResponse {
  success: boolean;
  new_version: number;
  version_id: number;
  snapshot_id: number;
  rolled_back_to_version: number;
  rolled_back_to_version_id: number;
  fields_changed: number;
  employees_affected: number;
  manual_changes_created: number;
  conflicts_created: number;
  pending_conflicts_count: number;
  changes: {
    employee_id: number;
    employee_name: string;
    field_name: string;
    old_value: string;
    new_value: string;
  }[];
}

export async function fetchVersionHistory(year: number, month: number) {
  const { data } = await client.get<VersionListResponse>(`/versions/${year}/${month}`);
  return data;
}

export async function compareVersions(payload: {
  version_id_1?: number;
  version_id_2?: number;
  snapshot_id_1?: number;
  snapshot_id_2?: number;
}) {
  const { data } = await client.post<VersionCompareResponse>("/versions/compare", payload);
  return data;
}

export async function fetchVersionDetail(versionId: number) {
  const { data } = await client.get<VersionDetailResponse>(`/versions/${versionId}`);
  return data;
}

export async function previewVersionRollback(versionId: number) {
  const { data } = await client.get<VersionRollbackPreviewResponse>(
    `/versions/${versionId}/rollback-preview`
  );
  return data;
}

export async function rollbackVersion(
  versionId: number,
  options: { confirmDataLoss?: boolean; confirmDingtalkOverwrite?: boolean } = {}
) {
  const { confirmDataLoss = false, confirmDingtalkOverwrite = false } = options;
  const { data } = await client.post<VersionRollbackResponse>(`/versions/${versionId}/rollback`, {
    confirm_data_loss: confirmDataLoss,
    confirm_dingtalk_overwrite: confirmDingtalkOverwrite,
  });
  return data;
}

export async function restoreVersion(versionId: number) {
  const { data } = await client.post<VersionRestoreResponse>(`/versions/${versionId}/restore`);
  return data;
}

export async function restoreVersionBySnapshot(snapshotId: number) {
  const { data } = await client.post<VersionRestoreResponse>("/versions/restore", {
    snapshot_id: snapshotId,
  });
  return data;
}
