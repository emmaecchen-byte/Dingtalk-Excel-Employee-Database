import { useCallback, useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Alert, Button, Card, Layout, Modal, Space, Tag, Typography, message } from "antd";
import {
  ArrowLeftOutlined,
  CheckOutlined,
  DownloadOutlined,
  FilePdfOutlined,
  FileSearchOutlined,
  InboxOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import PeriodAttendanceGrid from "../components/attendance-table/PeriodAttendanceGrid";
import {
  AttendancePeriodTableResponse,
  fetchAttendancePeriodTable,
} from "../services/attendanceTable";
import { getApiErrorMessage } from "../services/api";
import { exportPeriodExcel, exportPeriodPdf } from "../services/periodExport";
import {
  PERIOD_STATUS_LABELS,
  PeriodDisplayStatus,
  archiveAttendancePeriod,
  confirmAttendancePeriod,
} from "../services/attendancePeriods";
import { useAuth } from "../auth/AuthContext";

const { Header, Content } = Layout;
const { Title, Text } = Typography;

function normalizeDisplayStatus(status: string): PeriodDisplayStatus {
  if (status === "archived") return "archived";
  if (status === "confirmed" || status === "published") return "confirmed";
  return "draft";
}

export default function AttendancePeriodTablePage() {
  const { periodId } = useParams<{ periodId: string }>();
  const { user } = useAuth();
  const isAdmin = user?.role === "hr_admin";
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState<AttendancePeriodTableResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [exportingExcel, setExportingExcel] = useState(false);
  const [exportingPdf, setExportingPdf] = useState(false);
  const [workflowLoading, setWorkflowLoading] = useState(false);

  const page = Number(searchParams.get("page") ?? "1");
  const pageSize = Number(searchParams.get("page_size") ?? "50");

  const loadTable = useCallback(async () => {
    if (!periodId) return;
    setLoading(true);
    try {
      const response = await fetchAttendancePeriodTable(Number(periodId), page, pageSize);
      setData(response);
    } catch (error) {
      message.error(getApiErrorMessage(error, "加载考勤表格失败"));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [periodId, page, pageSize]);

  useEffect(() => {
    void loadTable();
  }, [loadTable]);

  const handlePageChange = (nextPage: number, nextPageSize: number) => {
    setSearchParams({ page: String(nextPage), page_size: String(nextPageSize) });
  };

  const handleExportExcel = async () => {
    if (!periodId) return;
    setExportingExcel(true);
    try {
      const filename = await exportPeriodExcel(Number(periodId));
      message.success(`已开始下载 ${filename}`);
    } catch (error) {
      message.error(getApiErrorMessage(error, "导出 Excel 失败"));
    } finally {
      setExportingExcel(false);
    }
  };

  const handleExportPdf = async () => {
    if (!periodId) return;
    setExportingPdf(true);
    try {
      const filename = await exportPeriodPdf(Number(periodId));
      message.success(`已开始下载 ${filename}`);
    } catch (error) {
      message.error(getApiErrorMessage(error, "导出 PDF 失败"));
    } finally {
      setExportingPdf(false);
    }
  };

  const handleConfirm = () => {
    if (!periodId) return;
    Modal.confirm({
      title: "确认月度考勤",
      content: "确认后仍可编辑，归档后将变为只读。",
      onOk: async () => {
        setWorkflowLoading(true);
        try {
          await confirmAttendancePeriod(Number(periodId));
          message.success("已确认");
          await loadTable();
        } catch (error) {
          message.error(getApiErrorMessage(error, "确认失败"));
        } finally {
          setWorkflowLoading(false);
        }
      },
    });
  };

  const handleArchive = () => {
    if (!periodId) return;
    Modal.confirm({
      title: "归档月度考勤",
      content: "归档后记录将变为只读，确定继续吗？",
      okType: "danger",
      onOk: async () => {
        setWorkflowLoading(true);
        try {
          await archiveAttendancePeriod(Number(periodId));
          message.success("已归档");
          await loadTable();
        } catch (error) {
          message.error(getApiErrorMessage(error, "归档失败"));
        } finally {
          setWorkflowLoading(false);
        }
      },
    });
  };

  const displayStatus = data ? normalizeDisplayStatus(data.status) : "draft";
  const isReadOnly = data?.is_read_only ?? false;

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
          <Link to="/attendance-list">
            <Button type="text" icon={<ArrowLeftOutlined />} style={{ color: "#fff" }}>
              返回列表
            </Button>
          </Link>
          <Title level={4} style={{ color: "#fff", margin: 0 }}>
            {isReadOnly ? "考勤查看" : "考勤编辑表"}
          </Title>
        </Space>
        <Space>
          {isAdmin && data && displayStatus === "draft" && (
            <Button
              type="text"
              icon={<CheckOutlined />}
              style={{ color: "#fff" }}
              loading={workflowLoading}
              onClick={handleConfirm}
            >
              确认
            </Button>
          )}
          {isAdmin && data && displayStatus === "confirmed" && (
            <Button
              type="text"
              icon={<InboxOutlined />}
              style={{ color: "#fff" }}
              loading={workflowLoading}
              onClick={handleArchive}
            >
              归档
            </Button>
          )}
          <Button
            type="text"
            icon={<DownloadOutlined />}
            style={{ color: "#fff" }}
            loading={exportingExcel}
            onClick={() => void handleExportExcel()}
          >
            导出 Excel
          </Button>
          <Button
            type="text"
            icon={<FilePdfOutlined />}
            style={{ color: "#fff" }}
            loading={exportingPdf}
            onClick={() => void handleExportPdf()}
          >
            导出 PDF
          </Button>
          <Link to={`/exceptions/${periodId}`}>
            <Button type="text" icon={<FileSearchOutlined />} style={{ color: "#fff" }}>
              异常处理
            </Button>
          </Link>
          <Button
            type="text"
            icon={<ReloadOutlined />}
            style={{ color: "#fff" }}
            onClick={() => void loadTable()}
          >
            刷新
          </Button>
        </Space>
      </Header>

      <Content style={{ padding: 20 }}>
        <Card style={{ marginBottom: 16 }}>
          {data ? (
            <Space wrap>
              <Text strong>
                {data.year}年{data.month}月
              </Text>
              <Text type="secondary">周期 ID: {data.period_id}</Text>
              <Tag color={isReadOnly ? "default" : displayStatus === "confirmed" ? "green" : "gold"}>
                {PERIOD_STATUS_LABELS[displayStatus]}
              </Tag>
              <Text type="secondary">本月 {data.days_in_month} 天</Text>
            </Space>
          ) : (
            <Text type="secondary">加载中…</Text>
          )}
        </Card>

        {isReadOnly ? (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 12 }}
            message="此记录已归档，仅供查看，不可编辑。"
          />
        ) : (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message="点击单元格可编辑上午/下午考勤状态；右侧合计会在保存后自动重算。"
          />
        )}

        {data && (
          <PeriodAttendanceGrid
            data={data}
            loading={loading}
            editable={data.is_editable && !isReadOnly}
            onPageChange={handlePageChange}
            onDataPatch={setData}
          />
        )}
      </Content>
    </Layout>
  );
}
