import client from "../auth/api";
import { parseBlobError, triggerBrowserDownload } from "./api";

function filenameFromContentDisposition(header?: string, fallback?: string): string {
  if (!header) {
    return fallback ?? "download.xlsx";
  }
  const match = /filename="?([^";\n]+)"?/i.exec(header);
  return match?.[1] ?? fallback ?? "download.xlsx";
}

/**
 * GET /api/attendance/period/{periodId}/export/excel — attendance + exception workbook.
 */
export async function exportPeriodExcel(periodId: number): Promise<string> {
  const response = await client.get(`/attendance/period/${periodId}/export/excel`, {
    responseType: "blob",
  });

  const contentType = String(response.headers["content-type"] ?? "");
  if (contentType.includes("application/json")) {
    const detail = await parseBlobError(response.data as Blob);
    throw new Error(detail ?? "导出 Excel 失败");
  }

  const filename = filenameFromContentDisposition(
    response.headers["content-disposition"],
    `attendance_period_${periodId}.xlsx`
  );
  const blob = new Blob([response.data], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  triggerBrowserDownload(blob, filename);
  return filename;
}

/**
 * GET /api/attendance/period/{periodId}/export/pdf — attendance + exception PDF report.
 */
export async function exportPeriodPdf(periodId: number): Promise<string> {
  const response = await client.get(`/attendance/period/${periodId}/export/pdf`, {
    responseType: "blob",
  });

  const contentType = String(response.headers["content-type"] ?? "");
  if (contentType.includes("application/json")) {
    const detail = await parseBlobError(response.data as Blob);
    throw new Error(detail ?? "导出 PDF 失败");
  }

  const filename = filenameFromContentDisposition(
    response.headers["content-disposition"],
    `attendance_period_${periodId}.pdf`
  );
  const blob = new Blob([response.data], { type: "application/pdf" });
  triggerBrowserDownload(blob, filename);
  return filename;
}
