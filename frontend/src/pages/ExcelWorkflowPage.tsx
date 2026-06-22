import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  Layout,
  Select,
  Space,
  Tabs,
  Typography,
  message,
} from "antd";
import { ArrowLeftOutlined, DownloadOutlined } from "@ant-design/icons";
import {
  downloadExcel,
  getApiErrorMessage,
  uploadAndConvertAttendance,
} from "../services/api";
import AttendanceConvertUpload from "../components/AttendanceConvertUpload";
import { useLanguage } from "../i18n/LanguageContext";

const { Header, Content } = Layout;
const { Title, Paragraph, Text } = Typography;

const MONTH_NAMES = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"];

export default function ExcelWorkflowPage() {
  const { t } = useLanguage();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [downloading, setDownloading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

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
      const filename = await uploadAndConvertAttendance(file, {
        year,
        month,
        onProgress: setUploadProgress,
      });
      message.success(`四表考勤 Excel 已开始下载：${filename}`);
    } catch (error) {
      message.error(getApiErrorMessage(error, "上传并转换考勤表失败"));
    } finally {
      setUploading(false);
      setUploadProgress(0);
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
            {t("excelWorkflow")}
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
                    message="上传钉钉原始月度汇总后，系统将解析数据并生成签字/情况说明/月度汇总/加班结算四表 Excel，并自动下载。"
                  />
                  <Space direction="vertical" style={{ width: "100%" }}>
                    <AttendanceConvertUpload
                      year={year}
                      month={month}
                      loading={uploading}
                      progress={uploadProgress}
                      label="上传并转换考勤表"
                      hint="上传钉钉月度汇总，自动生成签字/情况说明/月度汇总/加班结算四表 Excel，并自动下载。"
                      onFileSelected={handleUploadSource}
                    />
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
