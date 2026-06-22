import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Button,
  Card,
  Dropdown,
  Layout,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { MenuProps } from "antd/es";
import type { ColumnsType } from "antd/es/table";
import {
  ArrowLeftOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  EyeOutlined,
  PlusOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import {
  AttendancePeriodSummary,
  DATA_SOURCE_LABELS,
  PERIOD_STATUS_LABELS,
  PeriodDisplayStatus,
  archiveAttendancePeriod,
  confirmAttendancePeriod,
  deleteAttendancePeriodDraft,
  fetchAttendancePeriods,
} from "../services/attendancePeriods";
import { exportPeriodExcel, exportPeriodPdf } from "../services/periodExport";
import { getApiErrorMessage } from "../services/api";
import { useAuth } from "../auth/AuthContext";
import { useLanguage } from "../i18n/LanguageContext";

const { Header, Content } = Layout;
const { Title, Text } = Typography;

function statusColor(status: PeriodDisplayStatus) {
  if (status === "archived") return "default";
  if (status === "confirmed") return "green";
  return "gold";
}

function formatDateTime(value?: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

export default function AttendanceListPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { t } = useLanguage();
  const isAdmin = user?.role === "hr_admin";
  const [periods, setPeriods] = useState<AttendancePeriodSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<PeriodDisplayStatus | undefined>();
  const [actionPeriodId, setActionPeriodId] = useState<number | null>(null);

  const loadPeriods = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetchAttendancePeriods(statusFilter);
      setPeriods(response.periods);
    } catch (error) {
      message.error(getApiErrorMessage(error, "加载考勤记录失败"));
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    void loadPeriods();
  }, [loadPeriods]);

  const handleConfirm = (record: AttendancePeriodSummary) => {
    Modal.confirm({
      title: "确认月度考勤",
      content: `确认 ${record.year}年${record.month}月 考勤数据无误？确认后仍可编辑，归档前请完成所有修改。`,
      onOk: async () => {
        setActionPeriodId(record.id);
        try {
          await confirmAttendancePeriod(record.id);
          message.success("已确认");
          await loadPeriods();
        } catch (error) {
          message.error(getApiErrorMessage(error, "确认失败"));
        } finally {
          setActionPeriodId(null);
        }
      },
    });
  };

  const handleArchive = (record: AttendancePeriodSummary) => {
    Modal.confirm({
      title: "归档月度考勤",
      content: `归档后 ${record.year}年${record.month}月 记录将变为只读，确定归档吗？`,
      okType: "danger",
      onOk: async () => {
        setActionPeriodId(record.id);
        try {
          await archiveAttendancePeriod(record.id);
          message.success("已归档");
          await loadPeriods();
        } catch (error) {
          message.error(getApiErrorMessage(error, "归档失败"));
        } finally {
          setActionPeriodId(null);
        }
      },
    });
  };

  const handleDelete = (record: AttendancePeriodSummary) => {
    Modal.confirm({
      title: "删除草稿",
      content: `确定删除 ${record.year}年${record.month}月 草稿记录吗？此操作不可恢复。`,
      okType: "danger",
      onOk: async () => {
        setActionPeriodId(record.id);
        try {
          await deleteAttendancePeriodDraft(record.id);
          message.success("已删除");
          await loadPeriods();
        } catch (error) {
          message.error(getApiErrorMessage(error, "删除失败"));
        } finally {
          setActionPeriodId(null);
        }
      },
    });
  };

  const handleExport = async (periodId: number, type: "excel" | "pdf") => {
    setActionPeriodId(periodId);
    try {
      const filename =
        type === "excel" ? await exportPeriodExcel(periodId) : await exportPeriodPdf(periodId);
      message.success(`已开始下载 ${filename}`);
    } catch (error) {
      message.error(getApiErrorMessage(error, type === "excel" ? "导出 Excel 失败" : "导出 PDF 失败"));
    } finally {
      setActionPeriodId(null);
    }
  };

  const exportMenu = (periodId: number): MenuProps["items"] => [
    { key: "excel", label: "导出 Excel", onClick: () => void handleExport(periodId, "excel") },
    { key: "pdf", label: "导出 PDF", onClick: () => void handleExport(periodId, "pdf") },
  ];

  const columns: ColumnsType<AttendancePeriodSummary> = [
    {
      title: "月份",
      width: 100,
      render: (_, record) => (
        <Text strong>
          {record.year}年{record.month}月
        </Text>
      ),
    },
    {
      title: "数据来源",
      dataIndex: "data_source",
      width: 110,
      render: (value: string) => DATA_SOURCE_LABELS[value] || value,
    },
    {
      title: "员工数",
      dataIndex: "employee_count",
      width: 80,
      align: "center",
    },
    {
      title: "异常数",
      dataIndex: "exception_count",
      width: 80,
      align: "center",
    },
    {
      title: "状态",
      dataIndex: "display_status",
      width: 100,
      render: (value: PeriodDisplayStatus) => (
        <Tag color={statusColor(value)}>{PERIOD_STATUS_LABELS[value] || value}</Tag>
      ),
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      width: 160,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: "最后编辑",
      dataIndex: "updated_at",
      width: 160,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: "归档信息",
      width: 180,
      render: (_, record) =>
        record.display_status === "archived" ? (
          <Space direction="vertical" size={0}>
            <Text type="secondary">{formatDateTime(record.archived_at)}</Text>
            {record.archived_by_name && <Text type="secondary">by {record.archived_by_name}</Text>}
          </Space>
        ) : (
          "—"
        ),
    },
    {
      title: "操作",
      fixed: "right",
      width: 280,
      render: (_, record) => (
        <Space wrap size="small">
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => navigate(`/attendance-table/${record.id}`)}
          >
            查看
          </Button>
          {record.is_editable && (
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              onClick={() => navigate(`/attendance-table/${record.id}`)}
            >
              继续编辑
            </Button>
          )}
          <Dropdown menu={{ items: exportMenu(record.id) }} trigger={["click"]}>
            <Button
              type="link"
              size="small"
              icon={<DownloadOutlined />}
              loading={actionPeriodId === record.id}
            >
              导出
            </Button>
          </Dropdown>
          {isAdmin && record.display_status === "draft" && (
            <Button type="link" size="small" onClick={() => handleConfirm(record)}>
              确认
            </Button>
          )}
          {isAdmin && record.display_status === "confirmed" && (
            <Button type="link" size="small" onClick={() => handleArchive(record)}>
              归档
            </Button>
          )}
          {isAdmin && record.display_status === "draft" && (
            <Button
              type="link"
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() => handleDelete(record)}
            >
              删除
            </Button>
          )}
        </Space>
      ),
    },
  ];

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
              返回首页
            </Button>
          </Link>
          <Title level={4} style={{ color: "#fff", margin: 0 }}>
            {t("attendanceRecordsPageTitle")}
          </Title>
        </Space>
        <Space>
          <Link to="/excel-workflow">
            <Button type="text" icon={<PlusOutlined />} style={{ color: "#fff" }}>
              新建上传
            </Button>
          </Link>
          <Button
            type="text"
            icon={<ReloadOutlined />}
            style={{ color: "#fff" }}
            onClick={() => void loadPeriods()}
          >
            刷新
          </Button>
        </Space>
      </Header>

      <Content style={{ padding: 20 }}>
        <Card style={{ marginBottom: 16 }}>
          <Space wrap>
            <Text type="secondary">筛选状态：</Text>
            <Select
              allowClear
              placeholder="全部状态"
              style={{ width: 140 }}
              value={statusFilter}
              onChange={setStatusFilter}
              options={Object.entries(PERIOD_STATUS_LABELS).map(([value, label]) => ({
                value,
                label,
              }))}
            />
          </Space>
        </Card>

        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={periods}
          pagination={{ pageSize: 20 }}
          scroll={{ x: 1100 }}
        />
      </Content>
    </Layout>
  );
}
