import { useQuery } from "@tanstack/react-query";
import { fetchAttendanceSheets } from "../api";

export function attendanceSheetsKeys(year: number, month: number) {
  return ["attendance-sheets", year, month] as const;
}

export function useAttendanceSheetsQuery(year: number, month: number, enabled = true) {
  return useQuery({
    queryKey: attendanceSheetsKeys(year, month),
    queryFn: () => fetchAttendanceSheets(year, month),
    enabled,
  });
}
