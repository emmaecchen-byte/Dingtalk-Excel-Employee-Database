import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Alert, Button, Card, Form, Input, Select, Space, Typography, message } from "antd";
import { LockOutlined, MailOutlined, UserOutlined } from "@ant-design/icons";
import { registerUser } from "../auth/api";
import { useLanguage } from "../i18n/LanguageContext";

const { Title, Text } = Typography;

const ROLE_OPTIONS = [
  { value: "hr_admin", label: "HR Admin" },
  { value: "hr_viewer", label: "HR Viewer" },
  { value: "manager", label: "Manager" },
  { value: "employee", label: "Employee" },
];

export default function RegisterPage() {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onFinish = async (values: {
    name: string;
    email: string;
    password: string;
    role: string;
  }) => {
    setSubmitting(true);
    setError(null);
    try {
      await registerUser(values);
      message.success(t("registerSuccess"));
      navigate("/");
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        t("registerFailed");
      setError(typeof detail === "string" ? detail : t("registerFailed"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        background: "#f5f7fa",
        padding: 24,
      }}
    >
      <Card style={{ width: "100%", maxWidth: 480 }}>
        <Space direction="vertical" size="large" style={{ width: "100%" }}>
          <div>
            <Title level={3} style={{ marginBottom: 8 }}>
              {t("registerTitle")}
            </Title>
            <Text type="secondary">{t("registerSubtitle")}</Text>
          </div>

          {error && <Alert type="error" message={error} showIcon />}

          <Form layout="vertical" onFinish={onFinish} initialValues={{ role: "hr_viewer" }}>
            <Form.Item label={t("name")} name="name" rules={[{ required: true, message: t("nameRequired") }]}>
              <Input prefix={<UserOutlined />} />
            </Form.Item>

            <Form.Item
              label={t("email")}
              name="email"
              rules={[
                { required: true, message: t("emailRequired") },
                { type: "email", message: t("emailInvalid") },
              ]}
            >
              <Input prefix={<MailOutlined />} />
            </Form.Item>

            <Form.Item
              label={t("password")}
              name="password"
              rules={[
                { required: true, message: t("passwordRequired") },
                { min: 8, message: t("passwordMinLength") },
              ]}
            >
              <Input.Password prefix={<LockOutlined />} />
            </Form.Item>

            <Form.Item label={t("role")} name="role" rules={[{ required: true }]}>
              <Select options={ROLE_OPTIONS} />
            </Form.Item>

            <Space>
              <Button type="primary" htmlType="submit" loading={submitting}>
                {t("registerButton")}
              </Button>
              <Link to="/">
                <Button>{t("cancel")}</Button>
              </Link>
            </Space>
          </Form>
        </Space>
      </Card>
    </div>
  );
}
