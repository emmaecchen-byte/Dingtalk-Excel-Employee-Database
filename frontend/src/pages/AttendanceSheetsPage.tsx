import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Alert, Button, Layout, Select, Space, Spin, Typography } from "antd";
import { ArrowLeftOutlined } from "@ant-design/icons";
import AttendanceSheetsView from "../components/attendance-sheets/AttendanceSheetsView";
import { useAttendanceSheetsQuery } from "../hooks/useAttendanceSheets";
import { useLanguage } from "../i18n/LanguageContext";
import { getApiErrorMessage } from "../api";

const { Header, Content } = Layout;
const { Title } = Typography;

const MONTH_NAMES: Record<"zh" | "en", string[]> = {
  zh: ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"],
  en: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
};

function parsePeriod(searchParams: URLSearchParams) {
  const now = new Date();
  const year = Number(searchParams.get("year") ?? now.getFullYear());
  const month = Number(searchParams.get("month") ?? now.getMonth() + 1);
  return {
    year: Number.isFinite(year) ? year : now.getFullYear(),
    month: Number.isFinite(month) ? Math.min(12, Math.max(1, month)) : now.getMonth() + 1,
  };
}

export default function AttendanceSheetsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { language, t } = useLanguage();
  const { year, month } = useMemo(() => parsePeriod(searchParams), [searchParams]);

  const { data, isLoading, error, refetch, isFetching } = useAttendanceSheetsQuery(year, month);

  const yearOptions = useMemo(() => {
    const currentYear = new Date().getFullYear();
    return Array.from({ length: 5 }, (_, index) => {
      const value = currentYear - 2 + index;
      return {
        value,
        label: language === "zh" ? `${value}${t("yearSuffix")}` : String(value),
      };
    });
  }, [language, t]);

  const monthOptions = useMemo(
    () =>
      MONTH_NAMES[language].map((label, index) => ({
        value: index + 1,
        label,
      })),
    [language]
  );

  const updatePeriod = (nextYear: number, nextMonth: number) => {
    setSearchParams({ year: String(nextYear), month: String(nextMonth) });
  };

  return (
    <Layout style={{ minHeight: "100vh", background: "#f0f2f5" }}>
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
          <Link to="/">
            <Button type="text" icon={<ArrowLeftOutlined />} style={{ color: "#fff" }}>
              {t("backToDashboard")}
            </Button>
          </Link>
          <Title level={4} style={{ color: "#fff", margin: 0 }}>
            {t("attendanceSheetsTitle")}
          </Title>
        </Space>
        <Space>
          <Select value={year} options={yearOptions} onChange={(value) => updatePeriod(value, month)} />
          <Select value={month} options={monthOptions} onChange={(value) => updatePeriod(year, value)} />
          <Button onClick={() => void refetch()} loading={isFetching}>
            {t("refresh")}
          </Button>
        </Space>
      </Header>

      <Content style={{ padding: 20 }}>
        {isLoading ? (
          <div style={{ textAlign: "center", padding: 80 }}>
            <Spin size="large" />
          </div>
        ) : error ? (
          <Alert
            type="error"
            showIcon
            message={t("attendanceSheetsLoadFailed")}
            description={getApiErrorMessage(error, t("loadAttendanceFailed"))}
          />
        ) : data ? (
          <AttendanceSheetsView data={data} language={language} />
        ) : null}
      </Content>
    </Layout>
  );
}
