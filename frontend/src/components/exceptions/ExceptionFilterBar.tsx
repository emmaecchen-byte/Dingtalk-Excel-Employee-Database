import { Button, Input, Select, Space } from "antd";
import { SearchOutlined } from "@ant-design/icons";
import {
  EXCEPTION_TYPE_LABELS,
  SUPPLEMENT_STATUS_LABELS,
  type ExceptionType,
  type SupplementStatus,
} from "../../services/exceptions";

const TYPE_OPTIONS = Object.entries(EXCEPTION_TYPE_LABELS).map(([value, label]) => ({
  value,
  label,
}));

const SUPPLEMENT_OPTIONS = Object.entries(SUPPLEMENT_STATUS_LABELS).map(([value, label]) => ({
  value,
  label,
}));

export interface ExceptionFilters {
  employee_name: string;
  exception_type?: string;
  supplement_status?: string;
}

interface ExceptionFilterBarProps {
  filters: ExceptionFilters;
  onChange: (next: ExceptionFilters) => void;
  onRefresh: () => void;
}

export default function ExceptionFilterBar({ filters, onChange, onRefresh }: ExceptionFilterBarProps) {
  return (
    <Space wrap>
      <Input
        placeholder="按姓名筛选"
        prefix={<SearchOutlined />}
        value={filters.employee_name}
        onChange={(event) => onChange({ ...filters, employee_name: event.target.value })}
        style={{ width: 200 }}
        allowClear
      />
      <Select
        allowClear
        placeholder="异常类型"
        style={{ width: 150 }}
        options={TYPE_OPTIONS}
        value={filters.exception_type}
        onChange={(value) => onChange({ ...filters, exception_type: value })}
      />
      <Select
        allowClear
        placeholder="是否补单"
        style={{ width: 150 }}
        options={SUPPLEMENT_OPTIONS}
        value={filters.supplement_status}
        onChange={(value) => onChange({ ...filters, supplement_status: value })}
      />
      <Button onClick={onRefresh}>刷新</Button>
    </Space>
  );
}

export function filtersToQuery(filters: ExceptionFilters) {
  return {
    employee_name: filters.employee_name.trim() || undefined,
    exception_type: filters.exception_type as ExceptionType | undefined,
    supplement_status: filters.supplement_status as SupplementStatus | undefined,
  };
}
