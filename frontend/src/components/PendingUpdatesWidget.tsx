import { useEffect, useState } from "react";
import { Badge, Button, Card, Dropdown, Empty, List, Skeleton, Space, Typography } from "antd";
import { BellOutlined, ExclamationCircleOutlined, SyncOutlined } from "@ant-design/icons";
import type { PendingUpdateListItem } from "../api";
import { useSyncStatusQuery } from "../hooks/useSyncStatus";
import { useLanguage } from "../i18n/LanguageContext";
import type { TranslationKey } from "../i18n/translations";

const { Text } = Typography;

interface PendingUpdatesWidgetProps {
  onOpenConflicts: () => void;
  refreshToken?: number;
}

function formatTimestamp(value?: string, locale = "zh-CN") {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString(locale, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fieldLabel(
  fieldName: string,
  t: (key: TranslationKey, vars?: Record<string, string | number>) => string
): string {
  if (fieldName.startsWith("day_")) {
    const day = fieldName.replace("day_", "");
    return t("fieldDay", { day });
  }
  const labels: Record<string, TranslationKey> = {
    notes: "fieldNotes",
    anomaly_summary: "fieldAnomalySummary",
    supplement_submitted: "fieldSupplementSubmitted",
    total_overtime_hours: "fieldOvertimeHours",
    absenteeism_count: "fieldAbsenteeismCount",
    lateness_count: "fieldLatenessCount",
    missing_punch_count: "fieldMissingPunchCount",
  };
  const key = labels[fieldName];
  return key ? t(key) : fieldName;
}

export default function PendingUpdatesWidget({
  onOpenConflicts,
  refreshToken = 0,
}: PendingUpdatesWidgetProps) {
  const { language, t } = useLanguage();
  const locale = language === "zh" ? "zh-CN" : "en-US";
  const { data: status, isLoading, refetch } = useSyncStatusQuery(true);
  const [updatesOpen, setUpdatesOpen] = useState(false);

  useEffect(() => {
    if (refreshToken > 0) {
      void refetch();
    }
  }, [refreshToken, refetch]);

  const pendingUpdates = status?.pending_updates_count ?? 0;
  const pendingConflicts = status?.pending_conflicts_count ?? 0;

  const updatesDropdown = (
    <Card
      size="small"
      title={t("pendingUpdatesListTitle")}
      style={{ width: 360, maxHeight: 360, overflow: "auto", boxShadow: "0 6px 16px rgba(0,0,0,0.12)" }}
    >
      {(status?.pending_updates_list.length ?? 0) === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("pendingUpdatesEmpty")} />
      ) : (
        <List
          size="small"
          dataSource={status?.pending_updates_list ?? []}
          renderItem={(item: PendingUpdateListItem) => (
            <List.Item>
              <List.Item.Meta
                title={item.employee_name}
                description={
                  <Space direction="vertical" size={0}>
                    <Text type="secondary">{fieldLabel(item.field_name, t)}</Text>
                    <Text>
                      {t("pendingUpdatesNewValue")}: {item.new_value || "—"}
                    </Text>
                  </Space>
                }
              />
            </List.Item>
          )}
        />
      )}
    </Card>
  );

  if (isLoading && !status) {
    return (
      <Card style={{ marginBottom: 16 }}>
        <Skeleton active paragraph={{ rows: 1 }} />
      </Card>
    );
  }

  return (
    <Card style={{ marginBottom: 16 }}>
      <Space wrap size="middle" style={{ width: "100%", justifyContent: "space-between" }}>
        <Space wrap size="large">
          <Dropdown
            open={updatesOpen}
            onOpenChange={setUpdatesOpen}
            dropdownRender={() => updatesDropdown}
            trigger={["click"]}
            disabled={pendingUpdates === 0}
          >
            <Badge count={pendingUpdates} overflowCount={99} showZero={false}>
              <Button icon={<BellOutlined />} disabled={pendingUpdates === 0}>
                🔔 {t("pendingUpdates")}
              </Button>
            </Badge>
          </Dropdown>

          <Badge
            count={pendingConflicts}
            overflowCount={99}
            showZero={false}
            color={pendingConflicts > 0 ? "red" : undefined}
          >
            <Button
              icon={<ExclamationCircleOutlined />}
              danger={pendingConflicts > 0}
              onClick={onOpenConflicts}
              disabled={pendingConflicts === 0}
            >
              ⚠ {t("pendingConflicts")}
            </Button>
          </Badge>
        </Space>

        <Space>
          <SyncOutlined style={{ color: "#1677ff" }} />
          <Text type="secondary">
            {t("lastSync")}: {formatTimestamp(status?.last_sync_timestamp, locale)}
          </Text>
        </Space>
      </Space>
    </Card>
  );
}
