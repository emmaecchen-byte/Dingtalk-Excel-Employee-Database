import client from "../auth/api";
import { requestBlobDownload, triggerBrowserDownload } from "./api";

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
  const response = await requestBlobDownload(
    () => client.get(`/attendance/period/${periodId}/export/excel`, { responseType: "blob" }),
    "导出 Excel 失败"
  );

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
  const response = await requestBlobDownload(
    () => client.get(`/attendance/period/${periodId}/export/pdf`, { responseType: "blob" }),
    "导出 PDF 失败"
  );

  const filename = filenameFromContentDisposition(
    response.headers["content-disposition"],
    `attendance_period_${periodId}.pdf`
  );
  const blob = new Blob([response.data], { type: "application/pdf" });
  triggerBrowserDownload(blob, filename);
  return filename;
}
