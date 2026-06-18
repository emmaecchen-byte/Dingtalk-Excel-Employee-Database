import { useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  Layout,
  List,
  Progress,
  Select,
  Space,
  Tabs,
  Tag,
  Typography,
  message,
} from "antd";
import { ArrowLeftOutlined, DownloadOutlined, UploadOutlined } from "@ant-design/icons";
import {
  AttendanceUploadResponse,
  downloadExcel,
  getApiErrorMessage,
  uploadAttendanceExcel,
} from "../services/api";

const { Header, Content } = Layout;
const { Title, Paragraph, Text } = Typography;

const MONTH_NAMES = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"];

function severityColor(severity: string) {
  if (severity === "Error") return "red";
  if (severity === "Warning") return "orange";
  return "blue";
}

export default function ExcelWorkflowPage() {
  const navigate = useNavigate();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [downloading, setDownloading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadResult, setUploadResult] = useState<AttendanceUploadResponse | null>(null);
  const uploadInputRef = useRef<HTMLInputElement | null>(null);

  const yearOptions = useMemo(() => {
    const currentYear = new Date().getFullYear();
    return Array.from({ length: 5 }, (_, index) => {
      const value = currentYear - 2 + index;
      return { value, label: `${value}年` };
    });
  }, []);

  const monthOptions = useMemo(
    () => MONTH_NAMES.map((label, index) => ({ value: index + 1, label })),
    []
  );

  const handleDownloadMonthlyOnly = async () => {
    try {
      setDownloading(true);
      await downloadExcel(year, month);
      message.success("已下载月度汇总（单表）Excel");
    } catch (error) {
      message.error(getApiErrorMessage(error, "下载月度汇总失败"));
    } finally {
      setDownloading(false);
    }
  };

  const handleUploadSource = async (file: File) => {
    try {
      setUploading(true);
      setUploadResult(null);
      const parsed = await uploadAttendanceExcel(file, {
        year,
        month,
        onProgress: setUploadProgress,
      });
      setUploadResult(parsed);

      if (parsed.has_blocking_errors) {
        message.error("上传完成，但存在阻断性校验错误，请修正后重试");
        return;
      }

      message.success(`已解析 ${parsed.employee_count} 名员工，写入 ${parsed.daily_record_count} 条日考勤记录`);
      navigate(`/attendance-table/${parsed.period_id}`);
    } catch (error) {
      message.error(getApiErrorMessage(error, "上传钉钉原始月度汇总失败"));
    } finally {
      setUploading(false);
      setUploadProgress(0);
      if (uploadInputRef.current) {
        uploadInputRef.current.value = "";
      }
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
          <Link to="/">
            <Button type="text" icon={<ArrowLeftOutlined />} style={{ color: "#fff" }}>
              返回首页
            </Button>
          </Link>
          <Title level={4} style={{ color: "#fff", margin: 0 }}>
            Excel 两步流程
          </Title>
        </Space>
      </Header>

      <Content style={{ padding: 24, maxWidth: 1000, margin: "0 auto", width: "100%" }}>
        <Card style={{ marginBottom: 16 }}>
          <Space wrap>
            <Text strong>选择月份：</Text>
            <Select value={year} options={yearOptions} onChange={setYear} />
            <Select value={month} options={monthOptions} onChange={setMonth} />
          </Space>
        </Card>

        <Tabs
          items={[
            {
              key: "step1",
              label: "步骤1：下载月度汇总",
              children: (
                <Card>
                  <Paragraph>
                    第一步只导出 <Text code>月度汇总</Text> 单个工作表（不包含签字/情况说明/加班表）。
                  </Paragraph>
                  <Button
                    type="primary"
                    icon={<DownloadOutlined />}
                    loading={downloading}
                    onClick={() => void handleDownloadMonthlyOnly()}
                  >
                    下载月度汇总Excel
                  </Button>
                </Card>
              ),
            },
            {
              key: "step2",
              label: "步骤2：上传钉钉原始表",
              children: (
                <Card>
                  <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 12 }}
                    message="上传钉钉原始月度汇总后，系统会先解析并写入数据库，再生成四表Excel。"
                  />
                  <input
                    ref={uploadInputRef}
                    type="file"
                    accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    hidden
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (file) {
                        void handleUploadSource(file);
                      }
                    }}
                  />
                  <Space direction="vertical" style={{ width: "100%" }}>
                    <Button
                      icon={<UploadOutlined />}
                      loading={uploading}
                      onClick={() => uploadInputRef.current?.click()}
                    >
                      上传钉钉月度汇总（解析 + 生成四表）
                    </Button>
                    {uploading && <Progress percent={uploadProgress} status="active" />}
                    {uploadResult && (
                      <Alert
                        type={uploadResult.has_blocking_errors ? "error" : "success"}
                        showIcon
                        message={
                          uploadResult.has_blocking_errors
                            ? "校验未通过，数据未完整写入"
                            : `解析成功：${uploadResult.employee_count} 名员工，${uploadResult.requires_review_count} 项需复核`
                        }
                      />
                    )}
                    {uploadResult && uploadResult.validation_issues.length > 0 && (
                      <List
                        size="small"
                        bordered
                        dataSource={uploadResult.validation_issues}
                        renderItem={(issue) => (
                          <List.Item>
                            <Space>
                              <Tag color={severityColor(issue.severity)}>{issue.severity}</Tag>
                              <Text>{issue.message}</Text>
                            </Space>
                          </List.Item>
                        )}
                      />
                    )}
                  </Space>
                </Card>
              ),
            },
          ]}
        />
      </Content>
    </Layout>
  );
}
