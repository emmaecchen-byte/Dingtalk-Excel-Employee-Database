import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Empty,
  Modal,
  Skeleton,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import ReactDiffViewer from "react-diff-viewer-continued";
import {
  VersionCompareResponse,
  VersionListItem,
  VersionRollbackPreviewResponse,
  compareVersions,
  fetchVersionHistory,
  previewVersionRollback,
  rollbackVersion,
} from "../api";
import { useLanguage } from "../i18n/LanguageContext";
import type { TranslationKey } from "../i18n/translations";

const { Text, Title } = Typography;

interface VersionHistoryModalProps {
  open: boolean;
  year: number;
  month: number;
  onClose: () => void;
  onRestored?: () => void;
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

function versionRowKey(version: VersionListItem): string {
  return version.id > 0 ? `v-${version.id}` : `s-${version.snapshot_id}`;
}

function resolveComparePayload(left: VersionListItem, right: VersionListItem) {
  return {
    version_id_1: left.id > 0 ? left.id : undefined,
    version_id_2: right.id > 0 ? right.id : undefined,
    snapshot_id_1: left.snapshot_id,
    snapshot_id_2: right.snapshot_id,
  };
}

export default function VersionHistoryModal({
  open,
  year,
  month,
  onClose,
  onRestored,
}: VersionHistoryModalProps) {
  const { language, t } = useLanguage();
  const locale = language === "zh" ? "zh-CN" : "en-US";

  const [loading, setLoading] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [versions, setVersions] = useState<VersionListItem[]>([]);
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([]);
  const [diff, setDiff] = useState<VersionCompareResponse | null>(null);
  const [restoreTarget, setRestoreTarget] = useState<VersionListItem | null>(null);
  const [rollbackPreview, setRollbackPreview] = useState<VersionRollbackPreviewResponse | null>(null);

  const selectedVersions = useMemo(
    () =>
      versions.filter((version) => selectedRowKeys.includes(versionRowKey(version))),
    [versions, selectedRowKeys]
  );

  const loadVersions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchVersionHistory(year, month);
      setVersions(response.versions);
      setSelectedRowKeys([]);
      setDiff(null);
    } catch {
      setError(t("versionLoadFailed"));
      setVersions([]);
    } finally {
      setLoading(false);
    }
  }, [year, month, t]);

  useEffect(() => {
    if (open) {
      loadVersions();
    }
  }, [open, loadVersions]);

  const handleCompare = async () => {
    if (selectedVersions.length !== 2) {
      return;
    }

    const [left, right] = selectedVersions;
    if (!left.snapshot_id || !right.snapshot_id) {
      setError(t("versionCompareFailed"));
      return;
    }

    setComparing(true);
    setError(null);
    try {
      const result = await compareVersions(resolveComparePayload(left, right));
      setDiff(result);
    } catch {
      setError(t("versionCompareFailed"));
      setDiff(null);
    } finally {
      setComparing(false);
    }
  };

  const handleRestoreClick = async (record: VersionListItem) => {
    if (record.id <= 0) {
      setError(t("versionRestoreFailed"));
      return;
    }
    setRestoreTarget(record);
    setRollbackPreview(null);
    try {
      const preview = await previewVersionRollback(record.id);
      setRollbackPreview(preview);
    } catch {
      setRollbackPreview(null);
    }
  };

  const handleRestoreConfirm = async () => {
    if (!restoreTarget || restoreTarget.id <= 0) {
      return;
    }

    setRestoring(true);
    try {
      await rollbackVersion(restoreTarget.id, true);
      message.success(t("versionRestoreSuccess"));
      setRestoreTarget(null);
      setRollbackPreview(null);
      await loadVersions();
      onRestored?.();
    } catch (error: unknown) {
      const response = (error as { response?: { status?: number; data?: { detail?: VersionRollbackPreviewResponse } } })
        .response;
      if (response?.status === 409 && response.data?.detail) {
        setRollbackPreview(response.data.detail as VersionRollbackPreviewResponse);
        setError(t("versionRestoreConfirm", { version: restoreTarget.version_number }));
      } else {
        message.error(t("versionRestoreFailed"));
      }
    } finally {
      setRestoring(false);
    }
  };

  const columns: ColumnsType<VersionListItem> = [
    {
      title: t("versionNumber"),
      dataIndex: "version_number",
      key: "version_number",
      width: 90,
      render: (value: number) => <Tag color="blue">v{value}</Tag>,
    },
    {
      title: t("versionDate"),
      dataIndex: "created_at",
      key: "created_at",
      width: 180,
      render: (value?: string) => formatTimestamp(value, locale),
    },
    {
      title: t("versionCreatedBy"),
      dataIndex: "created_by",
      key: "created_by",
      width: 120,
    },
    {
      title: t("versionSummary"),
      dataIndex: "summary",
      key: "summary",
      ellipsis: true,
    },
    {
      title: "",
      key: "actions",
      width: 120,
      render: (_, record) =>
        record.can_restore && record.id > 0 ? (
          <Button size="small" onClick={() => handleRestoreClick(record)}>
            {t("versionRestore")}
          </Button>
        ) : null,
    },
  ];

  const diffColumns: ColumnsType<VersionCompareResponse["changed_fields"][number]> = [
    {
      title: t("versionEmployee"),
      dataIndex: "employee_name",
      key: "employee_name",
      width: 120,
    },
    {
      title: t("versionField"),
      dataIndex: "field_name",
      key: "field_name",
      width: 140,
      render: (value: string) => fieldLabel(value, t),
    },
    {
      title: t("versionOldValue"),
      dataIndex: "value_in_snapshot_1",
      key: "value_in_snapshot_1",
      render: (value: string) => <Text type="secondary">{value || "—"}</Text>,
    },
    {
      title: t("versionNewValue"),
      dataIndex: "value_in_snapshot_2",
      key: "value_in_snapshot_2",
      render: (value: string) => <Text>{value || "—"}</Text>,
    },
  ];

  return (
    <>
      <Modal
        title={t("versionHistoryTitle")}
        open={open}
        onCancel={onClose}
        width={1100}
        footer={null}
        destroyOnClose
      >
        {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}

        <Space style={{ marginBottom: 16 }}>
          <Button
            type="primary"
            disabled={selectedVersions.length !== 2}
            loading={comparing}
            onClick={handleCompare}
          >
            {t("versionCompare")}
          </Button>
          <Text type="secondary">
            {selectedVersions.length === 2
              ? `v${selectedVersions[0].version_number} ↔ v${selectedVersions[1].version_number}`
              : t("versionSelectTwo")}
          </Text>
        </Space>

        {loading ? (
          <Skeleton active paragraph={{ rows: 6 }} />
        ) : versions.length === 0 ? (
          <Empty description={t("versionNoData")} />
        ) : (
          <Table
            rowKey={(record) => versionRowKey(record)}
            size="small"
            columns={columns}
            dataSource={versions}
            pagination={{ pageSize: 8 }}
            rowSelection={{
              selectedRowKeys,
              onChange: (keys) => setSelectedRowKeys(keys as string[]),
              getCheckboxProps: (record) => ({
                disabled:
                  selectedRowKeys.length >= 2 &&
                  !selectedRowKeys.includes(versionRowKey(record)),
              }),
            }}
          />
        )}

        {comparing && <Skeleton active paragraph={{ rows: 4 }} style={{ marginTop: 24 }} />}

        {diff && !comparing && (
          <div style={{ marginTop: 24 }}>
            <Title level={5}>{t("versionDiffTitle")}</Title>

            {(diff.added_employees.length > 0 || diff.removed_employees.length > 0) && (
              <Space wrap style={{ marginBottom: 16 }}>
                {diff.added_employees.length > 0 && (
                  <Alert
                    type="success"
                    showIcon
                    message={t("versionAddedEmployees")}
                    description={diff.added_employees.map((item) => item.employee_name).join(", ")}
                  />
                )}
                {diff.removed_employees.length > 0 && (
                  <Alert
                    type="warning"
                    showIcon
                    message={t("versionRemovedEmployees")}
                    description={diff.removed_employees.map((item) => item.employee_name).join(", ")}
                  />
                )}
              </Space>
            )}

            {diff.changed_fields.length > 0 ? (
              <Table
                rowKey={(record) => `${record.employee_id}-${record.field_name}`}
                size="small"
                columns={diffColumns}
                dataSource={diff.changed_fields}
                pagination={{ pageSize: 6 }}
                style={{ marginBottom: 16 }}
              />
            ) : (
              <Alert type="info" message={t("versionNoData")} style={{ marginBottom: 16 }} />
            )}

            <Title level={5} style={{ marginTop: 8 }}>
              {t("versionDiffViewer")}
            </Title>
            <div style={{ maxHeight: 320, overflow: "auto", border: "1px solid #f0f0f0", borderRadius: 8 }}>
              <ReactDiffViewer
                oldValue={diff.diff_text_old}
                newValue={diff.diff_text_new}
                splitView
                useDarkTheme={false}
                leftTitle={`v${selectedVersions[0]?.version_number ?? ""}`}
                rightTitle={`v${selectedVersions[1]?.version_number ?? ""}`}
              />
            </div>
          </div>
        )}
      </Modal>

      <Modal
        title={t("versionRestoreTitle")}
        open={restoreTarget !== null}
        onCancel={() => {
          setRestoreTarget(null);
          setRollbackPreview(null);
        }}
        onOk={handleRestoreConfirm}
        confirmLoading={restoring}
        okText={t("confirm")}
        cancelText={t("cancel")}
      >
        <Text>
          {t("versionRestoreConfirm", { version: restoreTarget?.version_number ?? "" })}
        </Text>
        {rollbackPreview && rollbackPreview.fields_would_change > 0 && (
          <Alert
            type="warning"
            showIcon
            style={{ marginTop: 16 }}
            message={`${rollbackPreview.fields_would_change} field(s) across ${rollbackPreview.employees_affected} employee(s) will change`}
          />
        )}
      </Modal>
    </>
  );
}
