import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CheckCircleOutlined, ExclamationCircleOutlined } from "@ant-design/icons";
import { Input, InputNumber, Select, Table, Tag, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  EmployeeSummary,
  MonthlyAttendanceResponse,
  getApiErrorMessage,
  patchAttendance,
} from "../api";
import { useLanguage } from "../i18n/LanguageContext";
import type { TranslationKey } from "../i18n/translations";

type EditableField =
  | "total_attendance_days"
  | "absenteeism_count"
  | "lateness_count"
  | "missing_punch_count"
  | "supplement_submitted"
  | "notes";

const MANUAL_EDIT_STYLE: React.CSSProperties = {
  backgroundColor: "#fffbe6",
};

const CONFLICT_STYLE: React.CSSProperties = {
  backgroundColor: "#ffe7ba",
  border: "1px solid #fa8c16",
};

interface EmployeeTableProps {
  year: number;
  month: number;
  loading: boolean;
  data: MonthlyAttendanceResponse | null;
  employees: EmployeeSummary[];
  editable: boolean;
  page: number;
  pageSize: number;
  onPageChange: (page: number, pageSize: number) => void;
  onDataChange: (data: MonthlyAttendanceResponse) => void;
  onConflictDetected?: () => void;
}

interface EditingCell {
  employeeId: number;
  field: EditableField;
}

function cellKey(employeeId: number, field: EditableField): string {
  return `${employeeId}-${field}`;
}

function getFieldValue(employee: EmployeeSummary, field: EditableField): string {
  if (field === "notes") {
    return employee.notes ?? "";
  }
  if (field === "supplement_submitted") {
    return employee.supplement_submitted ? "true" : "false";
  }
  return String(employee[field]);
}

function formatDisplayValue(
  employee: EmployeeSummary,
  field: EditableField,
  t: (key: TranslationKey) => string
): string {
  if (field === "notes") {
    return employee.notes ?? "";
  }
  if (field === "supplement_submitted") {
    return employee.supplement_submitted ? t("yes") : t("no");
  }
  return String(employee[field]);
}

interface EditableCellProps {
  employee: EmployeeSummary;
  field: EditableField;
  editable: boolean;
  isEditing: boolean;
  isManual: boolean;
  isConflict: boolean;
  saving: boolean;
  onStartEdit: () => void;
  onSave: (value: string) => void;
  onCancel: () => void;
}

function EditableCell({
  employee,
  field,
  editable,
  isEditing,
  isManual,
  isConflict,
  saving,
  onStartEdit,
  onSave,
  onCancel,
}: EditableCellProps) {
  const { t } = useLanguage();
  const initial = getFieldValue(employee, field);
  const display = formatDisplayValue(employee, field, t);
  const [draft, setDraft] = useState<string>(initial);
  const committedRef = useRef(false);

  useEffect(() => {
    if (isEditing) {
      setDraft(initial);
      committedRef.current = false;
    }
  }, [isEditing, initial]);

  const cellStyle: React.CSSProperties = {
    minHeight: 32,
    padding: "4px 8px",
    cursor: editable ? "pointer" : "default",
    borderRadius: 4,
    ...(isConflict ? CONFLICT_STYLE : isManual ? MANUAL_EDIT_STYLE : {}),
  };

  if (!editable) {
    return <div style={cellStyle}>{display || "—"}</div>;
  }

  if (!isEditing) {
    return (
      <div style={cellStyle} onDoubleClick={onStartEdit} title={t("attendanceEditHint")}>
        {display === "" ? "—" : display}
      </div>
    );
  }

  const commit = (value?: string) => {
    if (committedRef.current) {
      return;
    }
    committedRef.current = true;
    onSave(value ?? draft);
  };

  if (field === "supplement_submitted") {
    return (
      <Select
        size="small"
        autoFocus
        defaultOpen
        disabled={saving}
        style={{ width: "100%" }}
        value={draft}
        options={[
          { value: "true", label: t("yes") },
          { value: "false", label: t("no") },
        ]}
        onChange={(value) => {
          setDraft(value);
          commit(value);
        }}
        onBlur={() => onCancel()}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            onCancel();
          }
        }}
      />
    );
  }

  if (field === "notes") {
    return (
      <Input
        size="small"
        autoFocus
        value={draft}
        disabled={saving}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => commit()}
        onPressEnter={() => commit()}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            onCancel();
          }
        }}
      />
    );
  }

  return (
    <InputNumber
      size="small"
      autoFocus
      min={0}
      value={Number(draft) || 0}
      disabled={saving}
      style={{ width: "100%" }}
      onChange={(value) => setDraft(String(value ?? 0))}
      onBlur={() => commit()}
      onPressEnter={() => commit()}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          onCancel();
        }
      }}
    />
  );
}

