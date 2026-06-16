import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Empty,
  Input,
  List,
  Modal,
  Radio,
  Row,
  Space,
  Spin,
  Tag,
  Typography,
} from "antd";
import {
  batchResolveConflicts,
  ConflictItem,
  ConflictResolutionMethod,
  fetchConflicts,
  resolveConflict,
} from "../api";
import { useLanguage } from "../i18n/LanguageContext";
import type { TranslationKey } from "../i18n/translations";

const { Text, Title } = Typography;

type ResolutionChoice = "manual_priority" | "dingtalk_priority" | "manual";

interface ConflictResolutionModalProps {
  open: boolean;
  year: number;
  month: number;
  onClose: () => void;
  onResolved: () => void;
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

export default function ConflictResolutionModal({
  open,
  year,
  month,
  onClose,
  onResolved,
}: ConflictResolutionModalProps) {
  const { language, t } = useLanguage();
  const locale = language === "zh" ? "zh-CN" : "en-US";

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflicts, setConflicts] = useState<ConflictItem[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [choice, setChoice] = useState<ResolutionChoice>("manual_priority");
  const [customValue, setCustomValue] = useState("");
  const [applyToAll, setApplyToAll] = useState(false);

  const activeConflict = conflicts[activeIndex] ?? null;

  const loadConflicts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchConflicts(year, month);
      setConflicts(response.conflicts);
      setActiveIndex(0);
    } catch {
      setError(t("conflictLoadFailed"));
      setConflicts([]);
    } finally {
      setLoading(false);
    }
  }, [year, month, t]);

  useEffect(() => {
    if (open) {
      loadConflicts();
    }
  }, [open, loadConflicts]);

  useEffect(() => {
    if (!activeConflict) {
      setCustomValue("");
      return;
    }
    setChoice("manual_priority");
    setCustomValue(activeConflict.manual_value ?? "");
  }, [activeConflict?.id]);

  const remainingCount = Math.max(conflicts.length - activeIndex, 0);

  const resolutionMethod = useMemo((): ConflictResolutionMethod => {
    if (choice === "manual") {
      return "manual";
    }
    return choice;
  }, [choice]);

  const resolvedValue = useMemo(() => {
    if (!activeConflict) {
      return undefined;
    }
    if (choice === "manual") {
      return customValue;
    }
    return undefined;
  }, [activeConflict, choice, customValue]);

  const targetConflictIds = useMemo(() => {
    if (!activeConflict) {
      return [];
    }
    if (applyToAll) {
      return conflicts.slice(activeIndex).map((conflict) => conflict.id);
    }
    return [activeConflict.id];
  }, [activeConflict, applyToAll, conflicts, activeIndex]);

  const handleSave = async () => {
    if (!activeConflict || targetConflictIds.length === 0) {
      return;
    }
    if (choice === "manual" && !customValue.trim()) {
      setError(t("customValueRequired"));
      return;
    }

    setSaving(true);
    setError(null);
    try {
      if (targetConflictIds.length === 1) {
        await resolveConflict(targetConflictIds[0], {
          resolution_method: resolutionMethod,
          resolved_value: resolvedValue,
        });
      } else {
        await batchResolveConflicts({
          conflict_ids: targetConflictIds,
          resolution_method: resolutionMethod,
          resolved_value: resolvedValue,
        });
      }
      if (applyToAll || activeIndex >= conflicts.length - 1) {
        onResolved();
        onClose();
      } else {
        await loadConflicts();
        setActiveIndex(0);
      }
    } catch {
      setError(t("conflictResolveFailed"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={t("conflictModalTitle")}
      open={open}
      onCancel={onClose}
      width={900}
      footer={
        <Space>
          <Button onClick={onClose}>{t("cancel")}</Button>
          <Button
            type="primary"
            loading={saving}
            disabled={!activeConflict || loading}
            onClick={handleSave}
          >
            {t("conflictSave")}
          </Button>
        </Space>
      }
      destroyOnClose
    >
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}

      {loading ? (
        <div style={{ textAlign: "center", padding: 48 }}>
          <Spin size="large" />
        </div>
      ) : conflicts.length === 0 ? (
        <Empty description={t("noConflicts")} />
      ) : (
        <Row gutter={16}>
          <Col xs={24} md={8}>
            <List
              size="small"
              header={<Text strong>{t("conflictListHeader")}</Text>}
              dataSource={conflicts}
              renderItem={(item, index) => (
                <List.Item
                  style={{
                    cursor: "pointer",
                    background: index === activeIndex ? "#e6f4ff" : undefined,
                    borderRadius: 6,
                    paddingInline: 8,
                  }}
                  onClick={() => setActiveIndex(index)}
                >
                  <Space direction="vertical" size={0}>
                    <Text strong>{item.employee_name}</Text>
                    <Text type="secondary">{fieldLabel(item.field_name, t)}</Text>
                  </Space>
                </List.Item>
              )}
            />
          </Col>

          <Col xs={24} md={16}>
            {activeConflict && (
              <Space direction="vertical" size="middle" style={{ width: "100%" }}>
                <div>
                  <Title level={5} style={{ marginTop: 0 }}>
                    {activeConflict.employee_name}
                    <Tag style={{ marginLeft: 8 }}>{activeConflict.department}</Tag>
                  </Title>
                  <Text type="secondary">{fieldLabel(activeConflict.field_name, t)}</Text>
                </div>

                <Row gutter={16}>
                  <Col span={12}>
                    <Card
                      size="small"
                      title={t("conflictManualSide")}
                      styles={{ body: { minHeight: 120 } }}
                    >
                      <Text>{activeConflict.manual_value || "—"}</Text>
                      <div style={{ marginTop: 12 }}>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {t("conflictEditedAt")}: {formatTimestamp(activeConflict.manual_edit_at, locale)}
                        </Text>
                      </div>
                    </Card>
                  </Col>
                  <Col span={12}>
                    <Card
                      size="small"
                      title={t("conflictDingTalkSide")}
                      styles={{ body: { minHeight: 120 } }}
                    >
                      <Text>{activeConflict.dingtalk_value || "—"}</Text>
                      <div style={{ marginTop: 12 }}>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {t("conflictSyncedAt")}: {formatTimestamp(activeConflict.dingtalk_sync_at, locale)}
                        </Text>
                      </div>
                    </Card>
                  </Col>
                </Row>

                <Radio.Group
                  value={choice}
                  onChange={(event) => setChoice(event.target.value)}
                  style={{ width: "100%" }}
                >
                  <Space direction="vertical" style={{ width: "100%" }}>
                    <Radio value="manual_priority">{t("conflictKeepManual")}</Radio>
                    <Radio value="dingtalk_priority">{t("conflictUseDingTalk")}</Radio>
                    <Radio value="manual">{t("conflictCustomValue")}</Radio>
                  </Space>
                </Radio.Group>

                {choice === "manual" && (
                  <Input
                    value={customValue}
                    onChange={(event) => setCustomValue(event.target.value)}
                    placeholder={t("conflictCustomPlaceholder")}
                  />
                )}

                <Checkbox checked={applyToAll} onChange={(event) => setApplyToAll(event.target.checked)}>
                  {t("conflictApplyToAll", { count: remainingCount })}
                </Checkbox>
              </Space>
            )}
          </Col>
        </Row>
      )}
    </Modal>
  );
}
