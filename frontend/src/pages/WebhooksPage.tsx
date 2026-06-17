import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Layout,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import {
  ArrowLeftOutlined,
  CopyOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import { useAuth } from "../auth/AuthContext";
import {
  fetchWebhookConfig,
  fetchWebhookEvents,
  getApiErrorMessage,
  replayWebhookEvent,
  testWebhook,
  WebhookConfig,
  WebhookEvent,
} from "../services/webhooks";

const { Header, Content } = Layout;
const { Title, Text, Paragraph } = Typography;

const STATUS_COLORS: Record<string, string> = {
  queued: "blue",
  processing: "gold",
  processed: "green",
  duplicate: "default",
  failed: "red",
};

const EVENT_TYPES = [
  "attendance_check",
  "leave_approved",
  "overtime_approved",
  "employee_joined",
  "employee_left",
];

function copyText(text: string) {
  void navigator.clipboard.writeText(text);
  message.success("Copied to clipboard");
}

export default function WebhooksPage() {
  const { user } = useAuth();
  const [config, setConfig] = useState<WebhookConfig | null>(null);
  const [events, setEvents] = useState<WebhookEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [testing, setTesting] = useState(false);
  const [form] = Form.useForm();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [configData, eventData] = await Promise.all([
        fetchWebhookConfig(),
        fetchWebhookEvents(50, statusFilter),
      ]);
      setConfig(configData);
      setEvents(eventData);
    } catch (error) {
      message.error(getApiErrorMessage(error, "Failed to load webhook data"));
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleReplay = async (eventId: number) => {
    try {
      await replayWebhookEvent(eventId);
      message.success(`Replay queued for event #${eventId}`);
      void loadData();
    } catch (error) {
      message.error(getApiErrorMessage(error, "Replay failed"));
    }
  };

  const handleTest = async () => {
    try {
      const values = await form.validateFields();
      setTesting(true);
      await testWebhook(values);
      message.success("Test webhook processed");
      void loadData();
    } catch (error) {
      if (error && typeof error === "object" && "errorFields" in error) {
        return;
      }
      message.error(getApiErrorMessage(error, "Test webhook failed"));
    } finally {
      setTesting(false);
    }
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
          <Link to="/">
            <Button type="text" icon={<ArrowLeftOutlined />} style={{ color: "#fff" }}>
              Dashboard
            </Button>
          </Link>
          <Title level={4} style={{ color: "#fff", margin: 0 }}>
            Webhook Management
          </Title>
        </Space>
        <Text style={{ color: "#fff" }}>{user?.name}</Text>
      </Header>

      <Content style={{ padding: 24, maxWidth: 1200, margin: "0 auto", width: "100%" }}>
        {config && (
          <Card title="DingTalk Registration URLs" style={{ marginBottom: 16 }}>
            <Paragraph type="secondary">
              Register these callback URLs in the DingTalk Open Platform for real-time attendance and
              employee sync. Set <Text code>DINGTALK_WEBHOOK_SECRET</Text> and configure signature
              verification headers.
            </Paragraph>
            <Space direction="vertical" style={{ width: "100%" }}>
              <Space wrap>
                <Text strong>Attendance:</Text>
                <Text code>{config.attendance_url}</Text>
                <Button
                  size="small"
                  icon={<CopyOutlined />}
                  onClick={() => copyText(config.attendance_url)}
                />
              </Space>
              <Space wrap>
                <Text strong>Employee:</Text>
                <Text code>{config.employee_url}</Text>
                <Button
                  size="small"
                  icon={<CopyOutlined />}
                  onClick={() => copyText(config.employee_url)}
                />
              </Space>
              <Space wrap>
                <Tag color={config.webhook_secret_configured ? "green" : "orange"}>
                  Secret {config.webhook_secret_configured ? "configured" : "not set"}
                </Tag>
                <Tag color={config.demo_mode ? "blue" : "default"}>
                  Demo mode {config.demo_mode ? "on" : "off"}
                </Tag>
                <Text type="secondary">
                  Timestamp window: {config.timestamp_max_skew_seconds}s
                </Text>
              </Space>
              <Text type="secondary">
                Supported events: {config.supported_event_types.join(", ")}
              </Text>
            </Space>
          </Card>
        )}

        <Card
          title="Recent Webhook Events"
          extra={
            <Space>
              <Select
                allowClear
                placeholder="Filter status"
                style={{ width: 140 }}
                value={statusFilter}
                onChange={setStatusFilter}
                options={[
                  { value: "queued", label: "Queued" },
                  { value: "processing", label: "Processing" },
                  { value: "processed", label: "Processed" },
                  { value: "failed", label: "Failed" },
                  { value: "duplicate", label: "Duplicate" },
                ]}
              />
              <Button icon={<ReloadOutlined />} onClick={() => void loadData()}>
                Refresh
              </Button>
            </Space>
          }
          style={{ marginBottom: 16 }}
        >
          <Table
            rowKey="id"
            loading={loading}
            dataSource={events}
            pagination={{ pageSize: 10 }}
            columns={[
              { title: "ID", dataIndex: "id", width: 70 },
              { title: "Endpoint", dataIndex: "endpoint", width: 100 },
              { title: "Event", dataIndex: "event_type", width: 160 },
              { title: "User", dataIndex: "dingtalk_user_id", width: 120 },
              {
                title: "Status",
                dataIndex: "status",
                width: 110,
                render: (value: string) => <Tag color={STATUS_COLORS[value] || "default"}>{value}</Tag>,
              },
              {
                title: "Created",
                dataIndex: "created_at",
                width: 180,
                render: (value: string) => new Date(value).toLocaleString(),
              },
              {
                title: "Error",
                dataIndex: "error_message",
                ellipsis: true,
              },
              {
                title: "Actions",
                width: 100,
                render: (_: unknown, record: WebhookEvent) =>
                  record.status === "failed" ? (
                    <Button
                      size="small"
                      icon={<PlayCircleOutlined />}
                      onClick={() => void handleReplay(record.id)}
                    >
                      Replay
                    </Button>
                  ) : null,
              },
            ]}
          />
        </Card>

        <Card title="Test Webhook">
          {config?.demo_mode ? (
            <Alert
              type="info"
              showIcon
              message="Demo mode allows test webhooks without signature headers."
              style={{ marginBottom: 16 }}
            />
          ) : (
            <Alert
              type="warning"
              showIcon
              message="Production mode requires DINGTALK_WEBHOOK_SECRET or enable DEMO_MODE for testing."
              style={{ marginBottom: 16 }}
            />
          )}
          <Form
            form={form}
            layout="vertical"
            initialValues={{ event_type: "attendance_check", user_id: "demo_user_001" }}
          >
            <Form.Item name="user_id" label="DingTalk user ID" rules={[{ required: true }]}>
              <Input placeholder="userid from DingTalk" />
            </Form.Item>
            <Form.Item name="event_type" label="Event type" rules={[{ required: true }]}>
              <Select options={EVENT_TYPES.map((value) => ({ value, label: value }))} />
            </Form.Item>
            <Form.Item name="work_date" label="Work date (attendance events)">
              <Input placeholder="YYYY-MM-DD" />
            </Form.Item>
            <Button type="primary" loading={testing} onClick={() => void handleTest()}>
              Send test webhook
            </Button>
          </Form>
        </Card>
      </Content>
    </Layout>
  );
}
