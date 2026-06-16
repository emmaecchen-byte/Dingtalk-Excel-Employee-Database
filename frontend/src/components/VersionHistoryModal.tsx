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
import { ArrowRightOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import {
  VersionCompareResponse,
  VersionListItem,
  VersionRollbackPreviewResponse,
  compareVersions,
  fetchVersionHistory,
  getApiErrorMessage,
  previewVersionRollback,
  rollbackVersion,
} from "../api";
import { useLanguage } from "../i18n/LanguageContext";
import type { TranslationKey } from "../i18n/translations";

const { Text } = Typography;

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
    total_attendance_days: "fieldAttendanceDays",
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

function ValueChange({
  oldValue,
  newValue,
}: {
  oldValue: string;
  newValue: string;
}) {
  return (
    <Space size="small" wrap>
      <Text type="secondary" delete={Boolean(oldValue)}>
        {oldValue || "—"}
      </Text>
      <ArrowRightOutlined style={{ color: "#1677ff", fontSize: 12 }} />
      <Text strong={Boolean(newValue)}>{newValue || "—"}</Text>
    </Space>
  );
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
  const [rollbackPreview, setRollbackPreview] = useState<VersionRollbackPreviewResponse | null>(
    null
  );
  const [previewLoading, setPreviewLoading] = useState(false);

  const selectedVersions = useMemo(
    () => versions.filter((version) => selectedRowKeys.includes(versionRowKey(version))),
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
    } catch (err) {
      setError(getApiErrorMessage(err, t("versionLoadFailed")));
      setVersions([]);
    } finally {
      setLoading(false);
    }
  }, [year, month, t]);

  useEffect(() => {
    if (open) {
      void loadVersions();
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
    } catch (err) {
      setError(getApiErrorMessage(err, t("versionCompareFailed")));
      setDiff(null);
    } finally {
      setComparing(false);
    }
  };

  const handleRestoreClick = async (record: VersionListItem) => {
    if (record.id <= 0) {
      message.error(t("versionRestoreFailed"));
      return;
    }
    setRestoreTarget(record);
    setRollbackPreview(null);
    setPreviewLoading(true);
    try {
      const preview = await previewVersionRollback(record.id);
      setRollbackPreview(preview);
    } catch (err) {
      message.error(getApiErrorMessage(err, t("versionRestoreFailed")));
      setRestoreTarget(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleRestoreConfirm = async () => {
    if (!restoreTarget || restoreTarget.id <= 0) {
      return;
    }

    setRestoring(true);
    try {
      const result = await rollbackVersion(restoreTarget.id, {
        confirmDataLoss: true,
        confirmDingtalkOverwrite: true,
      });
      const successText =
        result.conflicts_created > 0
          ? t("versionRestoreSuccessWithConflicts", { count: result.conflicts_created })
          : t("versionRestoreSuccess");
      message.success(successText);
      setRestoreTarget(null);
      setRollbackPreview(null);
      await loadVersions();
      onRestored?.();
    } catch (err) {
      message.error(getApiErrorMessage(err, t("versionRestoreFailed")));
    } finally {
      setRestoring(false);
    }
  };

  const columns: ColumnsType<VersionListItem> = [
    {
      title: t("versionNumber"),
      dataIndex: "version_number",
      key: "version_number",
      width: 100,
      render: (value: number) => <Tag color="blue">v{value}</Tag>,
    },
    {
      title: t("versionDate"),
      dataIndex: "created_at",
      key: "created_at",
      width: 170,
      render: (value?: string) => formatTimestamp(value, locale),
    },
    {
      title: t("versionCreatedBy"),
      dataIndex: "created_by",
      key: "created_by",
      width: 120,
      ellipsis: true,
    },
    {
      title: t("versionSummary"),
      dataIndex: "summary",
      key: "summary",
      ellipsis: true,
    },
    {
      title: t("versionActions"),
      key: "actions",
      width: 110,
      render: (_, record) =>
        record.can_restore && record.id > 0 ? (
          <Button size="small" onClick={() => void handleRestoreClick(record)}>
            {t("versionRestore")}
          </Button>
        ) : (
          <Text type="secondary">—</Text>
        ),
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
      title: t("versionChange"),
      key: "change",
      render: (_, record) => (
        <ValueChange
          oldValue={record.value_in_snapshot_1}
          newValue={record.value_in_snapshot_2}
        />
      ),
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

        <Space style={{ marginBottom: 16 }} wrap>
          <Button
            type="primary"
            disabled={selectedVersions.length !== 2}
            loading={comparing}
            onClick={() => void handleCompare()}
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
          <Skeleton active paragraph={{ rows: 8 }} title={{ width: "40%" }} />
        ) : versions.length === 0 ? (
          <Empty description={t("versionNoData")} />
        ) : (
          <Table
            rowKey={(record) => versionRowKey(record)}
            size="small"
            columns={columns}
            dataSource={versions}
            pagination={{ pageSize: 8, showSizeChanger: true, pageSizeOptions: [8, 15, 30] }}
            rowSelection={{
              selectedRowKeys,
              onChange: (keys) => setSelectedRowKeys(keys as string[]),
              getCheckboxProps: (record) => ({
                disabled:
                  !record.snapshot_id ||
                  (selectedRowKeys.length >= 2 &&
                    !selectedRowKeys.includes(versionRowKey(record))),
              }),
            }}
          />
        )}

        {comparing && (
          <div style={{ marginTop: 24 }}>
            <Skeleton active paragraph={{ rows: 6 }} title={{ width: "30%" }} />
          </div>
        )}

        {diff && !comparing && (
          <div style={{ marginTop: 24 }}>
            <Text strong style={{ display: "block", marginBottom: 12 }}>
              {t("versionDiffTitle")}
              {selectedVersions.length === 2 && (
                <Text type="secondary" style={{ marginLeft: 8, fontWeight: 400 }}>
                  (v{selectedVersions[0].version_number} → v{selectedVersions[1].version_number})
                </Text>
              )}
            </Text>

            {(diff.added_employees.length > 0 || diff.removed_employees.length > 0) && (
              <Space direction="vertical" style={{ width: "100%", marginBottom: 16 }}>
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
                    description={diff.removed_employees
                      .map((item) => item.employee_name)
                      .join(", ")}
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
                pagination={{ pageSize: 8, showSizeChanger: true }}
              />
            ) : (
              <Alert type="info" message={t("versionNoFieldChanges")} />
            )}
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
        onOk={() => void handleRestoreConfirm()}
        confirmLoading={restoring}
        okText={t("confirm")}
        cancelText={t("cancel")}
        okButtonProps={{ danger: Boolean(rollbackPreview?.requires_dingtalk_confirmation) }}
      >
        {previewLoading ? (
          <Skeleton active paragraph={{ rows: 3 }} />
        ) : (
          <>
            <Text>
              {t("versionRestoreConfirm", { version: restoreTarget?.version_number ?? "" })}
            </Text>
            {rollbackPreview && rollbackPreview.fields_would_change > 0 && (
              <Alert
                type="warning"
                showIcon
                style={{ marginTop: 16 }}
                message={t("versionRollbackImpact", {
                  fields: rollbackPreview.fields_would_change,
                  employees: rollbackPreview.employees_affected,
                })}
              />
            )}
            {rollbackPreview && rollbackPreview.dingtalk_overwrite_warnings.length > 0 && (
              <Alert
                type="error"
                showIcon
                style={{ marginTop: 16 }}
                message={t("versionRollbackDingtalkWarning", {
                  count: rollbackPreview.dingtalk_overwrite_warnings.length,
                })}
                description={
                  <ul style={{ margin: "8px 0 0", paddingLeft: 20 }}>
                    {rollbackPreview.dingtalk_overwrite_warnings.slice(0, 5).map((warning) => (
                      <li key={`${warning.employee_id}-${warning.field_name}`}>
                        {warning.employee_name} / {fieldLabel(warning.field_name, t)}:{" "}
                        <ValueChange
                          oldValue={warning.current_value}
                          newValue={warning.rollback_value}
                        />
                      </li>
                    ))}
                    {rollbackPreview.dingtalk_overwrite_warnings.length > 5 && (
                      <li>
                        {t("versionRollbackMoreWarnings", {
                          count: rollbackPreview.dingtalk_overwrite_warnings.length - 5,
                        })}
                      </li>
                    )}
                  </ul>
                }
              />
            )}
          </>
        )}
      </Modal>
    </>
  );
}
