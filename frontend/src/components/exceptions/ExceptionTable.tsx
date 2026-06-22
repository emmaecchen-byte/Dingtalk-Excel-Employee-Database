import { useMemo } from "react";
import { Button, Input, Select, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  AbnormalRecord,
  EXCEPTION_TYPE_LABELS,
  SUPPLEMENT_STATUS_LABELS,
  SupplementStatus,
  type ExceptionType,
} from "../../services/exceptions";

const { Text } = Typography;

const SUPPLEMENT_OPTIONS = Object.entries(SUPPLEMENT_STATUS_LABELS).map(([value, label]) => ({
  value,
  label,
}));

function supplementColor(status: SupplementStatus) {
  if (status === "yes") return "green";
  if (status === "no") return "red";
  if (status === "not_required") return "default";
  return "gold";
}

function formatDatesSummary(dates: AbnormalRecord["dates"]): string {
  if (dates.length === 0) return "—";
  if (dates.length <= 3) {
    return dates.map((item) => item.date).join("、");
  }
  return `${dates
    .slice(0, 2)
    .map((item) => item.date)
    .join("、")} 等 ${dates.length} 天`;
}

interface ExceptionTableProps {
  records: AbnormalRecord[];
  loading?: boolean;
  readOnly?: boolean;
  onUpdate: (recordId: number, payload: { supplement_status?: SupplementStatus; notes?: string }) => void;
  onDelete?: (record: AbnormalRecord) => void;
}

export default function ExceptionTable({
  records,
  loading = false,
  readOnly = false,
  onUpdate,
  onDelete,
}: ExceptionTableProps) {
  const columns: ColumnsType<AbnormalRecord> = useMemo(
    () => [
      {
        title: "姓名",
        dataIndex: "employee_name",
        width: 100,
        fixed: "left",
      },
      {
        title: "日期",
        dataIndex: "dates",
        width: 200,
        ellipsis: true,
        render: (dates: AbnormalRecord["dates"]) => formatDatesSummary(dates),
      },
      {
        title: "异常情况",
        dataIndex: "summary",
        width: 280,
        render: (_, record) => (
          <Space direction="vertical" size={2}>
            <Text>{record.summary}</Text>
            <Tag>{EXCEPTION_TYPE_LABELS[record.exception_type as ExceptionType] || record.exception_type}</Tag>
          </Space>
        ),
      },
      {
        title: "是否补单",
        dataIndex: "supplement_status",
        width: 130,
        render: (value: SupplementStatus, record) =>
          readOnly ? (
            <Text>{SUPPLEMENT_STATUS_LABELS[value]}</Text>
          ) : (
            <Select
              size="small"
              style={{ width: 110 }}
              value={value}
              options={SUPPLEMENT_OPTIONS}
              onChange={(next) => onUpdate(record.id, { supplement_status: next as SupplementStatus })}
            />
          ),
      },
      {
        title: "备注",
        dataIndex: "notes",
        width: 220,
        render: (value: string | null | undefined, record) =>
          readOnly ? (
            <Text>{value || "—"}</Text>
          ) : (
            <Input
              size="small"
              defaultValue={value ?? ""}
              placeholder="填写备注"
              onBlur={(event) => {
                const next = event.target.value;
                if ((value ?? "") !== next) {
                  onUpdate(record.id, { notes: next });
                }
              }}
            />
          ),
      },
      ...(!readOnly && onDelete
        ? [
            {
              title: "操作",
              width: 80,
              fixed: "right" as const,
              render: (_: unknown, record: AbnormalRecord) => (
                <Button type="link" danger size="small" onClick={() => onDelete(record)}>
                  删除
                </Button>
              ),
            },
          ]
        : []),
    ],
    [readOnly, onUpdate, onDelete]
  );

  return (
    <Table
      rowKey="id"
      loading={loading}
      columns={columns}
      dataSource={records}
      pagination={{ pageSize: 20, showTotal: (total) => `共 ${total} 条` }}
      scroll={{ x: 1100 }}
      expandable={{
        expandedRowRender: (record) => (
          <div style={{ padding: "4px 0" }}>
            {record.dates.map((item) => (
              <div key={`${record.id}-${item.day}`} style={{ marginBottom: 6 }}>
                <Tag color={supplementColor(record.supplement_status)}>{item.date}</Tag>
                <Text>
                  {item.detail || item.raw_text || `${item.morning || "—"} / ${item.afternoon || "—"}`}
                </Text>
              </div>
            ))}
            {record.edit_logs.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <Text type="secondary">最近编辑：</Text>
                {record.edit_logs.slice(0, 3).map((log) => (
                  <div key={log.id}>
                    <Text type="secondary">
                      {log.editor_name || "HR"} 修改 {log.field_name}: {log.old_value || "—"} →{" "}
                      {log.new_value || "—"} ({new Date(log.edited_at).toLocaleString()})
                    </Text>
                  </div>
                ))}
              </div>
            )}
          </div>
        ),
        rowExpandable: (record) => record.dates.length > 0,
      }}
    />
  );
}
