import type { EmployeeSummary, MonthlyStats } from "../api";

export function calculateStatsFromEmployees(
  employees: EmployeeSummary[],
  options?: { pendingConflicts?: number; pendingUpdates?: number }
): MonthlyStats {
  return {
    total_employees: employees.length,
    total_absenteeism_days: employees.reduce((sum, employee) => sum + employee.absenteeism_count, 0),
    total_lateness_days: employees.reduce((sum, employee) => sum + employee.lateness_count, 0),
    total_missing_punch_days: employees.reduce(
      (sum, employee) => sum + employee.missing_punch_count,
      0
    ),
    pending_conflicts: options?.pendingConflicts ?? 0,
    pending_updates: options?.pendingUpdates ?? 0,
  };
}
