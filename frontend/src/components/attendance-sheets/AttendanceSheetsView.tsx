import { Fragment, useMemo, useState } from "react";
import type { AttendanceSheetsResponse, EmployeeSheetRow } from "../../types/attendanceSheets";
import {
  SIGN_COUNT_SYMBOLS,
  dayHeaders,
  formatGeneratedAt,
  isWeekend,
  monthDateRange,
  monthlyStatusClass,
  statusClass,
} from "../../lib/attendanceSheetUtils";
import { formatOvertimeValue, summarizeOvertimeDays } from "../../lib/overtimeCalc";
import "./AttendanceSheets.css";

type SheetTab = "signature" | "monthly" | "overtime" | "explanation";

interface AttendanceSheetsViewProps {
  data: AttendanceSheetsResponse;
  language: "zh" | "en";
}

function StatusCell({ value, year, month, day }: { value: string; year: number; month: number; day: number }) {
  const weekend = !value && day > 0 && isWeekend(year, month, day);
  const display = weekend ? "" : value;
  const className = weekend ? "status-weekend" : statusClass(value);
  return <td className={className}>{display}</td>;
}

function MonthlyStatusCell({
  value,
  year,
  month,
  day,
}: {
  value: string;
  year: number;
  month: number;
  day: number;
}) {
  const weekend = !value && day > 0 && isWeekend(year, month, day);
  const display = weekend ? "" : value;
  const className = weekend ? "status-weekend" : monthlyStatusClass(value);
  return <td className={`monthly-status-cell ${className}`.trim()}>{display}</td>;
}

function SignatureSheet({ data }: { data: AttendanceSheetsResponse }) {
  const { year, month, company_name: companyName, employees } = data;

  return (
    <table>
      <thead>
        <tr>
          <th colSpan={3} className="header-title">
            {companyName}员工{year}年{month}月考勤表
          </th>
          <th colSpan={31} className="header-title" />
          <th colSpan={9} className="header-title">
            缺勤统计
          </th>
        </tr>
        <tr>
          <th>签名</th>
          <th>姓名</th>
          <th>时间</th>
          {Array.from({ length: 31 }, (_, index) => (
            <th key={`day-${index + 1}`}>{index + 1}</th>
          ))}
          {SIGN_COUNT_SYMBOLS.map((symbol) => (
            <th key={symbol}>{symbol}</th>
          ))}
          <th>缺勤</th>
        </tr>
      </thead>
      <tbody>
        {employees.map((employee) => (
          <Fragment key={employee.id}>
            <tr>
              <td />
              <td rowSpan={2} className="employee-name">
                {employee.name}
              </td>
              <td className="time-slot">上午</td>
              {employee.morning.map((value, index) => (
                <StatusCell
                  key={`${employee.id}-am-${index}`}
                  value={value}
                  year={year}
                  month={month}
                  day={index + 1}
                />
              ))}
              {SIGN_COUNT_SYMBOLS.map((symbol) => (
                <td key={`${employee.id}-count-${symbol}`}>{employee.sign_counts[symbol] ?? 0}</td>
              ))}
              <td rowSpan={2}>{employee.absent_days}</td>
            </tr>
            <tr>
              <td />
              <td className="time-slot">下午</td>
              {employee.afternoon.map((value, index) => (
                <StatusCell
                  key={`${employee.id}-pm-${index}`}
                  value={value}
                  year={year}
                  month={month}
                  day={index + 1}
                />
              ))}
            </tr>
          </Fragment>
        ))}
      </tbody>
    </table>
  );
}

