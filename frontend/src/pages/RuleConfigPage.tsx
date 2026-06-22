import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Button,
  Card,
  Checkbox,
  Input,
  InputNumber,
  Layout,
  Modal,
  Select,
  Space,
  Table,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { ArrowLeftOutlined, PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import {
  AttendanceRule,
  AttendanceRulePayload,
  LEAVE_TYPE_OPTIONS,
  createAttendanceRule,
  deleteAttendanceRule,
  fetchAttendanceRules,
  updateAttendanceRule,
} from "../services/rules";
import { getApiErrorMessage } from "../services/api";
import { useLanguage } from "../i18n/LanguageContext";

const { Header, Content } = Layout;
const { Title, Text } = Typography;

type EditableRule = AttendanceRule & { _dirty?: boolean };

const EMPTY_RULE: AttendanceRulePayload = {
  raw_keyword: "",
  normalized_status: "",
  symbol: "",
  counts_as_attendance: false,
  counts_as_meal_allowance: false,
  leave_type: "",
  is_abnormal: false,
  priority: 0,
};

export default function RuleConfigPage() {
  const { t } = useLanguage();
  const [rules, setRules] = useState<EditableRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [newRule, setNewRule] = useState<AttendanceRulePayload>(EMPTY_RULE);

  const loadRules = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetchAttendanceRules();
      setRules(response.rules);
    } catch (error) {
      message.error(getApiErrorMessage(error, "加载规则失败"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRules();
  }, [loadRules]);

  const updateLocalRule = (id: number, patch: Partial<EditableRule>) => {
    setRules((prev) =>
      prev.map((rule) => (rule.id === id ? { ...rule, ...patch, _dirty: true } : rule))
    );
  };

  const handleSave = async (rule: EditableRule) => {
    setSavingId(rule.id);
    try {
      const updated = await updateAttendanceRule(rule.id, {
        raw_keyword: rule.raw_keyword,
        normalized_status: rule.normalized_status,
        symbol: rule.symbol,
        counts_as_attendance: rule.counts_as_attendance,
        counts_as_meal_allowance: rule.counts_as_meal_allowance,
        leave_type: rule.leave_type || null,
        is_abnormal: rule.is_abnormal,
        priority: rule.priority,
      });
      setRules((prev) => prev.map((item) => (item.id === rule.id ? updated : item)));
      message.success("已保存");
    } catch (error) {
      message.error(getApiErrorMessage(error, "保存失败"));
    } finally {
      setSavingId(null);
    }
  };

  const handleDelete = (rule: AttendanceRule) => {
    Modal.confirm({
      title: "删除规则",
      content: `确定删除关键词「${rule.raw_keyword}」的规则吗？`,
      okType: "danger",
      onOk: async () => {
        try {
          await deleteAttendanceRule(rule.id);
          setRules((prev) => prev.filter((item) => item.id !== rule.id));
          message.success("已删除");
        } catch (error) {
          message.error(getApiErrorMessage(error, "删除失败"));
        }
      },
    });
  };

  const handleCreate = async () => {
    if (!newRule.raw_keyword.trim() || !newRule.normalized_status.trim()) {
      message.warning("请填写关键词和标准状态");
      return;
    }
    try {
      const created = await createAttendanceRule({
        ...newRule,
        raw_keyword: newRule.raw_keyword.trim(),
        normalized_status: newRule.normalized_status.trim(),
        leave_type: newRule.leave_type || null,
      });
      setRules((prev) => [...prev, created]);
      setAddOpen(false);
      setNewRule(EMPTY_RULE);
      message.success("已添加规则");
    } catch (error) {
      message.error(getApiErrorMessage(error, "添加失败"));
    }
  };

  const columns: ColumnsType<EditableRule> = [
    {
      title: "关键词",
      dataIndex: "raw_keyword",
      width: 120,
      render: (value, record) => (
        <Input
          size="small"
          value={value}
          onChange={(e) => updateLocalRule(record.id, { raw_keyword: e.target.value })}
        />
      ),
    },
    {
      title: "标准状态",
      dataIndex: "normalized_status",
      width: 110,
      render: (value, record) => (
        <Input
          size="small"
          value={value}
          onChange={(e) => updateLocalRule(record.id, { normalized_status: e.target.value })}
        />
      ),
    },
    {
      title: "符号",
      dataIndex: "symbol",
      width: 70,
      render: (value, record) => (
        <Input
          size="small"
          value={value}
          onChange={(e) => updateLocalRule(record.id, { symbol: e.target.value })}
        />
      ),
    },
    {
      title: "计出勤",
      dataIndex: "counts_as_attendance",
      width: 80,
      align: "center",
      render: (value, record) => (
        <Checkbox
          checked={value}
          onChange={(e) => updateLocalRule(record.id, { counts_as_attendance: e.target.checked })}
        />
      ),
    },
    {
      title: "计餐补",
      dataIndex: "counts_as_meal_allowance",
      width: 80,
      align: "center",
      render: (value, record) => (
        <Checkbox
          checked={value}
          onChange={(e) =>
            updateLocalRule(record.id, { counts_as_meal_allowance: e.target.checked })
          }
        />
      ),
    },
    {
      title: "假期类型",
      dataIndex: "leave_type",
      width: 120,
      render: (value, record) => (
        <Select
          size="small"
          style={{ width: 110 }}
          value={value ?? ""}
          options={LEAVE_TYPE_OPTIONS}
          onChange={(next) => updateLocalRule(record.id, { leave_type: next || null })}
        />
      ),
    },
    {
      title: "异常",
      dataIndex: "is_abnormal",
      width: 70,
      align: "center",
      render: (value, record) => (
        <Checkbox
          checked={value}
          onChange={(e) => updateLocalRule(record.id, { is_abnormal: e.target.checked })}
        />
      ),
    },
    {
      title: "优先级",
      dataIndex: "priority",
      width: 90,
      render: (value, record) => (
        <InputNumber
          size="small"
          style={{ width: 72 }}
          value={value}
          onChange={(next) => updateLocalRule(record.id, { priority: Number(next ?? 0) })}
        />
      ),
    },
    {
      title: "操作",
      width: 140,
      fixed: "right",
      render: (_, record) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            loading={savingId === record.id}
            onClick={() => void handleSave(record)}
          >
            保存
          </Button>
          <Button type="link" danger size="small" onClick={() => handleDelete(record)}>
            删除
          </Button>
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
            {t("ruleConfig")}
          </Title>
        </Space>
        <Space>
          <Button type="text" icon={<PlusOutlined />} style={{ color: "#fff" }} onClick={() => setAddOpen(true)}>
            添加规则
          </Button>
          <Button
            type="text"
            icon={<ReloadOutlined />}
            style={{ color: "#fff" }}
            onClick={() => void loadRules()}
          >
            刷新
          </Button>
        </Space>
      </Header>

      <Content style={{ padding: 20 }}>
        <Card style={{ marginBottom: 16 }}>
          <Text type="secondary">
            配置考勤状态映射与计数规则。优先级越高，在关键词冲突时优先匹配。修改后立即生效，无需重新部署。
          </Text>
        </Card>

        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={rules}
          pagination={{ pageSize: 25 }}
          scroll={{ x: 1200 }}
        />
      </Content>

      <Modal title="添加考勤规则" open={addOpen} onCancel={() => setAddOpen(false)} onOk={() => void handleCreate()}>
        <Space direction="vertical" style={{ width: "100%" }}>
          <Input
            placeholder="关键词（如：迟到、正常）"
            value={newRule.raw_keyword}
            onChange={(e) => setNewRule((prev) => ({ ...prev, raw_keyword: e.target.value }))}
          />
          <Input
            placeholder="标准状态"
            value={newRule.normalized_status}
            onChange={(e) => setNewRule((prev) => ({ ...prev, normalized_status: e.target.value }))}
          />
          <Input
            placeholder="符号（如：√、迟到）"
            value={newRule.symbol}
            onChange={(e) => setNewRule((prev) => ({ ...prev, symbol: e.target.value }))}
          />
          <Select
            style={{ width: "100%" }}
            placeholder="假期类型"
            value={newRule.leave_type ?? ""}
            options={LEAVE_TYPE_OPTIONS}
            onChange={(value) => setNewRule((prev) => ({ ...prev, leave_type: value || null }))}
          />
          <InputNumber
            style={{ width: "100%" }}
            placeholder="优先级"
            value={newRule.priority}
            onChange={(value) => setNewRule((prev) => ({ ...prev, priority: Number(value ?? 0) }))}
          />
          <Space>
            <Checkbox
              checked={newRule.counts_as_attendance}
              onChange={(e) => setNewRule((prev) => ({ ...prev, counts_as_attendance: e.target.checked }))}
            >
              计出勤
            </Checkbox>
            <Checkbox
              checked={newRule.counts_as_meal_allowance}
              onChange={(e) =>
                setNewRule((prev) => ({ ...prev, counts_as_meal_allowance: e.target.checked }))
              }
            >
              计餐补
            </Checkbox>
            <Checkbox
              checked={newRule.is_abnormal}
              onChange={(e) => setNewRule((prev) => ({ ...prev, is_abnormal: e.target.checked }))}
            >
              异常
            </Checkbox>
          </Space>
        </Space>
      </Modal>
    </Layout>
  );
}
