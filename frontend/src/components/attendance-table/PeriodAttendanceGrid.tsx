import { memo, useCallback, useMemo, useState } from "react";
import { Input, Pagination, Select, Spin, message } from "antd";
import {
  AttendancePeriodTableResponse,
  AttendanceStatusOption,
  FlatGridRow,
  flattenEmployeesToGridRows,
  patchDailyAttendanceCell,
} from "../../services/attendanceTable";
import { statusClass } from "../../lib/attendanceSheetUtils";
import { getApiErrorMessage } from "../../services/api";
import "./attendancePeriodGrid.css";

const TOTAL_COLUMNS: Array<{ key: keyof FlatGridRow["totals"]; label: string }> = [
  { key: "present", label: "出勤" },
  { key: "personal_leave", label: "事假" },
  { key: "compensatory_leave", label: "调休" },
  { key: "business_trip", label: "出差" },
  { key: "sick_leave", label: "病假" },
  { key: "absenteeism", label: "旷工" },
  { key: "lateness", label: "迟到" },
  { key: "missing_punch", label: "缺卡" },
];

interface EditingCell {
  dailyId: number;
  shift: "morning" | "afternoon";
}

interface PeriodAttendanceGridProps {
  data: AttendancePeriodTableResponse;
  loading?: boolean;
  editable?: boolean;
  onPageChange: (page: number, pageSize: number) => void;
  onDataPatch: (next: AttendancePeriodTableResponse) => void;
}

function weekendLabel(year: number, month: number, day: number): string {
  const weekday = new Date(year, month - 1, day).getDay();
  if (weekday === 6) return "六";
  if (weekday === 0) return "日";
  return String(day);
}

function displayCellValue(cell: FlatGridRow["days"][number]): string {
  return cell.symbol || cell.status || "";
}

interface GridRowProps {
  row: FlatGridRow;
  daysInMonth: number;
  editable: boolean;
  statusOptions: AttendanceStatusOption[];
  editingCell: EditingCell | null;
  onStartEdit: (cell: EditingCell) => void;
  onFinishEdit: (dailyId: number, shift: "morning" | "afternoon", status: string) => void;
  onCancelEdit: () => void;
}

const GridRow = memo(function GridRow({
  row,
  daysInMonth,
  editable,
  statusOptions,
  editingCell,
  onStartEdit,
  onFinishEdit,
  onCancelEdit,
}: GridRowProps) {
  return (
    <tr>
      <td className="sticky-col-1 employee-name-cell">{row.show_name ? row.employee_name : ""}</td>
      <td className="sticky-col-2 shift-cell">{row.shift_label}</td>
      {Array.from({ length: daysInMonth }, (_, index) => {
        const day = index + 1;
        const cell = row.days[day - 1];
        const isEditing =
          editingCell?.dailyId === cell?.daily_id && editingCell.shift === row.shift;
        const display = displayCellValue(cell);
        const className = `day-cell ${statusClass(display)} ${cell?.requires_review ? "review" : ""}`;

        return (
          <td
            key={`${row.key}-day-${day}`}
            className={className}
            onClick={() => {
              if (!editable || !cell?.daily_id) return;
              onStartEdit({ dailyId: cell.daily_id, shift: row.shift });
            }}
          >
            {isEditing ? (
              <Select
                size="small"
                autoFocus
                defaultOpen
                style={{ width: 72 }}
                options={statusOptions.map((option) => ({
                  value: option.value,
                  label: option.symbol ? `${option.symbol} ${option.value}` : option.value,
                }))}
                defaultValue={cell.status || undefined}
                onChange={(value) => onFinishEdit(cell.daily_id!, row.shift, value)}
                onBlur={onCancelEdit}
              />
            ) : (
              display || "—"
            )}
          </td>
        );
      })}
      {TOTAL_COLUMNS.map((column) => (
        <td key={`${row.key}-${column.key}`} className="totals-col">
          {row.totals[column.key]}
        </td>
      ))}
    </tr>
  );
});

