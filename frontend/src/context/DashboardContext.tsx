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
import { message } from "antd";
import {
  AttendanceSummaryResponse,
  MonthlyAttendanceResponse,
  MonthlyStats,
  downloadExcel,
  fetchAttendance,
  fetchAttendanceSummary,
  getApiErrorMessage,
  syncAll,
  uploadExcel,
} from "../api";
import { useLanguage } from "../i18n/LanguageContext";

export type AnomalyFilter = "all" | "issues_only";

interface DashboardContextValue {
  year: number;
  month: number;
  setYear: (year: number) => void;
  setMonth: (month: number) => void;
  data: MonthlyAttendanceResponse | null;
  summary: AttendanceSummaryResponse | null;
  stats: MonthlyStats | null;
  attendanceLoading: boolean;
  summaryLoading: boolean;
  syncing: boolean;
  uploading: boolean;
  downloading: boolean;
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
  refreshAttendance: () => Promise<void>;
  refreshSummary: () => Promise<void>;
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
  const [year, setYear] = useState(2026);
  const [month, setMonth] = useState(5);
  const [data, setData] = useState<MonthlyAttendanceResponse | null>(null);
  const [summary, setSummary] = useState<AttendanceSummaryResponse | null>(null);
  const [attendanceLoading, setAttendanceLoading] = useState(true);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [search, setSearch] = useState("");
  const [department, setDepartment] = useState("all");
  const [anomalyFilter, setAnomalyFilter] = useState<AnomalyFilter>("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [syncRefreshToken, setSyncRefreshToken] = useState(0);
  const [conflictModalOpen, setConflictModalOpen] = useState(false);
  const uploadInputRef = useRef<HTMLInputElement | null>(null);

  const bumpSyncRefresh = useCallback(() => {
    setSyncRefreshToken((value) => value + 1);
  }, []);

  const refreshAttendance = useCallback(async () => {
    setAttendanceLoading(true);
    try {
      const response = await fetchAttendance(year, month);
      setData(response);
    } catch (error) {
      message.error(getApiErrorMessage(error, t("loadAttendanceFailed")));
      setData(null);
    } finally {
      setAttendanceLoading(false);
    }
  }, [year, month, t]);

  const refreshSummary = useCallback(async () => {
    setSummaryLoading(true);
    try {
      const response = await fetchAttendanceSummary(year, month);
      setSummary(response);
    } catch (error) {
      message.error(getApiErrorMessage(error, t("loadSummaryFailed")));
      setSummary(null);
    } finally {
      setSummaryLoading(false);
    }
  }, [year, month, t]);

  const refreshAll = useCallback(async () => {
    await Promise.all([refreshAttendance(), refreshSummary()]);
  }, [refreshAttendance, refreshSummary]);

  useEffect(() => {
    refreshAttendance();
    refreshSummary();
  }, [refreshAttendance, refreshSummary]);

  useEffect(() => {
    setPage(1);
  }, [search, department, anomalyFilter, year, month]);

  const departments = useMemo(() => {
    const values = new Set((data?.employees ?? []).map((employee) => employee.department));
    return Array.from(values).sort();
  }, [data]);

  const filteredEmployees = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (data?.employees ?? []).filter((employee) => {
      const matchesSearch = !query || employee.name.toLowerCase().includes(query);
      const matchesDepartment = department === "all" || employee.department === department;
      const matchesAnomaly = anomalyFilter === "all" || employee.status === "warning";
      return matchesSearch && matchesDepartment && matchesAnomaly;
    });
  }, [data, search, department, anomalyFilter]);

  const handleSync = useCallback(async () => {
    setSyncing(true);
    try {
      const result = await syncAll();
      message.success(result.message);
      await refreshAll();
      bumpSyncRefresh();
    } catch (error) {
      message.error(getApiErrorMessage(error, t("syncFailed")));
    } finally {
      setSyncing(false);
    }
  }, [refreshAll, bumpSyncRefresh, t]);

  const handleDownloadExcel = useCallback(async () => {
    setDownloading(true);
    try {
      await downloadExcel(year, month);
    } catch (error) {
      message.error(getApiErrorMessage(error, t("downloadExcelFailed")));
    } finally {
      setDownloading(false);
    }
  }, [year, month, t]);

  const handleUploadExcel = useCallback(
    async (file: File) => {
      setUploading(true);
      try {
        const result = await uploadExcel(year, month, file);
        message.success(
          t("uploadExcelSuccess", {
            changes: result.changes_detected,
            conflicts: result.conflicts_created,
          })
        );
        await refreshAll();
        bumpSyncRefresh();
        if (result.conflicts_created > 0) {
          setConflictModalOpen(true);
        }
      } catch (error) {
        message.error(getApiErrorMessage(error, t("uploadExcelFailed")));
      } finally {
        setUploading(false);
        if (uploadInputRef.current) {
          uploadInputRef.current.value = "";
        }
      }
    },
    [year, month, refreshAll, bumpSyncRefresh, t]
  );

  const handleDataChange = useCallback((nextData: MonthlyAttendanceResponse) => {
    setData(nextData);
    setSummary((current) =>
      current
        ? { ...current, stats: nextData.stats }
        : {
            year: nextData.year,
            month: nextData.month,
            stats: nextData.stats,
            last_sync: nextData.last_sync,
          }
    );
  }, []);

  const triggerUpload = useCallback(() => {
    uploadInputRef.current?.click();
  }, []);

  const stats = summary?.stats ?? data?.stats ?? null;

  const value = useMemo<DashboardContextValue>(
    () => ({
      year,
      month,
      setYear,
      setMonth,
      data,
      summary,
      stats,
      attendanceLoading,
      summaryLoading,
      syncing,
      uploading,
      downloading,
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
      refreshAttendance,
      refreshSummary,
      refreshAll,
      handleSync,
      handleDownloadExcel,
      handleUploadExcel,
      triggerUpload,
      handleDataChange,
      syncRefreshToken,
      bumpSyncRefresh,
      conflictModalOpen,
      setConflictModalOpen,
    }),
    [
      year,
      month,
      data,
      summary,
      stats,
      attendanceLoading,
      summaryLoading,
      syncing,
      uploading,
      downloading,
      search,
      department,
      anomalyFilter,
      page,
      pageSize,
      departments,
      filteredEmployees,
      refreshAttendance,
      refreshSummary,
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
