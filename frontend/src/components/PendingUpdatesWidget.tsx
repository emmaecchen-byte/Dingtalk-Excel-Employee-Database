import { useCallback, useEffect, useState } from "react";
import { Badge, Button, Card, Empty, Modal, Skeleton, Space, Table, Typography, message } from "antd";
import { BellOutlined, ExclamationCircleOutlined, SyncOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import { PendingUpdateListItem, SyncStatusResponse, fetchSyncStatus, getApiErrorMessage } from "../api";
import { useLanguage } from "../i18n/LanguageContext";
import type { TranslationKey } from "../i18n/translations";

const { Text } = Typography;

const POLL_INTERVAL_MS = 30_000;

interface PendingUpdatesWidgetProps {
  onOpenConflicts: () => void;
  refreshToken?: number;
  onCountsChange?: (counts: { pendingUpdates: number; pendingConflicts: number }) => void;
}

function formatTimestamp(value?: string, locale = "zh-CN") {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString(locale);
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
  };
  const key = labels[fieldName];
  return key ? t(key) : fieldName;
}

export default function PendingUpdatesWidget({
  onOpenConflicts,
  refreshToken = 0,
  onCountsChange,
}: PendingUpdatesWidgetProps) {
  const { language, t } = useLanguage();
  const locale = language === "zh" ? "zh-CN" : "en-US";

  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<SyncStatusResponse | null>(null);
  const [updatesModalOpen, setUpdatesModalOpen] = useState(false);

  const loadStatus = useCallback(async () => {
    try {
      const response = await fetchSyncStatus();
      setStatus(response);
      onCountsChange?.({
        pendingUpdates: response.pending_updates_count,
        pendingConflicts: response.pending_conflicts_count,
      });
    } catch (error) {
      setStatus(null);
      message.error(getApiErrorMessage(error, t("loadSyncStatusFailed")));
    } finally {
      setLoading(false);
    }
  }, [onCountsChange, t]);

  useEffect(() => {
    loadStatus();
    const intervalId = window.setInterval(loadStatus, POLL_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
  }, [loadStatus, refreshToken]);

  const updateColumns: ColumnsType<PendingUpdateListItem> = [
    {
      title: t("name"),
      dataIndex: "employee_name",
      key: "employee_name",
      width: 140,
    },
    {
      title: t("pendingUpdatesField"),
      dataIndex: "field_name",
      key: "field_name",
      width: 160,
      render: (value: string) => fieldLabel(value, t),
    },
    {
      title: t("pendingUpdatesNewValue"),
      dataIndex: "new_value",
      key: "new_value",
      render: (value?: string) => value || "—",
    },
  ];

  if (loading && !status) {
    return (
      <Card style={{ marginBottom: 16 }}>
        <Skeleton active paragraph={{ rows: 1 }} />
      </Card>
    );
  }

  const pendingUpdates = status?.pending_updates_count ?? 0;
  const pendingConflicts = status?.pending_conflicts_count ?? 0;

  return (
    <>
      <Card style={{ marginBottom: 16 }}>
        <Space wrap size="middle" style={{ width: "100%", justifyContent: "space-between" }}>
          <Space wrap size="large">
            <Badge count={pendingUpdates} overflowCount={99} showZero={false}>
              <Button
                icon={<BellOutlined />}
                onClick={() => setUpdatesModalOpen(true)}
                disabled={pendingUpdates === 0}
              >
                {t("pendingUpdates")}
              </Button>
            </Badge>

            <Badge count={pendingConflicts} overflowCount={99} showZero={false}>
              <Button
                icon={<ExclamationCircleOutlined />}
                onClick={onOpenConflicts}
                disabled={pendingConflicts === 0}
              >
                {t("pendingConflicts")}
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

      <Modal
        title={t("pendingUpdatesListTitle")}
        open={updatesModalOpen}
        onCancel={() => setUpdatesModalOpen(false)}
        footer={null}
        width={720}
        destroyOnClose
      >
        {(status?.pending_updates_list.length ?? 0) === 0 ? (
          <Empty description={t("pendingUpdatesEmpty")} />
        ) : (
          <Table
            rowKey={(record, index) => `${record.employee_name}-${record.field_name}-${index}`}
            size="small"
            columns={updateColumns}
            dataSource={status?.pending_updates_list ?? []}
            pagination={{ pageSize: 8 }}
          />
        )}
      </Modal>
    </>
  );
}
