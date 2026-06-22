import axios, { type AxiosResponse } from "axios";
import client from "../auth/api";

export interface SyncResultResponse {
  success: boolean;
  message: string;
  records_updated: number;
  synced_at: string;
}

export interface ExcelUploadConflictPreview {
  id: number;
  employee_id: number;
  employee_name: string;
  field_name: string;
  dingtalk_value?: string;
  manual_value?: string;
  status: string;
}

export interface ExcelFieldChange {
  employee_id: number;
  employee_name: string;
  field_name: string;
  old_value?: string;
  new_value?: string;
  conflict: boolean;
  conflict_id?: number | null;
}

export interface ExcelUploadResponse {
  success: boolean;
  year: number;
  month: number;
  snapshot_id: number;
  total_changes: number;
  employees_affected: number;
  changes_detected: number;
  employees_modified: number;
  conflicts_created: number;
  auto_merged: number;
  has_conflicts: boolean;
  conflicts_list: ExcelUploadConflictPreview[];
  pending_conflicts_count: number;
  changes_list: ExcelFieldChange[];
  changes: ExcelFieldChange[];
}

export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (typeof detail === "object" && detail && "message" in detail) {
      return String(detail.message);
    }
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0];
      if (typeof first === "object" && first && "msg" in first) {
        return String(first.msg);
      }
    }
  }
  return fallback;
}

export async function parseBlobError(blob: Blob): Promise<string | null> {
  try {
    const text = await blob.text();
    const json = JSON.parse(text) as { detail?: string };
    return typeof json.detail === "string" ? json.detail : null;
  } catch {
    return null;
  }
}

async function assertBlobDownload(response: AxiosResponse<Blob>, fallbackError: string): Promise<void> {
  const contentType = String(response.headers["content-type"] ?? "");
  if (response.status >= 400 || contentType.includes("application/json")) {
    const detail = await parseBlobError(response.data as Blob);
    throw new Error(detail ?? fallbackError);
  }
}

export async function requestBlobDownload(
  request: () => Promise<AxiosResponse<Blob>>,
  fallbackError: string
): Promise<AxiosResponse<Blob>> {
  try {
    const response = await request();
    await assertBlobDownload(response, fallbackError);
    return response;
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.data instanceof Blob) {
      const detail = await parseBlobError(error.response.data);
      throw new Error(detail ?? fallbackError);
    }
    throw error;
  }
}

export function triggerBrowserDownload(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

function filenameFromContentDisposition(header?: string, fallback?: string): string {
  if (!header) {
    return fallback ?? "download";
  }
  const match = /filename="?([^";\n]+)"?/i.exec(header);
  return match?.[1] ?? fallback ?? "download";
}

/**
 * GET /api/excel/download/{year}/{month} — authenticated blob download.
 */
export async function downloadExcel(year: number, month: number): Promise<string> {
  const response = await requestBlobDownload(
    () => client.get(`/excel/download/${year}/${month}`, { responseType: "blob" }),
    "Failed to download Excel file"
  );

  const filename = filenameFromContentDisposition(
    response.headers["content-disposition"],
    `attendance_${year}_${String(month).padStart(2, "0")}.xlsx`
  );
  const blob = new Blob([response.data], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  triggerBrowserDownload(blob, filename);
  return filename;
}

/**
 * POST /api/excel/upload — multipart FormData with year, month, and .xlsx file.
 */
export async function uploadExcel(
  year: number,
  month: number,
  file: File,
  onProgress?: (percent: number) => void
): Promise<ExcelUploadResponse> {
  if (!file.name.toLowerCase().endsWith(".xlsx")) {
    throw new Error("Only .xlsx files are supported");
  }

  const formData = new FormData();
  formData.append("year", String(year));
  formData.append("month", String(month));
  formData.append("file", file);

  const { data } = await client.post<ExcelUploadResponse>("/excel/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: (event) => {
      if (!event.total) {
        return;
      }
      onProgress?.(Math.round((event.loaded * 100) / event.total));
    },
  });
  return data;
}

/**
 * POST /api/attendance/upload-and-convert — upload DingTalk 月度汇总 and download 4-sheet workbook.
 */
export async function uploadAndConvertAttendance(
  file: File,
  options?: { year?: number; month?: number; onProgress?: (percent: number) => void }
): Promise<string> {
  if (!file.name.toLowerCase().endsWith(".xlsx")) {
    throw new Error("Only .xlsx files are supported");
  }

  const formData = new FormData();
  formData.append("file", file);
  if (options?.year) {
    formData.append("year", String(options.year));
  }
  if (options?.month) {
    formData.append("month", String(options.month));
  }

  const response = await requestBlobDownload(
    () =>
      client.post("/attendance/upload-and-convert", formData, {
        headers: { "Content-Type": "multipart/form-data" },
        responseType: "blob",
        onUploadProgress: (event) => {
          if (!event.total) {
            return;
          }
          options?.onProgress?.(Math.round((event.loaded * 100) / event.total));
        },
      }),
    "Failed to convert uploaded attendance file"
  );

  const fallbackYear = options?.year ?? new Date().getFullYear();
  const fallbackMonth = options?.month ?? new Date().getMonth() + 1;
  const filename = filenameFromContentDisposition(
    response.headers["content-disposition"],
    `attendance_full_${fallbackYear}_${String(fallbackMonth).padStart(2, "0")}.xlsx`
  );
  const blob = new Blob([response.data], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  triggerBrowserDownload(blob, filename);
  return filename;
}

/**
 * POST /api/excel/upload-dingtalk-source — legacy alias for upload-and-convert.
 */
export async function uploadDingTalkSourceAndDownloadFullExcel(
  year: number,
  month: number,
  file: File,
  onProgress?: (percent: number) => void
): Promise<string> {
  return uploadAndConvertAttendance(file, { year, month, onProgress });
}

export interface ValidationIssue {
  severity: string;
  code: string;
  message: string;
  employee_name?: string | null;
  day?: number | null;
  row_index?: number | null;
}

export interface AttendanceUploadResponse {
  success: boolean;
  period_id: number;
  year: number;
  month: number;
  status: string;
  employee_count: number;
  daily_record_count: number;
  requires_review_count: number;
  persisted: boolean;
  has_blocking_errors: boolean;
  validation_issues: ValidationIssue[];
}

/**
 * POST /api/attendance/upload — parse DingTalk monthly summary and store structured data.
 */
export async function uploadAttendanceExcel(
  file: File,
  options?: { year?: number; month?: number; onProgress?: (percent: number) => void }
): Promise<AttendanceUploadResponse> {
  if (!file.name.toLowerCase().endsWith(".xlsx")) {
    throw new Error("Only .xlsx files are supported");
  }

  const formData = new FormData();
  formData.append("file", file);
  if (options?.year) {
    formData.append("year", String(options.year));
  }
  if (options?.month) {
    formData.append("month", String(options.month));
  }

  const { data } = await client.post<AttendanceUploadResponse>("/attendance/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: (event) => {
      if (!event.total) {
        return;
      }
      options?.onProgress?.(Math.round((event.loaded * 100) / event.total));
    },
  });
  return data;
}

/**
 * POST /api/sync/all — sync DingTalk data for the selected month.
 */
export async function syncAll(year: number, month: number): Promise<SyncResultResponse> {
  const { data } = await client.post<SyncResultResponse>("/sync/all", { year, month });
  return data;
}
