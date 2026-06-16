import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  Input,
  Layout,
  Select,
  Space,
  Tag,
  Typography,
} from "antd";
import {
  CloudSyncOutlined,
  CopyOutlined,
  DownloadOutlined,
  ExclamationCircleOutlined,
  FilePdfOutlined,
  GlobalOutlined,
  HistoryOutlined,
  LogoutOutlined,
  UploadOutlined,
  UserAddOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { useAuth } from "../auth/AuthContext";
import CloneMonthModal from "../components/CloneMonthModal";
import ConflictResolutionModal from "../components/ConflictResolutionModal";
import EmployeeTable from "../components/EmployeeTable";
import PendingUpdatesWidget from "../components/PendingUpdatesWidget";
import SummaryCards from "../components/SummaryCards";
import VersionHistoryModal from "../components/VersionHistoryModal";
import { DashboardProvider, useDashboard } from "../context/DashboardContext";
import { useLanguage } from "../i18n/LanguageContext";

const { Header, Content } = Layout;
const { Title, Text } = Typography;

function buildYearOptions(currentYear: number, language: "zh" | "en", yearSuffix: string) {
  const start = currentYear - 2;
  const end = currentYear + 2;
  return Array.from({ length: end - start + 1 }, (_, index) => {
    const value = start + index;
    return {
      value,
      label: language === "zh" ? `${value}${yearSuffix}` : String(value),
    };
  });
}

const MONTH_NAMES: Record<"zh" | "en", string[]> = {
  zh: ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"],
  en: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
};

export default function Dashboard() {
  return (
    <DashboardProvider>
      <DashboardContent />
    </DashboardProvider>
  );
}

function DashboardContent() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { language, toggleLanguage, t } = useLanguage();
  const {
    year,
    month,
    setYear,
    setMonth,
    data,
    stats,
    isLoading,
    attendanceLoading,
    syncing,
    syncStatusMessage,
    uploading,
    downloading,
    exportingPdf,
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
    triggerUpload,
    handleDataChange,
    syncRefreshToken,
    bumpSyncRefresh,
    conflictModalOpen,
    setConflictModalOpen,
  } = useDashboard();

  const [versionModalOpen, setVersionModalOpen] = useState(false);
  const [cloneModalOpen, setCloneModalOpen] = useState(false);

  const isHrAdmin = user?.role === "hr_admin";
  const canSync = user?.role === "hr_admin" || user?.role === "hr_viewer";

  const monthOptions = useMemo(
    () =>
      MONTH_NAMES[language].map((label, index) => ({
        value: index + 1,
        label,
      })),
    [language]
  );

  const yearOptions = useMemo(
    () => buildYearOptions(new Date().getFullYear(), language, t("yearSuffix")),
    [language, t]
  );

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          background: "#001529",
          padding: "0 24px",
        }}
      >
        <Space>
          <Title level={4} style={{ color: "#fff", margin: 0 }}>
            {t("appTitle")}
          </Title>
          <Tag color="blue">{t("demoTag")}</Tag>
        </Space>
        <Space>
          {isHrAdmin && (
            <Link to="/register">
              <Button type="text" icon={<UserAddOutlined />} style={{ color: "#fff" }}>
                {t("registerUser")}
              </Button>
            </Link>
          )}
          <Button type="text" icon={<GlobalOutlined />} onClick={toggleLanguage} style={{ color: "#fff" }}>
            {t("switchToEnglish")}
          </Button>
          <UserOutlined style={{ color: "#fff" }} />
          <Text style={{ color: "#fff" }}>{user?.name}</Text>
          <Button type="text" icon={<LogoutOutlined />} onClick={handleLogout} style={{ color: "#fff" }}>
            {t("logout")}
          </Button>
        </Space>
      </Header>

      <Content style={{ padding: 24, maxWidth: 1200, margin: "0 auto", width: "100%" }}>
        {syncStatusMessage && (
          <Alert
            message={syncStatusMessage}
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
          />
        )}

        <Card style={{ marginBottom: 16 }}>
          <Space wrap>
            <Select value={year} onChange={setYear} options={yearOptions} />
            <Select value={month} onChange={setMonth} options={monthOptions} />
            {canSync && (
              <Button type="primary" icon={<CloudSyncOutlined />} loading={syncing} onClick={() => void handleSync()}>
                {t("syncDingTalk")}
              </Button>
            )}
            {canSync && (
              <Button
                icon={<DownloadOutlined />}
                loading={downloading}
                onClick={() => void handleDownloadExcel()}
                disabled={!data}
              >
                {t("downloadExcel")}
              </Button>
            )}
            {canSync && (
              <Button icon={<UploadOutlined />} loading={uploading} onClick={triggerUpload} disabled={!data}>
                {t("uploadExcel")}
              </Button>
            )}
            {canSync && (
              <Button
                icon={<FilePdfOutlined />}
                loading={exportingPdf}
                onClick={() => void handleExportPdf(false)}
                onContextMenu={(event) => {
                  event.preventDefault();
                  void handleExportPdf(true);
                }}
                disabled={!data}
                title={t("exportPdfHint")}
              >
                {t("exportPdf")}
              </Button>
            )}
            {isHrAdmin && (
              <Button icon={<CopyOutlined />} onClick={() => setCloneModalOpen(true)} disabled={!data}>
                {t("cloneMonth")}
              </Button>
            )}
            {canSync && (
              <Button icon={<HistoryOutlined />} onClick={() => setVersionModalOpen(true)}>
                {t("versionHistory")}
              </Button>
            )}
            {canSync && (
              <Button icon={<ExclamationCircleOutlined />} onClick={() => setConflictModalOpen(true)}>
                {t("resolveConflicts")}
              </Button>
            )}
          </Space>
        </Card>

        {canSync && (
          <PendingUpdatesWidget
            refreshToken={syncRefreshToken}
            onOpenConflicts={() => setConflictModalOpen(true)}
          />
        )}

        <SummaryCards stats={stats} loading={attendanceLoading || isLoading} />

        <Card
          title={t("employeeList")}
          extra={
            <Space wrap>
              <Input.Search
                placeholder={t("searchNamePlaceholder")}
                allowClear
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                style={{ width: 200 }}
              />
              <Select
                value={department}
                onChange={setDepartment}
                style={{ width: 160 }}
                options={[
                  { value: "all", label: t("allDepartments") },
                  ...departments.map((value) => ({ value, label: value })),
                ]}
              />
              <Select
                value={anomalyFilter}
                onChange={setAnomalyFilter}
                style={{ width: 160 }}
                options={[
                  { value: "all", label: t("allAnomalies") },
                  { value: "issues_only", label: t("issuesOnly") },
                ]}
              />
            </Space>
          }
        >
          <EmployeeTable
            year={year}
            month={month}
            loading={attendanceLoading}
            data={data}
            employees={filteredEmployees}
            editable={canSync}
            page={page}
            pageSize={pageSize}
            onPageChange={(nextPage, nextPageSize) => {
              setPage(nextPage);
              setPageSize(nextPageSize);
            }}
            onDataChange={handleDataChange}
            onConflictDetected={bumpSyncRefresh}
          />
        </Card>
      </Content>

      <ConflictResolutionModal
        open={conflictModalOpen}
        year={year}
        month={month}
        onClose={() => setConflictModalOpen(false)}
        onResolved={() => {
          void refreshAll();
          bumpSyncRefresh();
        }}
      />

      <VersionHistoryModal
        open={versionModalOpen}
        year={year}
        month={month}
        onClose={() => setVersionModalOpen(false)}
        onRestored={refreshAll}
      />

      <CloneMonthModal
        open={cloneModalOpen}
        sourceYear={year}
        sourceMonth={month}
        onClose={() => setCloneModalOpen(false)}
        onCloned={(targetYear, targetMonth) => {
          setYear(targetYear);
          setMonth(targetMonth);
          void refreshAll();
        }}
      />
    </Layout>
  );
}
