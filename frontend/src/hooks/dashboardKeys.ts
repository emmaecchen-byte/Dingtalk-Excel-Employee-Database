export const dashboardKeys = {
  all: ["dashboard"] as const,
  attendance: (year: number, month: number) =>
    [...dashboardKeys.all, "attendance", year, month] as const,
  syncStatus: () => [...dashboardKeys.all, "syncStatus"] as const,
};
