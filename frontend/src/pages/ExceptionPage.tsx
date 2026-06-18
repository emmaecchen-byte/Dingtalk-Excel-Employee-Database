import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  Input,
  Layout,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { ArrowLeftOutlined, DownloadOutlined, FilePdfOutlined, PlusOutlined, ReloadOutlined, SearchOutlined } from "@ant-design/icons";
import {
  AbnormalRecord,
  EXCEPTION_TYPE_LABELS,
  ExceptionType,
  SUPPLEMENT_STATUS_LABELS,
  SupplementStatus,
  createAbnormalRecord,
  deleteAbnormalRecord,
  detectPeriodExceptions,
  fetchPeriodExceptions,
  updateAbnormalRecord,
} from "../services/exceptions";
import { getApiErrorMessage } from "../services/api";
import { exportPeriodExcel, exportPeriodPdf } from "../services/periodExport";
import { fetchAttendancePeriod } from "../services/attendancePeriods";

const { Header, Content } = Layout;
const { Title, Text } = Typography;

const SUPPLEMENT_OPTIONS = Object.entries(SUPPLEMENT_STATUS_LABELS).map(([value, label]) => ({
  value,
  label,
}));

const TYPE_OPTIONS = Object.entries(EXCEPTION_TYPE_LABELS).map(([value, label]) => ({
  value,
  label,
}));

function supplementColor(status: SupplementStatus) {
  if (status === "yes") return "green";
  if (status === "no") return "red";
  if (status === "not_required") return "default";
  return "gold";
}

