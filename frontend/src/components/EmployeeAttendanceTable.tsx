import { useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircleOutlined, ExclamationCircleOutlined } from "@ant-design/icons";
import { Input, InputNumber, Table, Tag, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  EmployeeSummary,
  MonthlyAttendanceResponse,
  patchAttendance,
} from "../api";
import { useLanguage } from "../i18n/LanguageContext";
import type { TranslationKey } from "../i18n/translations";

type EditableField =
  | "total_attendance_days"
  | "absenteeism_count"
  | "lateness_count"
  | "missing_punch_count"
  | "notes";

const MANUAL_EDIT_STYLE: React.CSSProperties = {
  backgroundColor: "#fffbe6",
};

interface EmployeeAttendanceTableProps {
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

function getFieldValue(employee: EmployeeSummary, field: EditableField): string | number {
  if (field === "notes") {
    return employee.notes ?? "";
  }
  return employee[field];
}

interface EditableCellProps {
  employee: EmployeeSummary;
  field: EditableField;
  editable: boolean;
  isEditing: boolean;
  isManual: boolean;
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
  saving,
  onStartEdit,
  onSave,
  onCancel,
}: EditableCellProps) {
  const initial = getFieldValue(employee, field);
  const [draft, setDraft] = useState<string | number>(initial);

  useEffect(() => {
    if (isEditing) {
      setDraft(initial);
    }
  }, [isEditing, initial]);

  const cellStyle: React.CSSProperties = {
    minHeight: 32,
    padding: "4px 8px",
    cursor: editable ? "pointer" : "default",
    borderRadius: 4,
    ...(isManual ? MANUAL_EDIT_STYLE : {}),
  };

  if (!editable) {
    return <div style={cellStyle}>{initial || "—"}</div>;
  }

  if (!isEditing) {
    return (
      <div
        style={cellStyle}
        onDoubleClick={onStartEdit}
        title={editable ? "Double-click to edit" : undefined}
      >
        {initial === "" ? "—" : initial}
      </div>
    );
  }

  const commit = () => {
    onSave(String(draft));
  };

  if (field === "notes") {
    return (
      <Input
        size="small"
        autoFocus
        value={String(draft)}
        disabled={saving}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={commit}
        onPressEnter={commit}
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
      value={typeof draft === "number" ? draft : Number(draft) || 0}
      disabled={saving}
      style={{ width: "100%" }}
      onChange={(value) => setDraft(value ?? 0)}
      onBlur={commit}
      onPressEnter={commit}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          onCancel();
        }
      }}
    />
  );
}

export default function EmployeeAttendanceTable({
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
}: EmployeeAttendanceTableProps) {
  const { t } = useLanguage();
  const [editingCell, setEditingCell] = useState<EditingCell | null>(null);
  const [savingKey, setSavingKey] = useState<string | null>(null);

  const fieldTitle = useCallback(
    (key: TranslationKey) => t(key),
    [t]
  );

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

  const handleSave = useCallback(
    async (employee: EmployeeSummary, field: EditableField, rawValue: string) => {
      if (!data) {
        return;
      }

      const previousValue = getFieldValue(employee, field);
      const normalized =
        field === "notes" ? rawValue.trim() : String(Number(rawValue) || 0);

      if (String(previousValue) === normalized) {
        setEditingCell(null);
        return;
      }

      const saveKey = `${employee.id}-${field}`;
      setSavingKey(saveKey);

      const snapshot = structuredClone(data);
      updateEmployee(employee.id, (current) => {
        const next = { ...current };
        if (field === "notes") {
          next.notes = normalized;
        } else {
          next[field] = Number(normalized);
        }
        const overrides = new Set(next.manual_override_fields ?? []);
        overrides.add(field);
        next.manual_override_fields = Array.from(overrides);
        return next;
      });

      try {
        const result = await patchAttendance(year, month, employee.id, {
          field_name: field,
          new_value: normalized,
        });

        if (result.conflict_detected) {
          onDataChange(snapshot);
          message.warning(t("attendanceEditConflict"));
          onConflictDetected?.();
        } else {
          updateEmployee(employee.id, (current) => {
            const next = { ...current };
            if (field === "notes") {
              next.notes = result.new_value ?? normalized;
            } else {
              next[field] = Number(result.new_value ?? normalized);
            }
            next.manual_override_fields = result.manual_override_fields;
            return next;
          });
          message.success(t("attendanceEditSaved"));
        }
      } catch {
        onDataChange(snapshot);
        message.error(t("attendanceEditFailed"));
      } finally {
        setSavingKey(null);
        setEditingCell(null);
      }
    },
    [data, month, onConflictDetected, onDataChange, t, updateEmployee, year]
  );

  const renderEditable = useCallback(
    (field: EditableField) =>
      (_: unknown, record: EmployeeSummary) => {
        const isEditing =
          editingCell?.employeeId === record.id && editingCell.field === field;
        const isManual = (record.manual_override_fields ?? []).includes(field);
        const saving = savingKey === `${record.id}-${field}`;

        return (
          <EditableCell
            employee={record}
            field={field}
            editable={editable}
            isEditing={isEditing}
            isManual={isManual}
            saving={saving}
            onStartEdit={() => setEditingCell({ employeeId: record.id, field })}
            onCancel={() => setEditingCell(null)}
            onSave={(value) => handleSave(record, field, value)}
          />
        );
      },
    [editable, editingCell, handleSave, savingKey]
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
