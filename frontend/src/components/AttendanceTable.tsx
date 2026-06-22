import { memo, useCallback, useMemo, useRef, useState, type CSSProperties } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Pagination, Select, Spin, message } from "antd";
import {
  AttendancePeriodTableResponse,
  AttendanceStatusOption,
  FlatGridRow,
  applyDailyPatch,
  dayHeaderLabel,
  flattenEmployeesToGridRows,
  formatStatusOptionLabel,
  isWeekendDay,
  patchDailyAttendanceCell,
} from "../services/attendanceTable";
import { statusClass } from "../lib/attendanceSheetUtils";
import { getApiErrorMessage } from "../services/api";
import "./attendance-table/attendancePeriodGrid.css";

const ROW_HEIGHT = 34;

const TOTAL_COLUMNS: Array<{ key: keyof FlatGridRow["totals"]; label: string }> = [
  { key: "present", label: "出勤" },
  { key: "personal_leave", label: "事假" },
  { key: "compensatory_leave", label: "调休" },
  { key: "business_trip", label: "出差" },
  { key: "sick_leave", label: "病假" },
  { key: "welfare_leave", label: "福利假" },
  { key: "annual_leave", label: "年假" },
  { key: "maternity_leave", label: "产假" },
  { key: "funeral_leave", label: "丧假" },
  { key: "marriage_leave", label: "婚假" },
  { key: "absenteeism", label: "旷工" },
  { key: "lateness", label: "迟到" },
  { key: "missing_punch", label: "缺卡" },
];

interface EditingCell {
  dailyId: number;
  shift: "morning" | "afternoon";
}

export interface AttendanceTableProps {
  data: AttendancePeriodTableResponse;
  loading?: boolean;
  editable?: boolean;
  onPageChange: (page: number, pageSize: number) => void;
  onDataPatch: (next: AttendancePeriodTableResponse) => void;
}

function displayCellValue(cell: FlatGridRow["days"][number]): string {
  return cell.symbol || cell.status || "";
}

interface GridRowProps {
  row: FlatGridRow;
  year: number;
  month: number;
  daysInMonth: number;
  editable: boolean;
  statusOptions: AttendanceStatusOption[];
  editingCell: EditingCell | null;
  savingCell: EditingCell | null;
  onStartEdit: (cell: EditingCell) => void;
  onFinishEdit: (dailyId: number, shift: "morning" | "afternoon", status: string) => void;
  onCancelEdit: () => void;
  style?: CSSProperties;
}

