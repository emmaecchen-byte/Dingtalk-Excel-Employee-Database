/** Day column multipliers for 加班结算 (matches Excel template D=day1 … AH=day31). */

type Multiplier = 1.5 | 2 | 3;

const OVERTIME_15X_DAYS = new Set([7, 8, 9, 10, 12, 13, 14, 15, 16, 19, 20, 21, 22, 23, 26, 27, 28, 29]);
const OVERTIME_2X_DAYS = new Set([4, 5, 6, 11, 17, 18, 24, 25, 30, 31]);
const OVERTIME_3X_DAYS = new Set([2, 3]);

function dayMultiplier(day: number): Multiplier {
  if (OVERTIME_3X_DAYS.has(day)) {
    return 3;
  }
  if (OVERTIME_2X_DAYS.has(day)) {
    return 2;
  }
  if (OVERTIME_15X_DAYS.has(day)) {
    return 1.5;
  }
  return 1.5;
}

export interface OvertimeSummary {
  totalHours: number;
  hours15: number;
  hours2: number;
  hours3: number;
  pay15: number;
  pay2: number;
  pay3: number;
  multiplierPayTotal: number;
}

export function summarizeOvertimeDays(overtimeDays: number[], daysInMonth = 31): OvertimeSummary {
  let totalHours = 0;
  let hours15 = 0;
  let hours2 = 0;
  let hours3 = 0;

  for (let day = 1; day <= daysInMonth; day += 1) {
    const hours = overtimeDays[day - 1] ?? 0;
    if (hours <= 0) {
      continue;
    }
    totalHours += hours;
    const rate = dayMultiplier(day);
    if (rate === 3) {
      hours3 += hours;
    } else if (rate === 2) {
      hours2 += hours;
    } else {
      hours15 += hours;
    }
  }

  const pay15 = hours15 * 1.5;
  const pay2 = hours2 * 2;
  const pay3 = hours3 * 3;
  const multiplierPayTotal = pay15 + pay2 + pay3;

  return {
    totalHours,
    hours15,
    hours2,
    hours3,
    pay15,
    pay2,
    pay3,
    multiplierPayTotal,
  };
}

export function formatOvertimeValue(value: number): string {
  if (value <= 0) {
    return "";
  }
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}
