import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { message, Progress } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  MonthlyAttendanceResponse,
  MonthlyStats,
  downloadExcel,
  downloadPdf,
  fetchAttendance,
  getApiErrorMessage,
  syncAll,
  uploadExcel,
} from "../api";
import { calculateStatsFromEmployees } from "../lib/attendanceStats";
import { useLanguage } from "../i18n/LanguageContext";
import { dashboardKeys } from "../hooks/dashboardKeys";
import { useSyncStatusQuery } from "../hooks/useSyncStatus";

export type AnomalyFilter = "all" | "issues_only";

const now = new Date();

interface DashboardContextValue {
  selectedYear: number;
  selectedMonth: number;
  setSelectedYear: (year: number) => void;
  setSelectedMonth: (month: number) => void;
  year: number;
  month: number;
  setYear: (year: number) => void;
  setMonth: (month: number) => void;
  employeeData: MonthlyAttendanceResponse["employees"];
  data: MonthlyAttendanceResponse | null;
  stats: MonthlyStats | null;
  isLoading: boolean;
  attendanceLoading: boolean;
  syncing: boolean;
  uploading: boolean;
  uploadProgress: number;
  downloading: boolean;
  exportingPdf: boolean;
  handleExportPdf: (openInNewTab?: boolean) => Promise<void>;
  search: string;
  setSearch: (value: string) => void;
  department: string;
  setDepartment: (value: string) => void;
  anomalyFilter: AnomalyFilter;
  setAnomalyFilter: (value: AnomalyFilter) => void;
  page: number;
  pageSize: number;
  setPage: (page: number) => void;
  setPageSize: (size: number) => void;
  departments: string[];
  filteredEmployees: MonthlyAttendanceResponse["employees"];
  refreshAll: () => Promise<void>;
  handleSync: () => Promise<void>;
  handleDownloadExcel: () => Promise<void>;
  handleUploadExcel: (file: File) => Promise<void>;
  triggerUpload: () => void;
  handleDataChange: (nextData: MonthlyAttendanceResponse) => void;
  syncRefreshToken: number;
  bumpSyncRefresh: () => void;
  conflictModalOpen: boolean;
  setConflictModalOpen: (open: boolean) => void;
}

const DashboardContext = createContext<DashboardContextValue | null>(null);