function MonthlySheet({ data }: { data: AttendanceSheetsResponse }) {
  const { year, month, generated_at: generatedAt, employees } = data;
  const headers = useMemo(() => dayHeaders(year, month), [year, month]);
  const totalCols = 1 + headers.length;

  return (
    <table>
      <thead>
        <tr>
          <th colSpan={totalCols} className="header-title">
            月度汇总 统计日期：{monthDateRange(year, month)}
          </th>
        </tr>
        <tr>
          <th colSpan={totalCols} style={{ background: "#fafafa", fontSize: 12 }}>
            报表生成时间：{formatGeneratedAt(generatedAt)}
          </th>
        </tr>
        <tr>
          <th>姓名</th>
          <th colSpan={headers.length}>每日考勤状态</th>
        </tr>
        <tr>
          <th>姓名</th>
          {headers.map((label, index) => (
            <th key={`monthly-header-${index}`} className={label === "六" || label === "日" ? "status-weekend" : ""}>
              {label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {employees.map((employee) => (
          <tr key={employee.id}>
            <td className="employee-name">{employee.name}</td>
            {employee.days.map((value, index) => (
              <MonthlyStatusCell
                key={`${employee.id}-day-${index}`}
                value={value}
                year={year}
                month={month}
                day={index + 1}
              />
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function OvertimeSheet({ data }: { data: AttendanceSheetsResponse }) {
  const { year, month, employees } = data;
  const daysInMonth = new Date(year, month, 0).getDate();
  const hoursTotalLabel = `${month}月加班时长合计`;
  const multiplierTotalLabel = `${month}月加班倍数合计`;
  const dayCount = 31;
  const leadingCols = 3;
  const totalCols = leadingCols + dayCount + 7;

  return (
    <table>
      <thead>
        <tr>
          <th colSpan={totalCols} className="header-title">
            {year}年{month}月加班统计汇总表
          </th>
        </tr>
        <tr>
          <th rowSpan={2}>姓名</th>
          <th rowSpan={2}>部门</th>
          <th rowSpan={2}>加班兑换方式</th>
          {Array.from({ length: dayCount }, (_, index) => (
            <th key={`ot-day-${index + 1}`} rowSpan={2}>
              {index + 1}
            </th>
          ))}
          <th colSpan={3} className="overtime-header">
            {hoursTotalLabel}
          </th>
          <th colSpan={3} className="overtime-header">
            {multiplierTotalLabel}
          </th>
          <th rowSpan={2} className="overtime-header">
            总计
          </th>
        </tr>
        <tr>
          {["1.5倍", "2倍", "3倍", "1.5倍", "2倍", "3倍"].map((label, index) => (
            <th key={`ot-rate-${index}`}>{label}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {employees.map((employee) => {
          const summary = summarizeOvertimeDays(employee.overtime_days, daysInMonth);
          const calcValues = [
            summary.hours15,
            summary.hours2,
            summary.hours3,
            summary.pay15,
            summary.pay2,
            summary.pay3,
            summary.multiplierPayTotal,
          ];
          return (
            <tr key={employee.id}>
              <td className="employee-name">{employee.name}</td>
              <td>{employee.department}</td>
              <td>加班费</td>
              {employee.overtime_days.map((hours, index) => (
                <td key={`${employee.id}-ot-${index}`}>{hours > 0 ? hours : ""}</td>
              ))}
              {calcValues.map((value, index) => (
                <td key={`${employee.id}-ot-calc-${index}`} className="overtime-value">
                  {formatOvertimeValue(value)}
                </td>
              ))}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function explanationRows(employees: EmployeeSheetRow[]): EmployeeSheetRow[] {
  return employees.filter(
    (employee) =>
      employee.absenteeism_count > 0 ||
      employee.lateness_count > 0 ||
      employee.missing_punch_count > 0
  );
}

function ExplanationSheet({ data }: { data: AttendanceSheetsResponse }) {
  const { year, month } = data;
  const rows = explanationRows(data.employees);

  return (
    <table>
      <thead>
        <tr>
          <th>姓名</th>
          <th>日期</th>
          <th>异常情况</th>
          <th>是否补单</th>
          <th>备注</th>
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 ? (
          <tr>
            <td colSpan={5}>暂无异常情况</td>
          </tr>
        ) : (
          rows.map((employee) => (
            <tr key={employee.id}>
              <td className="employee-name">{employee.name}</td>
              <td>{employee.first_anomaly_date ?? `${year}-${String(month).padStart(2, "0")}-01`}</td>
              <td>{employee.anomaly_summary ?? ""}</td>
              <td>{employee.supplement_submitted ? "Y" : ""}</td>
              <td>{employee.notes ?? ""}</td>
            </tr>
          ))
        )}
      </tbody>
    </table>
  );
}

export default function AttendanceSheetsView({ data, language }: AttendanceSheetsViewProps) {
  const [activeTab, setActiveTab] = useState<SheetTab>("signature");
  const locale = language === "zh" ? "zh-CN" : "en-US";

  const tabs: { id: SheetTab; label: string }[] = [
    { id: "signature", label: "📋 签到表" },
    { id: "monthly", label: "📊 月度汇总" },
    { id: "overtime", label: "💰 加班结算" },
    { id: "explanation", label: "📝 情况说明" },
  ];

  return (
    <div className="attendance-sheets">
      <div className="attendance-sheets__container">
        <h1 className="attendance-sheets__title">
          {data.company_name}
          <br />
          <span className="attendance-sheets__subtitle">
            {data.year}年{data.month}月考勤管理系统
          </span>
        </h1>

        <div className="attendance-sheets__tabs">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`attendance-sheets__tab${activeTab === tab.id ? " active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="legend">
          <span style={{ fontWeight: 600, marginRight: 10 }}>图例：</span>
          <div className="legend-item">
            <div className="legend-color status-present" /> 正常
          </div>
          <div className="legend-item">
            <div className="legend-color status-chuchai" /> 出差
          </div>
          <div className="legend-item">
            <div className="legend-color status-kuanggong" /> 旷工
          </div>
          <div className="legend-item">
            <div className="legend-color status-queka" /> 缺卡
          </div>
          <div className="legend-item">
            <div className="legend-color status-chidao" /> 迟到
          </div>
          <div className="legend-item">
            <div className="legend-color status-waichu" /> 外出
          </div>
          <div className="legend-item">
            <div className="legend-color status-jiaban" /> 加班
          </div>
          <div className="legend-item">
            <div className="legend-color status-bingjia" /> 病假
          </div>
          <div className="legend-item">
            <div className="legend-color status-shijia" /> 事假
          </div>
          <div className="legend-item">
            <div className="legend-color status-xiuxi" /> 休息
          </div>
          <div className="legend-item">
            <div className="legend-color status-weekend" /> 周末
          </div>
        </div>

        <div className={`attendance-sheets__panel${activeTab === "signature" ? " active" : ""}`}>
          <SignatureSheet data={data} />
        </div>
        <div className={`attendance-sheets__panel${activeTab === "monthly" ? " active" : ""}`}>
          <MonthlySheet data={data} />
        </div>
        <div className={`attendance-sheets__panel${activeTab === "overtime" ? " active" : ""}`}>
          <OvertimeSheet data={data} />
        </div>
        <div className={`attendance-sheets__panel${activeTab === "explanation" ? " active" : ""}`}>
          <ExplanationSheet data={data} />
        </div>

        <div className="stats">
          <h3>📊 月度统计摘要</h3>
          <div className="stats-grid">
            <div className="stat-item">
              <span className="stat-label">员工总数</span>
              <span className="stat-value">{data.stats.total_employees}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">旷工合计</span>
              <span className="stat-value">{data.stats.total_absenteeism_days}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">迟到合计</span>
              <span className="stat-value">{data.stats.total_lateness_days}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">缺卡合计</span>
              <span className="stat-value">{data.stats.total_missing_punch_days}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">应出勤天数</span>
              <span className="stat-value">{data.work_days}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">报表生成时间</span>
              <span className="stat-value">{formatGeneratedAt(data.generated_at, locale)}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