export default function PeriodAttendanceGrid({
  data,
  loading = false,
  editable = true,
  onPageChange,
  onDataPatch,
}: PeriodAttendanceGridProps) {
  const [editingCell, setEditingCell] = useState<EditingCell | null>(null);
  const [customStatus, setCustomStatus] = useState("");

  const gridRows = useMemo(
    () => flattenEmployeesToGridRows(data.employees),
    [data.employees]
  );

  const handleFinishEdit = useCallback(
    async (dailyId: number, shift: "morning" | "afternoon", status: string) => {
      setEditingCell(null);
      try {
        const patch = await patchDailyAttendanceCell(dailyId, shift, status);
        const nextEmployees = data.employees.map((employee) => {
          if (employee.employee_attendance_id !== patch.employee_attendance_id) {
            return employee;
          }
          return {
            ...employee,
            requires_review: patch.employee_requires_review,
            totals: patch.employee_totals,
            rows: employee.rows.map((shiftRow) => {
              if (shiftRow.shift !== shift) {
                return shiftRow;
              }
              return {
                ...shiftRow,
                totals: patch.row_totals,
                days: shiftRow.days.map((dayCell) => {
                  if (dayCell.daily_id !== dailyId) {
                    return dayCell;
                  }
                  return {
                    ...dayCell,
                    status: patch.status,
                    symbol: patch.symbol,
                    raw_text: patch.raw_text,
                    requires_review: patch.requires_review,
                  };
                }),
              };
            }),
          };
        });
        onDataPatch({ ...data, employees: nextEmployees });
      } catch (error) {
        message.error(getApiErrorMessage(error, "更新单元格失败"));
      }
    },
    [data, onDataPatch]
  );

  return (
    <Spin spinning={loading}>
      <div className="attendance-period-grid-wrapper">
        <div className="attendance-period-grid-scroll">
          <table className="attendance-period-grid">
            <thead>
              <tr>
                <th className="sticky-col-1">姓名</th>
                <th className="sticky-col-2">班次</th>
                {Array.from({ length: data.days_in_month }, (_, index) => {
                  const day = index + 1;
                  const label = weekendLabel(data.year, data.month, day);
                  const weekend = label === "六" || label === "日";
                  return (
                    <th key={`header-${day}`} className={weekend ? "weekend-header" : undefined}>
                      {label}
                    </th>
                  );
                })}
                {TOTAL_COLUMNS.map((column) => (
                  <th key={column.key} className="totals-col">
                    {column.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {gridRows.map((row) => (
                <GridRow
                  key={row.key}
                  row={row}
                  daysInMonth={data.days_in_month}
                  editable={editable}
                  statusOptions={data.status_options}
                  editingCell={editingCell}
                  onStartEdit={setEditingCell}
                  onFinishEdit={(dailyId, shift, status) => void handleFinishEdit(dailyId, shift, status)}
                  onCancelEdit={() => setEditingCell(null)}
                />
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ padding: 12, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span>
            共 {data.total_employees} 名员工（本页 {data.employees.length} 名）
          </span>
          <Pagination
            current={data.page}
            pageSize={data.page_size}
            total={data.total_employees}
            showSizeChanger
            pageSizeOptions={[25, 50, 100, 200]}
            onChange={onPageChange}
          />
        </div>
        {editable && (
          <div style={{ padding: "0 12px 12px" }}>
            <Input.Search
              placeholder="自定义状态文本（回车保存到当前编辑单元格）"
              value={customStatus}
              onChange={(event) => setCustomStatus(event.target.value)}
              onSearch={(value) => {
                if (!editingCell || !value.trim()) return;
                void handleFinishEdit(editingCell.dailyId, editingCell.shift, value.trim());
                setCustomStatus("");
              }}
              enterButton="应用"
            />
          </div>
        )}
      </div>
    </Spin>
  );
}
