import client from "../auth/api";

export interface AttendanceRule {
  id: number;
  company_id: number;
  raw_keyword: string;
  normalized_status: string;
  symbol: string;
  counts_as_attendance: boolean;
  counts_as_meal_allowance: boolean;
  leave_type?: string | null;
  is_abnormal: boolean;
  priority: number;
  created_at: string;
  updated_at: string;
}

export interface AttendanceRuleListResponse {
  total: number;
  rules: AttendanceRule[];
}

export type AttendanceRulePayload = {
  raw_keyword: string;
  normalized_status: string;
  symbol: string;
  counts_as_attendance: boolean;
  counts_as_meal_allowance: boolean;
  leave_type?: string | null;
  is_abnormal: boolean;
  priority: number;
};

export const LEAVE_TYPE_OPTIONS = [
  { value: "", label: "—" },
  { value: "present", label: "出勤" },
  { value: "personal_leave", label: "事假" },
  { value: "compensatory_leave", label: "调休" },
  { value: "business_trip", label: "出差" },
  { value: "sick_leave", label: "病假" },
  { value: "welfare_leave", label: "福利假" },
  { value: "annual_leave", label: "年假" },
  { value: "maternity_leave", label: "产假" },
  { value: "funeral_leave", label: "丧假" },
  { value: "marriage_leave", label: "婚假" },
];

export async function fetchAttendanceRules(): Promise<AttendanceRuleListResponse> {
  const { data } = await client.get<AttendanceRuleListResponse>("/config/rules");
  return data;
}

export async function createAttendanceRule(payload: AttendanceRulePayload): Promise<AttendanceRule> {
  const { data } = await client.post<AttendanceRule>("/config/rules", payload);
  return data;
}

export async function updateAttendanceRule(
  ruleId: number,
  payload: Partial<AttendanceRulePayload>
): Promise<AttendanceRule> {
  const { data } = await client.put<AttendanceRule>(`/config/rules/${ruleId}`, payload);
  return data;
}

export async function deleteAttendanceRule(ruleId: number): Promise<void> {
  await client.delete(`/config/rules/${ruleId}`);
}
