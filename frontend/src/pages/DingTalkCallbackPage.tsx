import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Alert, Card, Spin, Typography } from "antd";
import { useAuth } from "../auth/AuthContext";
import { useLanguage } from "../i18n/LanguageContext";

const { Title, Text } = Typography;

export default function DingTalkCallbackPage() {
  const { loginWithTokens } = useAuth();
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const oauthError = searchParams.get("error");
    const oauthMessage = searchParams.get("message");
    const accessToken = searchParams.get("access_token");
    const refreshToken = searchParams.get("refresh_token");

    if (oauthError) {
      setError(oauthMessage || t("dingtalkLoginFailed"));
      return;
    }

    if (!accessToken || !refreshToken) {
      setError(t("dingtalkLoginFailed"));
      return;
    }

    loginWithTokens(accessToken, refreshToken)
      .then(() => navigate("/", { replace: true }))
      .catch(() => setError(t("dingtalkLoginFailed")));
  }, [loginWithTokens, navigate, searchParams, t]);

  if (error) {
    return (
      <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 24 }}>
        <Card style={{ width: "100%", maxWidth: 420 }}>
          <Title level={4}>{t("dingtalkLoginFailed")}</Title>
          <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />
          <Text>
            <a href="/login">{t("backToLogin")}</a>
          </Text>
        </Card>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center" }}>
      <Card style={{ width: 320, textAlign: "center" }}>
        <Spin size="large" />
        <Title level={5} style={{ marginTop: 16 }}>
          {t("dingtalkSigningIn")}
        </Title>
      </Card>
    </div>
  );
}
