import { useEffect, useMemo, useState } from "react";
import { Checkbox, Col, Form, Modal, Row, Select, Typography, message } from "antd";
import { cloneMonth, MonthCloneCopyOptions } from "../api";
import { useLanguage } from "../i18n/LanguageContext";

const { Text } = Typography;

const YEARS = [2025, 2026, 2027, 2028];

interface CloneMonthModalProps {
  open: boolean;
  sourceYear: number;
  sourceMonth: number;
  onClose: () => void;
  onCloned: (targetYear: number, targetMonth: number) => void;
}

const DEFAULT_OPTIONS: MonthCloneCopyOptions = {
  copy_employees: true,
  keep_attendance_data: false,
  keep_formulas: true,
  keep_manual_notes: true,
  reset_anomalies: true,
};

export default function CloneMonthModal({
  open,
  sourceYear,
  sourceMonth,
  onClose,
  onCloned,
}: CloneMonthModalProps) {
  const { language, t } = useLanguage();
  const [saving, setSaving] = useState(false);
  const [targetYear, setTargetYear] = useState(sourceYear);
  const [targetMonth, setTargetMonth] = useState(sourceMonth === 12 ? 1 : sourceMonth + 1);
  const [options, setOptions] = useState<MonthCloneCopyOptions>(DEFAULT_OPTIONS);

  useEffect(() => {
    if (open) {
      setTargetYear(sourceYear);
      setTargetMonth(sourceMonth === 12 ? 1 : sourceMonth + 1);
      setOptions(DEFAULT_OPTIONS);
    }
  }, [open, sourceYear, sourceMonth]);

  const monthOptions = useMemo(
    () =>
      Array.from({ length: 12 }, (_, index) => ({
        value: index + 1,
        label: language === "zh" ? `${index + 1}月` : `Month ${index + 1}`,
      })),
    [language]
  );

  const yearOptions = useMemo(
    () => YEARS.map((value) => ({ value, label: String(value) })),
    []
  );

  const handleSubmit = async () => {
    if (sourceYear === targetYear && sourceMonth === targetMonth) {
      message.error(t("cloneMonthSamePeriod"));
      return;
    }

    setSaving(true);
    try {
      const result = await cloneMonth({
        source_year: sourceYear,
        source_month: sourceMonth,
        target_year: targetYear,
        target_month: targetMonth,
        copy_options: options,
      });
      message.success(
        t("cloneMonthSuccess", {
          count: result.employees_copied,
          year: result.target_year,
          month: result.target_month,
        })
      );
      onCloned(result.target_year, result.target_month);
      onClose();
    } catch (error: unknown) {
      const detail = (error as { response?: { data?: { detail?: string } } }).response?.data?.detail;
      message.error(typeof detail === "string" ? detail : t("cloneMonthFailed"));
    } finally {
      setSaving(false);
    }
  };

  const updateOption = (key: keyof MonthCloneCopyOptions, checked: boolean) => {
    setOptions((current) => ({ ...current, [key]: checked }));
  };

  return (
    <Modal
      title={t("cloneMonthTitle")}
      open={open}
      onCancel={onClose}
      onOk={handleSubmit}
      confirmLoading={saving}
      okText={t("cloneMonthConfirm")}
      cancelText={t("cancel")}
      width={560}
      destroyOnClose
    >
      <Form layout="vertical">
        <Text type="secondary" style={{ display: "block", marginBottom: 16 }}>
          {t("cloneMonthDescription", { year: sourceYear, month: sourceMonth })}
        </Text>

        <Row gutter={16}>
          <Col span={12}>
            <Form.Item label={t("cloneMonthTargetYear")}>
              <Select value={targetYear} onChange={setTargetYear} options={yearOptions} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item label={t("cloneMonthTargetMonth")}>
              <Select value={targetMonth} onChange={setTargetMonth} options={monthOptions} />
            </Form.Item>
          </Col>
        </Row>

        <Form.Item label={t("cloneMonthOptions")}>
          <Checkbox
            checked={options.copy_employees}
            onChange={(event) => updateOption("copy_employees", event.target.checked)}
          >
            {t("cloneOptionEmployees")}
          </Checkbox>
          <br />
          <Checkbox
            checked={options.keep_attendance_data}
            onChange={(event) => updateOption("keep_attendance_data", event.target.checked)}
            disabled={!options.copy_employees}
          >
            {t("cloneOptionAttendance")}
          </Checkbox>
          <br />
          <Checkbox
            checked={options.keep_formulas}
            onChange={(event) => updateOption("keep_formulas", event.target.checked)}
            disabled={!options.copy_employees || !options.keep_attendance_data}
          >
            {t("cloneOptionFormulas")}
          </Checkbox>
          <br />
          <Checkbox
            checked={options.keep_manual_notes}
            onChange={(event) => updateOption("keep_manual_notes", event.target.checked)}
            disabled={!options.copy_employees}
          >
            {t("cloneOptionNotes")}
          </Checkbox>
          <br />
          <Checkbox
            checked={options.reset_anomalies}
            onChange={(event) => updateOption("reset_anomalies", event.target.checked)}
            disabled={!options.copy_employees}
          >
            {t("cloneOptionAnomalies")}
          </Checkbox>
        </Form.Item>
      </Form>
    </Modal>
  );
}
