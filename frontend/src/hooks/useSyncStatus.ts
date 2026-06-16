import { useQuery } from "@tanstack/react-query";
import { fetchSyncStatus } from "../api";
import { dashboardKeys } from "./dashboardKeys";

const POLL_INTERVAL_MS = 30_000;

export function useSyncStatusQuery(enabled = true) {
  return useQuery({
    queryKey: dashboardKeys.syncStatus(),
    queryFn: fetchSyncStatus,
    enabled,
    refetchInterval: POLL_INTERVAL_MS,
    refetchIntervalInBackground: true,
  });
}
