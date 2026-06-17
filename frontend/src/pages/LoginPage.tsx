import { useEffect, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { Alert, Button, Card, Divider, Form, Input, Space, Typography } from "antd";
import { DingdingOutlined, LockOutlined, MailOutlined } from "@ant-design/icons";
import { useAuth } from "../auth/AuthContext";
import { fetchDingTalkOAuthStatus, getDingTalkLoginUrl } from "../auth/api";
import { useLanguage } from "../i18n/LanguageContext";

const { Title, Text } = Typography;

export default function LoginPage() {
  const { login, isAuthenticated, loading } = useAuth();
  const { t } = useLanguage();
  const navigate = useNavigate();
  const location = useLocation();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dingtalkEnabled, setDingtalkEnabled] = useState<boolean | null>(null);
  const [dingtalkMissing, setDingtalkMissing] = useState<string[]>([]);

  const from = (location.state as { from?: string } | null)?.from || "/";

  useEffect(() => {
    fetchDingTalkOAuthStatus()
      .then((status) => {
        setDingtalkEnabled(status.enabled);
        setDingtalkMissing(status.missing_settings);
      })
      .catch(() => {
        setDingtalkEnabled(false);
      });
  }, []);

  if (!loading && isAuthenticated) {
    return <Navigate to={from} replace />;
  }

  const onFinish = async (values: { email: string; password: string }) => {
    setSubmitting(true);
    setError(null);
    try {
      await login(values.email, values.password);
      navigate(from, { replace: true });
    } catch {
      setError(t("loginFailed"));
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
        background: "linear-gradient(135deg, #f5f7fa 0%, #e4ebf5 100%)",
        padding: 24,
      }}
    >
      <Card style={{ width: "100%", maxWidth: 420 }}>
        <Space direction="vertical" size="large" style={{ width: "100%" }}>
          <div>
            <Title level={3} style={{ marginBottom: 8 }}>
              {t("loginTitle")}
            </Title>
            <Text type="secondary">{t("loginSubtitle")}</Text>
          </div>

          {error && <Alert type="error" message={error} showIcon />}

          <Alert type="info" message={t("demoCredentials")} showIcon />

          <Form layout="vertical" onFinish={onFinish} requiredMark={false}>
            <Form.Item
              label={t("email")}
              name="email"
              rules={[
                { required: true, message: t("emailRequired") },
                { type: "email", message: t("emailInvalid") },
              ]}
            >
              <Input prefix={<MailOutlined />} placeholder="admin@demo.com" autoComplete="email" />
            </Form.Item>

            <Form.Item
              label={t("password")}
              name="password"
              rules={[{ required: true, message: t("passwordRequired") }]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="Admin123!" autoComplete="current-password" />
            </Form.Item>

            <Button type="primary" htmlType="submit" block loading={submitting}>
              {t("loginButton")}
            </Button>
          </Form>

          <Divider>{t("or")}</Divider>

          {dingtalkEnabled === false && dingtalkMissing.length > 0 && (
            <Alert
              type="warning"
              showIcon
              message={t("dingtalkNotConfigured")}
              description={dingtalkMissing.join(", ")}
            />
          )}

          <Button
            block
            icon={<DingdingOutlined />}
            disabled={dingtalkEnabled === false}
            loading={dingtalkEnabled === null}
            onClick={() => {
              window.location.href = getDingTalkLoginUrl();
            }}
          >
            {t("loginWithDingTalk")}
          </Button>

          <Text type="secondary">
            <Link to="/">{t("backToHome")}</Link>
          </Text>
        </Space>
      </Card>
    </div>
  );
}
