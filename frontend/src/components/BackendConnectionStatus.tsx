import { useQuery } from "@tanstack/react-query";
import { Tag, Tooltip } from "antd";
import { fetchHealth, getConnectionErrorMessage } from "../auth/api";
import { API_BASE_URL } from "../config/apiBase";
import { useLanguage } from "../i18n/LanguageContext";

export default function BackendConnectionStatus() {
  const { t } = useLanguage();
  const { data, isError, error, isFetching } = useQuery({
    queryKey: ["backend-health", API_BASE_URL],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
    retry: 1,
  });

  const connected = Boolean(data?.status === "ok");
  const errorMessage = isError ? getConnectionErrorMessage(error) : null;

  return (
    <Tooltip
      title={
        connected
          ? `${t("backendConnected")} (${API_BASE_URL})`
          : errorMessage || t("backendDisconnected")
      }
    >
      <Tag
        color={connected ? "success" : "error"}
        style={{
          position: "fixed",
          right: 12,
          bottom: 12,
          zIndex: 1000,
          margin: 0,
          cursor: "default",
        }}
      >
        {isFetching && !data ? t("backendChecking") : connected ? t("backendConnected") : t("backendDisconnected")}
      </Tag>
    </Tooltip>
  );
}