export default function ExceptionPage() {
  const { periodId } = useParams<{ periodId: string }>();
  const [records, setRecords] = useState<AbnormalRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [detecting, setDetecting] = useState(false);
  const [exportingExcel, setExportingExcel] = useState(false);
  const [exportingPdf, setExportingPdf] = useState(false);
  const [isReadOnly, setIsReadOnly] = useState(false);
  const [nameFilter, setNameFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState<string | undefined>();
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [addOpen, setAddOpen] = useState(false);
  const [newRecord, setNewRecord] = useState({
    employee_name: "",
    exception_type: "late_arrival" as ExceptionType,
    summary: "",
    supplement_status: "pending" as SupplementStatus,
    notes: "",
  });

  const loadRecords = useCallback(async () => {
    if (!periodId) return;
    setLoading(true);
    try {
      const response = await fetchPeriodExceptions(Number(periodId), {
        employee_name: nameFilter || undefined,
        exception_type: typeFilter,
        supplement_status: statusFilter,
      });
      setRecords(response.records);
    } catch (error) {
      message.error(getApiErrorMessage(error, "加载异常记录失败"));
    } finally {
      setLoading(false);
    }
  }, [periodId, nameFilter, typeFilter, statusFilter]);

  useEffect(() => {
    void loadRecords();
  }, [loadRecords]);

  useEffect(() => {
    if (!periodId) return;
    void fetchAttendancePeriod(Number(periodId))
      .then((period) => setIsReadOnly(period.is_read_only))
      .catch(() => setIsReadOnly(false));
  }, [periodId]);

  const handleDetect = async () => {
    if (!periodId) return;
    setDetecting(true);
    try {
      const result = await detectPeriodExceptions(Number(periodId));
      message.success(`已检测 ${result.records_created} 条异常记录`);
      await loadRecords();
    } catch (error) {
      message.error(getApiErrorMessage(error, "异常检测失败"));
    } finally {
      setDetecting(false);
    }
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

  const handleUpdate = async (
    recordId: number,
    payload: { supplement_status?: SupplementStatus; notes?: string }
  ) => {
    try {
      const updated = await updateAbnormalRecord(recordId, payload);
      setRecords((prev) => prev.map((item) => (item.id === recordId ? updated : item)));
      message.success("已保存");
    } catch (error) {
      message.error(getApiErrorMessage(error, "保存失败"));
    }
  };

  const handleDelete = (record: AbnormalRecord) => {
    Modal.confirm({
      title: "删除异常记录",
      content: `确定删除 ${record.employee_name} 的「${EXCEPTION_TYPE_LABELS[record.exception_type]}」记录吗？`,
      onOk: async () => {
        try {
          await deleteAbnormalRecord(record.id);
          setRecords((prev) => prev.filter((item) => item.id !== record.id));
          message.success("已删除");
        } catch (error) {
          message.error(getApiErrorMessage(error, "删除失败"));
        }
      },
    });
  };

  const handleCreate = async () => {
    if (!periodId || !newRecord.employee_name.trim()) {
      message.warning("请填写员工姓名");
      return;
    }
    try {
      const created = await createAbnormalRecord(Number(periodId), {
        employee_name: newRecord.employee_name.trim(),
        exception_type: newRecord.exception_type,
        summary: newRecord.summary || EXCEPTION_TYPE_LABELS[newRecord.exception_type],
        supplement_status: newRecord.supplement_status,
        notes: newRecord.notes || undefined,
      });
      setRecords((prev) => [...prev, created]);
      setAddOpen(false);
      setNewRecord({
        employee_name: "",
        exception_type: "late_arrival",
        summary: "",
        supplement_status: "pending",
        notes: "",
      });
      message.success("已添加异常记录");
    } catch (error) {
      message.error(getApiErrorMessage(error, "添加失败"));
    }
  };

  const columns: ColumnsType<AbnormalRecord> = useMemo(
    () => [
      {
        title: "姓名",
        dataIndex: "employee_name",
        width: 100,
        fixed: "left",
      },
      {
        title: "异常类型",
        dataIndex: "exception_type",
        width: 100,
        render: (value: ExceptionType) => (
          <Tag>{EXCEPTION_TYPE_LABELS[value] || value}</Tag>
        ),
      },
      {
        title: "日期",
        dataIndex: "dates",
        width: 220,
        ellipsis: true,
        render: (dates: AbnormalRecord["dates"]) =>
          dates.length > 0 ? dates.map((item) => item.date).join("、") : "—",
      },
      {
        title: "异常详情",
        dataIndex: "summary",
        width: 260,
        ellipsis: true,
        render: (_, record) => record.summary,
      },
      {
        title: "补交状态",
        dataIndex: "supplement_status",
        width: 130,
        render: (value: SupplementStatus, record) =>
          isReadOnly ? (
            <Text>{SUPPLEMENT_STATUS_LABELS[value]}</Text>
          ) : (
            <Select
              size="small"
              style={{ width: 110 }}
              value={value}
              options={SUPPLEMENT_OPTIONS}
              onChange={(next) =>
                void handleUpdate(record.id, { supplement_status: next as SupplementStatus })
              }
            />
          ),
      },
      {
        title: "备注",
        dataIndex: "notes",
        width: 220,
        render: (value: string | null | undefined, record) =>
          isReadOnly ? (
            <Text>{value || "—"}</Text>
          ) : (
            <Input
              size="small"
              defaultValue={value ?? ""}
              placeholder="填写备注"
              onBlur={(event) => {
                const next = event.target.value;
                if ((value ?? "") !== next) {
                  void handleUpdate(record.id, { notes: next });
                }
              }}
            />
          ),
      },
      ...(isReadOnly
        ? []
        : [
            {
              title: "操作",
              width: 90,
              fixed: "right" as const,
              render: (_: unknown, record: AbnormalRecord) => (
                <Button type="link" danger size="small" onClick={() => handleDelete(record)}>
                  删除
                </Button>
              ),
            },
          ]),
    ],
    [isReadOnly]
  );

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
          <Link to={`/attendance-table/${periodId}`}>
            <Button type="text" icon={<ArrowLeftOutlined />} style={{ color: "#fff" }}>
              返回考勤表
            </Button>
          </Link>
          <Title level={4} style={{ color: "#fff", margin: 0 }}>
            情况说明 / 异常处理
          </Title>
        </Space>
        <Space>
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
          {!isReadOnly && (
            <Button
              type="text"
              icon={<ReloadOutlined />}
              style={{ color: "#fff" }}
              loading={detecting}
              onClick={() => void handleDetect()}
            >
              重新检测
            </Button>
          )}
          {!isReadOnly && (
            <Button type="text" icon={<PlusOutlined />} style={{ color: "#fff" }} onClick={() => setAddOpen(true)}>
              手动添加
            </Button>
          )}
        </Space>
      </Header>

      <Content style={{ padding: 20 }}>
        <Card style={{ marginBottom: 16 }}>
          <Space wrap>
            <Input
              placeholder="按姓名筛选"
              prefix={<SearchOutlined />}
              value={nameFilter}
              onChange={(event) => setNameFilter(event.target.value)}
              style={{ width: 180 }}
            />
            <Select
              allowClear
              placeholder="异常类型"
              style={{ width: 140 }}
              options={TYPE_OPTIONS}
              value={typeFilter}
              onChange={setTypeFilter}
            />
            <Select
              allowClear
              placeholder="补交状态"
              style={{ width: 140 }}
              options={SUPPLEMENT_OPTIONS}
              value={statusFilter}
              onChange={setStatusFilter}
            />
            <Button onClick={() => void loadRecords()}>应用筛选</Button>
          </Space>
        </Card>

        <Alert
          type={isReadOnly ? "warning" : "info"}
          showIcon
          style={{ marginBottom: 12 }}
          message={
            isReadOnly
              ? "此记录已归档，异常信息仅供查看。"
              : "系统自动检测旷工、缺卡、迟到、早退、未识别和冲突状态，并按员工+类别合并。"
          }
        />

        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={records}
          pagination={{ pageSize: 20 }}
          scroll={{ x: 1200 }}
          expandable={{
            expandedRowRender: (record) => (
              <div style={{ padding: "4px 0" }}>
                {record.dates.map((item) => (
                  <div key={`${record.id}-${item.day}`} style={{ marginBottom: 6 }}>
                    <Tag color={supplementColor(record.supplement_status)}>{item.date}</Tag>
                    <Text>{item.detail || item.raw_text || `${item.morning} / ${item.afternoon}`}</Text>
                  </div>
                ))}
                {record.edit_logs.length > 0 && (
                  <div style={{ marginTop: 8 }}>
                    <Text type="secondary">最近编辑：</Text>
                    {record.edit_logs.slice(0, 3).map((log) => (
                      <div key={log.id}>
                        <Text type="secondary">
                          {log.editor_name || "HR"} 修改 {log.field_name}: {log.old_value || "—"} →{" "}
                          {log.new_value || "—"} ({new Date(log.edited_at).toLocaleString()})
                        </Text>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ),
            rowExpandable: (record) => record.dates.length > 0,
          }}
        />
      </Content>

      <Modal
        title="手动添加异常记录"
        open={addOpen}
        onCancel={() => setAddOpen(false)}
        onOk={() => void handleCreate()}
      >
        <Space direction="vertical" style={{ width: "100%" }}>
          <Input
            placeholder="员工姓名"
            value={newRecord.employee_name}
            onChange={(event) => setNewRecord((prev) => ({ ...prev, employee_name: event.target.value }))}
          />
          <Select
            style={{ width: "100%" }}
            value={newRecord.exception_type}
            options={TYPE_OPTIONS}
            onChange={(value) =>
              setNewRecord((prev) => ({ ...prev, exception_type: value as ExceptionType }))
            }
          />
          <Input
            placeholder="异常摘要"
            value={newRecord.summary}
            onChange={(event) => setNewRecord((prev) => ({ ...prev, summary: event.target.value }))}
          />
          <Select
            style={{ width: "100%" }}
            value={newRecord.supplement_status}
            options={SUPPLEMENT_OPTIONS}
            onChange={(value) =>
              setNewRecord((prev) => ({ ...prev, supplement_status: value as SupplementStatus }))
            }
          />
          <Input.TextArea
            placeholder="备注"
            value={newRecord.notes}
            onChange={(event) => setNewRecord((prev) => ({ ...prev, notes: event.target.value }))}
          />
        </Space>
      </Modal>
    </Layout>
  );
}
