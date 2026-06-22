import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Alert, Button, Card, Input, Layout, Modal, Select, Space, Typography, message } from "antd";
import {
  ArrowLeftOutlined,
  DownloadOutlined,
  FilePdfOutlined,
  PlusOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import ExceptionFilterBar, { filtersToQuery, type ExceptionFilters } from "../components/exceptions/ExceptionFilterBar";
import ExceptionTable from "../components/exceptions/ExceptionTable";
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
const { Title } = Typography;

const TYPE_OPTIONS = Object.entries(EXCEPTION_TYPE_LABELS).map(([value, label]) => ({
  value,
  label,
}));

const SUPPLEMENT_OPTIONS = Object.entries(SUPPLEMENT_STATUS_LABELS).map(([value, label]) => ({
  value,
  label,
}));

const EMPTY_FILTERS: ExceptionFilters = {
  employee_name: "",
};

export default function ExceptionManager() {
  const { periodId } = useParams<{ periodId: string }>();
  const [records, setRecords] = useState<AbnormalRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [detecting, setDetecting] = useState(false);
  const [exportingExcel, setExportingExcel] = useState(false);
  const [exportingPdf, setExportingPdf] = useState(false);
  const [isReadOnly, setIsReadOnly] = useState(false);
  const [periodLabel, setPeriodLabel] = useState("");
  const [filters, setFilters] = useState<ExceptionFilters>(EMPTY_FILTERS);
  const [debouncedName, setDebouncedName] = useState("");
  const [periodLoaded, setPeriodLoaded] = useState(false);
  const autoDetectRan = useRef(false);
  const [addOpen, setAddOpen] = useState(false);
  const [newRecord, setNewRecord] = useState({
    employee_name: "",
    exception_type: "late_arrival" as ExceptionType,
    summary: "",
    supplement_status: "pending" as SupplementStatus,
    notes: "",
  });

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedName(filters.employee_name), 300);
    return () => window.clearTimeout(timer);
  }, [filters.employee_name]);

  const queryFilters = useMemo(
    () => filtersToQuery({ ...filters, employee_name: debouncedName }),
    [filters.exception_type, filters.supplement_status, debouncedName]
  );

  const loadRecords = useCallback(async () => {
    if (!periodId) return 0;
    setLoading(true);
    try {
      const response = await fetchPeriodExceptions(Number(periodId), queryFilters);
      setRecords(response.records);
      return response.total;
    } catch (error) {
      message.error(getApiErrorMessage(error, "加载异常记录失败"));
      setRecords([]);
      return 0;
    } finally {
      setLoading(false);
    }
  }, [periodId, queryFilters]);

  const runDetection = useCallback(async () => {
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
  }, [periodId, loadRecords]);

  useEffect(() => {
    if (!periodId) return;
    setPeriodLoaded(false);
    autoDetectRan.current = false;
    void fetchAttendancePeriod(Number(periodId))
      .then((period) => {
        setIsReadOnly(period.is_read_only);
        setPeriodLabel(`${period.year}年${period.month}月`);
      })
      .catch(() => {
        setIsReadOnly(false);
        setPeriodLabel("");
      })
      .finally(() => setPeriodLoaded(true));
  }, [periodId]);

  useEffect(() => {
    if (!periodLoaded || !periodId) return;
    void (async () => {
      const total = await loadRecords();
      if (!autoDetectRan.current && total === 0 && !isReadOnly) {
        autoDetectRan.current = true;
        await runDetection();
      }
    })();
  }, [periodLoaded, loadRecords, periodId, isReadOnly, runDetection]);

  const handleUpdate = useCallback(
    async (recordId: number, payload: { supplement_status?: SupplementStatus; notes?: string }) => {
      try {
        const updated = await updateAbnormalRecord(recordId, payload);
        setRecords((prev) => prev.map((item) => (item.id === recordId ? updated : item)));
      } catch (error) {
        message.error(getApiErrorMessage(error, "保存失败"));
      }
    },
    []
  );

  const handleDelete = useCallback((record: AbnormalRecord) => {
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
  }, []);

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
          <Link to={`/attendance-editor/${periodId}`}>
            <Button type="text" icon={<ArrowLeftOutlined />} style={{ color: "#fff" }}>
              返回考勤表
            </Button>
          </Link>
          <Title level={4} style={{ color: "#fff", margin: 0 }}>
            异常情况说明{periodLabel ? ` - ${periodLabel}` : ""}
          </Title>
        </Space>
        <Space>
          <Button
            type="text"
            icon={<DownloadOutlined />}
            style={{ color: "#fff" }}
            loading={exportingExcel}
            onClick={() => {
              if (!periodId) return;
              setExportingExcel(true);
              void exportPeriodExcel(Number(periodId))
                .then((filename) => message.success(`已开始下载 ${filename}`))
                .catch((error) => message.error(getApiErrorMessage(error, "导出 Excel 失败")))
                .finally(() => setExportingExcel(false));
            }}
          >
            导出 Excel
          </Button>
          <Button
            type="text"
            icon={<FilePdfOutlined />}
            style={{ color: "#fff" }}
            loading={exportingPdf}
            onClick={() => {
              if (!periodId) return;
              setExportingPdf(true);
              void exportPeriodPdf(Number(periodId))
                .then((filename) => message.success(`已开始下载 ${filename}`))
                .catch((error) => message.error(getApiErrorMessage(error, "导出 PDF 失败")))
                .finally(() => setExportingPdf(false));
            }}
          >
            导出 PDF
          </Button>
          {!isReadOnly && (
            <Button
              type="text"
              icon={<ReloadOutlined />}
              style={{ color: "#fff" }}
              loading={detecting}
              onClick={() => void runDetection()}
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
          <ExceptionFilterBar filters={filters} onChange={setFilters} onRefresh={() => void loadRecords()} />
        </Card>

        <Alert
          type={isReadOnly ? "warning" : "info"}
          showIcon
          style={{ marginBottom: 12 }}
          message={
            isReadOnly
              ? "此记录已归档，异常信息仅供查看。"
              : "系统自动检测旷工、缺卡、迟到、早退、未识别和冲突状态，并按员工+类别合并。点击行可展开查看具体日期。"
          }
        />

        <ExceptionTable
          records={records}
          loading={loading || detecting}
          readOnly={isReadOnly}
          onUpdate={(recordId, payload) => void handleUpdate(recordId, payload)}
          onDelete={isReadOnly ? undefined : handleDelete}
        />
      </Content>

      <Modal title="手动添加异常记录" open={addOpen} onCancel={() => setAddOpen(false)} onOk={() => void handleCreate()}>
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
            onChange={(value) => setNewRecord((prev) => ({ ...prev, exception_type: value as ExceptionType }))}
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