export function DashboardProvider({ children }: { children: ReactNode }) {
  const { t } = useLanguage();
  const queryClient = useQueryClient();
  const uploadInputRef = useRef<HTMLInputElement | null>(null);

  const [selectedYear, setSelectedYear] = useState(now.getFullYear());
  const [selectedMonth, setSelectedMonth] = useState(now.getMonth() + 1);
  const [search, setSearch] = useState("");
  const [department, setDepartment] = useState("all");
  const [anomalyFilter, setAnomalyFilter] = useState<AnomalyFilter>("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [syncRefreshToken, setSyncRefreshToken] = useState(0);
  const [conflictModalOpen, setConflictModalOpen] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [localData, setLocalData] = useState<MonthlyAttendanceResponse | null>(null);

  const bumpSyncRefresh = useCallback(() => {
    setSyncRefreshToken((value) => value + 1);
  }, []);

  const attendanceQuery = useQuery({
    queryKey: dashboardKeys.attendance(selectedYear, selectedMonth),
    queryFn: () => fetchAttendance(selectedYear, selectedMonth),
    retry: 1,
  });

  const syncStatusQuery = useSyncStatusQuery(true);

  useEffect(() => {
    if (attendanceQuery.data) {
      setLocalData(attendanceQuery.data);
    }
  }, [attendanceQuery.data]);

  useEffect(() => {
    if (attendanceQuery.isError) {
      message.error(getApiErrorMessage(attendanceQuery.error, t("loadAttendanceFailed")));
      setLocalData(null);
    }
  }, [attendanceQuery.isError, attendanceQuery.error, t]);

  useEffect(() => {
    setPage(1);
  }, [search, department, anomalyFilter, selectedYear, selectedMonth]);

  const data = localData;
  const employeeData = data?.employees ?? [];

  const stats = useMemo(() => {
    if (!employeeData.length && !data) {
      return null;
    }
    return calculateStatsFromEmployees(employeeData, {
      pendingConflicts: syncStatusQuery.data?.pending_conflicts_count ?? data?.stats.pending_conflicts ?? 0,
      pendingUpdates: syncStatusQuery.data?.pending_updates_count ?? data?.stats.pending_updates ?? 0,
    });
  }, [employeeData, data, syncStatusQuery.data]);

  const departments = useMemo(() => {
    const values = new Set(employeeData.map((employee) => employee.department));
    return Array.from(values).sort();
  }, [employeeData]);

  const filteredEmployees = useMemo(() => {
    const query = search.trim().toLowerCase();
    return employeeData.filter((employee) => {
      const matchesSearch = !query || employee.name.toLowerCase().includes(query);
      const matchesDepartment = department === "all" || employee.department === department;
      const matchesAnomaly = anomalyFilter === "all" || employee.status === "warning";
      return matchesSearch && matchesDepartment && matchesAnomaly;
    });
  }, [employeeData, search, department, anomalyFilter]);

  const refreshAll = useCallback(async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: dashboardKeys.attendance(selectedYear, selectedMonth) }),
      queryClient.invalidateQueries({ queryKey: dashboardKeys.syncStatus() }),
    ]);
    bumpSyncRefresh();
  }, [queryClient, selectedYear, selectedMonth, bumpSyncRefresh]);

  const syncMutation = useMutation({
    mutationFn: syncAll,
    onSuccess: async (result) => {
      message.success(result.message ?? t("syncSuccess"));
      await refreshAll();
    },
    onError: (error) => {
      message.error(getApiErrorMessage(error, t("syncFailed")));
    },
  });

  const downloadMutation = useMutation({
    mutationFn: () => downloadExcel(selectedYear, selectedMonth),
    onError: (error) => {
      message.error(getApiErrorMessage(error, t("downloadExcelFailed")));
    },
  });

  const exportPdfMutation = useMutation({
    mutationFn: (openInNewTab: boolean) => downloadPdf(selectedYear, selectedMonth, { openInNewTab }),
    onSuccess: (_data, openInNewTab) => {
      message.success(openInNewTab ? t("exportPdfOpened") : t("exportPdfSuccess"));
    },
    onError: (error) => {
      message.error(getApiErrorMessage(error, t("exportPdfFailed")));
    },
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) =>
      uploadExcel(selectedYear, selectedMonth, file, (percent) => setUploadProgress(percent)),
    onSuccess: async (result) => {
      message.success(
        t("uploadExcelSuccess", {
          changes: result.changes_detected,
          conflicts: result.conflicts_created,
        })
      );
      await refreshAll();
      if (result.has_conflicts || result.conflicts_created > 0) {
        setConflictModalOpen(true);
      }
    },
    onError: (error) => {
      message.error(getApiErrorMessage(error, t("uploadExcelFailed")));
    },
    onSettled: () => {
      setUploadProgress(0);
      if (uploadInputRef.current) {
        uploadInputRef.current.value = "";
      }
    },
  });

  const handleSync = useCallback(async () => {
    await syncMutation.mutateAsync();
  }, [syncMutation]);

  const handleDownloadExcel = useCallback(async () => {
    await downloadMutation.mutateAsync();
  }, [downloadMutation]);

  const handleExportPdf = useCallback(
    async (openInNewTab = false) => {
      await exportPdfMutation.mutateAsync(openInNewTab);
    },
    [exportPdfMutation]
  );

  const handleUploadExcel = useCallback(
    async (file: File) => {
      await uploadMutation.mutateAsync(file);
    },
    [uploadMutation]
  );

  const handleDataChange = useCallback((nextData: MonthlyAttendanceResponse) => {
    setLocalData(nextData);
    queryClient.setQueryData(dashboardKeys.attendance(nextData.year, nextData.month), nextData);
  }, [queryClient]);

  const triggerUpload = useCallback(() => {
    uploadInputRef.current?.click();
  }, []);

  const isLoading =
    attendanceQuery.isLoading ||
    attendanceQuery.isFetching ||
    syncMutation.isPending ||
    downloadMutation.isPending ||
    exportPdfMutation.isPending ||
    uploadMutation.isPending;

  const value = useMemo<DashboardContextValue>(
    () => ({
      selectedYear,
      selectedMonth,
      setSelectedYear,
      setSelectedMonth,
      year: selectedYear,
      month: selectedMonth,
      setYear: setSelectedYear,
      setMonth: setSelectedMonth,
      employeeData,
      data,
      stats,
      isLoading,
      attendanceLoading: attendanceQuery.isLoading || attendanceQuery.isFetching,
      syncing: syncMutation.isPending,
      uploading: uploadMutation.isPending,
      uploadProgress,
      downloading: downloadMutation.isPending,
      exportingPdf: exportPdfMutation.isPending,
      search,
      setSearch,
      department,
      setDepartment,
      anomalyFilter,
      setAnomalyFilter,
      page,
      pageSize,
      setPage,
      setPageSize,
      departments,
      filteredEmployees,
      refreshAll,
      handleSync,
      handleDownloadExcel,
      handleExportPdf,
      handleUploadExcel,
      triggerUpload,
      handleDataChange,
      syncRefreshToken,
      bumpSyncRefresh,
      conflictModalOpen,
      setConflictModalOpen,
    }),
    [
      selectedYear,
      selectedMonth,
      employeeData,
      data,
      stats,
      isLoading,
      attendanceQuery.isLoading,
      attendanceQuery.isFetching,
      syncMutation.isPending,
      uploadMutation.isPending,
      uploadProgress,
      downloadMutation.isPending,
      exportPdfMutation.isPending,
      handleExportPdf,
      search,
      department,
      anomalyFilter,
      page,
      pageSize,
      departments,
      filteredEmployees,
      refreshAll,
      handleSync,
      handleDownloadExcel,
      handleUploadExcel,
      triggerUpload,
      handleDataChange,
      syncRefreshToken,
      bumpSyncRefresh,
      conflictModalOpen,
    ]
  );

  return (
    <DashboardContext.Provider value={value}>
      <input
        ref={uploadInputRef}
        type="file"
        accept=".xlsx,.xls"
        hidden
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) {
            void handleUploadExcel(file);
          }
        }}
      />
      {uploadMutation.isPending && uploadProgress > 0 && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            zIndex: 1000,
            padding: "0 24px",
            background: "rgba(255,255,255,0.95)",
          }}
        >
          <Progress percent={uploadProgress} status="active" showInfo />
        </div>
      )}
      {children}
    </DashboardContext.Provider>
  );
}

export function useDashboard() {
  const context = useContext(DashboardContext);
  if (!context) {
    throw new Error("useDashboard must be used within DashboardProvider");
  }
  return context;
}
