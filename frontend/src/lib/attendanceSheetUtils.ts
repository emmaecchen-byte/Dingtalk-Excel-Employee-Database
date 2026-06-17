export const SIGN_COUNT_SYMBOLS = ["√", "◇", "✬", "▼", "※", "●", "AL", "○", "FL"] as const;

export const STATUS_CLASS_MAP: Record<string, string> = {
  "√": "status-present",
  正常: "status-present",
  出差: "status-chuchai",
  "▼": "status-chuchai",
  旷工: "status-kuanggong",
  缺卡: "status-queka",
  迟到: "status-chidao",
  外出: "status-waichu",
  加班: "status-jiaban",
  病假: "status-bingjia",
  "※": "status-bingjia",
  事假: "status-shijia",
  "◇": "status-shijia",
  六: "status-weekend",
  日: "status-weekend",
};

export function statusClass(value: string): string {
  if (!value) {
    return "";
  }
  if (STATUS_CLASS_MAP[value]) {
    return STATUS_CLASS_MAP[value];
  }
  return monthlyStatusClass(value);
}

/** Pattern-based colors for 月度汇总 DingTalk descriptive text. */
export function monthlyStatusClass(value: string): string {
  if (!value) {
    return "";
  }
  if (value.includes("出差")) {
    return "status-chuchai";
  }
  if (value.includes("旷工")) {
    return "status-kuanggong";
  }
  if (value.includes("缺卡") || value === "未打卡") {
    return "status-queka";
  }
  if (value.includes("迟到") || value.includes("早退")) {
    return "status-chidao";
  }
  if (value.includes("外勤") || value.includes("外出")) {
    return "status-waichu";
  }
  if (value.includes("病假")) {
    return "status-bingjia";
  }
  if (value.includes("事假")) {
    return "status-shijia";
  }
  if (value === "休息" || value.startsWith("休息")) {
    return "status-xiuxi";
  }
  if (value.includes("加班")) {
    return "status-jiaban";
  }
  if (value === "正常" || value.includes("正常")) {
    return "status-present";
  }
  return "";
}

export function isWeekend(year: number, month: number, day: number): boolean {
  const weekday = new Date(year, month - 1, day).getDay();
  return weekday === 0 || weekday === 6;
}

export function weekendLabel(year: number, month: number, day: number): string {
  const weekday = new Date(year, month - 1, day).getDay();
  if (weekday === 6) {
    return "六";
  }
  if (weekday === 0) {
    return "日";
  }
  return String(day);
}

export function monthDateRange(year: number, month: number): string {
  const daysInMonth = new Date(year, month, 0).getDate();
  const monthText = String(month).padStart(2, "0");
  return `${year}-${monthText}-01 至 ${year}-${monthText}-${String(daysInMonth).padStart(2, "0")}`;
}

export function formatGeneratedAt(value?: string, locale = "zh-CN"): string {
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
    hour12: false,
  });
}

export function dayHeaders(year: number, month: number): string[] {
  const daysInMonth = new Date(year, month, 0).getDate();
  return Array.from({ length: 31 }, (_, index) => {
    const day = index + 1;
    if (day > daysInMonth) {
      return "";
    }
    return weekendLabel(year, month, day);
  });
}