const GridRow = memo(function GridRow({
  row,
  year,
  month,
  daysInMonth,
  editable,
  statusOptions,
  editingCell,
  savingCell,
  onStartEdit,
  onFinishEdit,
  onCancelEdit,
  style,
}: GridRowProps) {
  return (
    <tr style={style}>
      <td className="sticky-col-1 employee-name-cell">{row.show_name ? row.employee_name : ""}</td>
      <td className="sticky-col-2 shift-cell">{row.shift_label}</td>
      {Array.from({ length: daysInMonth }, (_, index) => {
        const day = index + 1;
        const cell = row.days[day - 1];
        const isEditing =
          editingCell !== null &&
          editingCell.dailyId === cell?.daily_id &&
          editingCell.shift === row.shift;
        const isSaving =
          savingCell !== null &&
          savingCell.dailyId === cell?.daily_id &&
          savingCell.shift === row.shift;
        const display = displayCellValue(cell);
        const weekend = isWeekendDay(year, month, day);
        const className = [
          "day-cell",
          statusClass(display),
          cell?.requires_review ? "review" : "",
          weekend ? "weekend-cell" : "",
          isSaving ? "saving" : "",
        ]
          .filter(Boolean)
          .join(" ");

        return (
          <td
            key={`${row.key}-day-${day}`}
            className={className}
            onClick={() => {
              if (!editable || !cell?.daily_id || isSaving) return;
              onStartEdit({ dailyId: cell.daily_id, shift: row.shift });
            }}
          >
            {isEditing ? (
              <Select
                size="small"
                autoFocus
                defaultOpen
                showSearch
                optionFilterProp="label"
                style={{ width: 132 }}
                options={statusOptions.map((option) => ({
                  value: option.value,
                  label: formatStatusOptionLabel(option),
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
        <td key={`${row.key}-${String(column.key)}`} className="totals-col">
          {row.totals[column.key]}
        </td>
      ))}
    </tr>
  );
});

export default function AttendanceTable({
  data,
  loading = false,
  editable = true,
  onPageChange,
  onDataPatch,
}: AttendanceTableProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [editingCell, setEditingCell] = useState<EditingCell | null>(null);
  const [savingCell, setSavingCell] = useState<EditingCell | null>(null);

  const gridRows = useMemo(() => flattenEmployeesToGridRows(data.employees), [data.employees]);

  const virtualizer = useVirtualizer({
    count: gridRows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
  });

  const virtualItems = virtualizer.getVirtualItems();
  const paddingTop = virtualItems.length > 0 ? virtualItems[0].start : 0;
  const paddingBottom =
    virtualItems.length > 0
      ? virtualizer.getTotalSize() - virtualItems[virtualItems.length - 1].end
      : 0;

  const handleFinishEdit = useCallback(
    async (dailyId: number, shift: "morning" | "afternoon", status: string) => {
      setEditingCell(null);
      const previousData = data;
      setSavingCell({ dailyId, shift });

      try {
        const patch = await patchDailyAttendanceCell(dailyId, shift, status);
        onDataPatch(applyDailyPatch(data, patch));
      } catch (error) {
        onDataPatch(previousData);
        message.error(getApiErrorMessage(error, "更新单元格失败"));
      } finally {
        setSavingCell(null);
      }
    },
    [data, onDataPatch]
  );

  return (
    <Spin spinning={loading}>
      <div className="attendance-period-grid-wrapper">
        <div ref={scrollRef} className="attendance-period-grid-scroll">
          <table className="attendance-period-grid">
            <thead>
              <tr>
                <th className="sticky-col-1">姓名</th>
                <th className="sticky-col-2">班次</th>
                {Array.from({ length: data.days_in_month }, (_, index) => {
                  const day = index + 1;
                  const label = dayHeaderLabel(data.year, data.month, day);
                  const weekend = label === "六" || label === "日";
                  return (
                    <th key={`header-${day}`} className={weekend ? "weekend-header" : undefined}>
                      {label}
                    </th>
                  );
                })}
                {TOTAL_COLUMNS.map((column) => (
                  <th key={String(column.key)} className="totals-col">
                    {column.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {paddingTop > 0 && (
                <tr className="virtual-spacer" aria-hidden>
                  <td colSpan={2 + data.days_in_month + TOTAL_COLUMNS.length} style={{ height: paddingTop, padding: 0, border: 0 }} />
                </tr>
              )}
              {virtualItems.map((virtualRow) => {
                const row = gridRows[virtualRow.index];
                return (
                  <GridRow
                    key={row.key}
                    row={row}
                    year={data.year}
                    month={data.month}
                    daysInMonth={data.days_in_month}
                    editable={editable}
                    statusOptions={data.status_options}
                    editingCell={editingCell}
                    savingCell={savingCell}
                    onStartEdit={setEditingCell}
                    onFinishEdit={(dailyId, shift, status) => void handleFinishEdit(dailyId, shift, status)}
                    onCancelEdit={() => setEditingCell(null)}
                  />
                );
              })}
              {paddingBottom > 0 && (
                <tr className="virtual-spacer" aria-hidden>
                  <td colSpan={2 + data.days_in_month + TOTAL_COLUMNS.length} style={{ height: paddingBottom, padding: 0, border: 0 }} />
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="attendance-period-grid-footer">
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
      </div>
    </Spin>
  );
}