export default function EmployeeTable({
  year,
  month,
  loading,
  data,
  employees,
  editable,
  page,
  pageSize,
  onPageChange,
  onDataChange,
  onConflictDetected,
}: EmployeeTableProps) {
  const { t } = useLanguage();
  const [editingCell, setEditingCell] = useState<EditingCell | null>(null);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [conflictCells, setConflictCells] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    setConflictCells(new Set());
    setEditingCell(null);
  }, [year, month]);

  const fieldTitle = useCallback((key: TranslationKey) => t(key), [t]);

  const updateEmployee = useCallback(
    (employeeId: number, updater: (employee: EmployeeSummary) => EmployeeSummary) => {
      if (!data) {
        return;
      }
      const nextEmployees = data.employees.map((employee) =>
        employee.id === employeeId ? updater(employee) : employee
      );
      onDataChange({ ...data, employees: nextEmployees });
    },
    [data, onDataChange]
  );

  const applyOptimisticUpdate = useCallback(
    (employee: EmployeeSummary, field: EditableField, normalized: string) => {
      updateEmployee(employee.id, (current) => {
        const next = { ...current };
        if (field === "notes") {
          next.notes = normalized;
        } else if (field === "supplement_submitted") {
          next.supplement_submitted = normalized === "true";
        } else {
          next[field] = Number(normalized);
        }
        const overrides = new Set(next.manual_override_fields ?? []);
        overrides.add(field);
        next.manual_override_fields = Array.from(overrides);
        return next;
      });
    },
    [updateEmployee]
  );

  const handleSave = useCallback(
    async (employee: EmployeeSummary, field: EditableField, rawValue: string) => {
      if (!data) {
        return;
      }

      const previousValue = getFieldValue(employee, field);
      const normalized =
        field === "notes"
          ? rawValue.trim()
          : field === "supplement_submitted"
            ? rawValue === "true"
              ? "true"
              : "false"
            : String(Number(rawValue) || 0);

      if (previousValue === normalized) {
        setEditingCell(null);
        return;
      }

      const saveKey = cellKey(employee.id, field);
      setSavingKey(saveKey);

      const snapshot = structuredClone(data);
      applyOptimisticUpdate(employee, field, normalized);

      try {
        const result = await patchAttendance(year, month, employee.id, {
          field_name: field,
          new_value: normalized,
        });

        if (result.conflict_detected) {
          onDataChange(snapshot);
          setConflictCells((current) => {
            const next = new Set(current);
            next.add(saveKey);
            return next;
          });
          message.warning(t("attendanceEditConflict"));
          onConflictDetected?.();
        } else {
          setConflictCells((current) => {
            if (!current.has(saveKey)) {
              return current;
            }
            const next = new Set(current);
            next.delete(saveKey);
            return next;
          });
          updateEmployee(employee.id, (current) => {
            const next = { ...current };
            if (field === "notes") {
              next.notes = result.new_value ?? normalized;
            } else if (field === "supplement_submitted") {
              next.supplement_submitted = (result.new_value ?? normalized) === "true";
            } else {
              next[field] = Number(result.new_value ?? normalized);
            }
            next.manual_override_fields = result.manual_override_fields;
            return next;
          });
          message.success(t("attendanceEditSaved"));
        }
      } catch (err) {
        onDataChange(snapshot);
        message.error(getApiErrorMessage(err, t("attendanceEditFailed")));
      } finally {
        setSavingKey(null);
        setEditingCell(null);
      }
    },
    [
      applyOptimisticUpdate,
      data,
      month,
      onConflictDetected,
      onDataChange,
      t,
      updateEmployee,
      year,
    ]
  );

  const renderEditable = useCallback(
    (field: EditableField) =>
      (_: unknown, record: EmployeeSummary) => {
        const key = cellKey(record.id, field);
        const isEditing =
          editingCell?.employeeId === record.id && editingCell.field === field;
        const isManual = (record.manual_override_fields ?? []).includes(field);
        const isConflict = conflictCells.has(key);
        const saving = savingKey === key;

        return (
          <EditableCell
            employee={record}
            field={field}
            editable={editable}
            isEditing={isEditing}
            isManual={isManual}
            isConflict={isConflict}
            saving={saving}
            onStartEdit={() => setEditingCell({ employeeId: record.id, field })}
            onCancel={() => setEditingCell(null)}
            onSave={(value) => void handleSave(record, field, value)}
          />
        );
      },
    [conflictCells, editable, editingCell, handleSave, savingKey]
  );

  const columns: ColumnsType<EmployeeSummary> = useMemo(
    () => [
      { title: fieldTitle("name"), dataIndex: "name", key: "name" },
      { title: fieldTitle("department"), dataIndex: "department", key: "department" },
      {
        title: fieldTitle("attendanceDays"),
        dataIndex: "total_attendance_days",
        key: "attendance",
        align: "center",
        render: renderEditable("total_attendance_days"),
      },
      {
        title: fieldTitle("absenteeism"),
        dataIndex: "absenteeism_count",
        key: "absenteeism",
        align: "center",
        render: renderEditable("absenteeism_count"),
      },
      {
        title: fieldTitle("lateness"),
        dataIndex: "lateness_count",
        key: "lateness",
        align: "center",
        render: renderEditable("lateness_count"),
      },
      {
        title: fieldTitle("missingPunch"),
        dataIndex: "missing_punch_count",
        key: "missing",
        align: "center",
        render: renderEditable("missing_punch_count"),
      },
      {
        title: fieldTitle("fieldSupplementSubmitted"),
        dataIndex: "supplement_submitted",
        key: "supplement_submitted",
        align: "center",
        render: renderEditable("supplement_submitted"),
      },
      {
        title: fieldTitle("fieldNotes"),
        dataIndex: "notes",
        key: "notes",
        ellipsis: true,
        render: renderEditable("notes"),
      },
      {
        title: fieldTitle("status"),
        key: "status",
        align: "center",
        render: (_, record) =>
          record.status === "ok" ? (
            <Tag icon={<CheckCircleOutlined />} color="success">
              {fieldTitle("statusOk")}
            </Tag>
          ) : (
            <Tag icon={<ExclamationCircleOutlined />} color="warning">
              {fieldTitle("statusWarning")}
            </Tag>
          ),
      },
    ],
    [fieldTitle, renderEditable]
  );

  return (
    <Table
      rowKey="id"
      loading={loading}
      columns={columns}
      dataSource={employees}
      pagination={{
        current: page,
        pageSize,
        total: employees.length,
        showSizeChanger: true,
        pageSizeOptions: [10, 20, 50],
        onChange: onPageChange,
        showTotal: (total) => `${total}`,
      }}
    />
  );
}
