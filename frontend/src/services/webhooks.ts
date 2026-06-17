import client from "../auth/api";
import { getApiErrorMessage } from "./api";

export interface WebhookEvent {
  id: number;
  company_id?: number | null;
  source: string;
  endpoint: string;
  event_type: string;
  dingtalk_user_id?: string | null;
  event_id?: string | null;
  status: string;
  payload: Record<string, unknown>;
  error_message?: string | null;
  pending_update_id?: number | null;
  processed_at?: string | null;
  created_at: string;
}

export interface WebhookConfig {
  attendance_url: string;
  employee_url: string;
  legacy_attendance_url: string;
  webhook_secret_configured: boolean;
  webhook_crypto_configured: boolean;
  timestamp_max_skew_seconds: number;
  allowed_ips: string[];
  demo_mode: boolean;
  supported_event_types: string[];
}

export interface WebhookTestPayload {
  user_id: string;
  event_type?: string;
  event_time?: string;
  event_id?: string;
  work_date?: string;
  year?: number;
  month?: number;
  data?: Record<string, unknown>;
}

export async function fetchWebhookConfig(): Promise<WebhookConfig> {
  const { data } = await client.get<WebhookConfig>("/webhooks/config");
  return data;
}

export async function fetchWebhookEvents(limit = 50, status?: string): Promise<WebhookEvent[]> {
  const { data } = await client.get<{ events: WebhookEvent[] }>("/webhooks/events", {
    params: { limit, status },
  });
  return data.events;
}

export async function replayWebhookEvent(eventId: number): Promise<void> {
  await client.post(`/webhooks/events/${eventId}/replay`);
}

export async function testWebhook(payload: WebhookTestPayload): Promise<void> {
  await client.post("/webhooks/test", payload);
}

export { getApiErrorMessage };
