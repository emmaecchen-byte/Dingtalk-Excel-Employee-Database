import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";
import { API_BASE_URL } from "../config/apiBase";
import {
  AccessTokenResponse,
  AuthUser,
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
  TokenResponse,
} from "./storage";

export interface RegisterPayload {
  name: string;
  email: string;
  password: string;
  role: string;
}

const client = axios.create({ baseURL: API_BASE_URL, timeout: 30_000 });

let refreshPromise: Promise<string | null> | null = null;

client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    if (error.response?.status !== 401 || !originalRequest || originalRequest._retry) {
      return Promise.reject(error);
    }

    if (originalRequest.url?.includes("/auth/login") || originalRequest.url?.includes("/auth/refresh")) {
      return Promise.reject(error);
    }

    originalRequest._retry = true;

    if (!refreshPromise) {
      refreshPromise = refreshAccessToken().finally(() => {
        refreshPromise = null;
      });
    }

    const newToken = await refreshPromise;
    if (!newToken) {
      clearTokens();
      window.location.href = "/login";
      return Promise.reject(error);
    }

    originalRequest.headers.Authorization = `Bearer ${newToken}`;
    return client(originalRequest);
  }
);

export async function login(email: string, password: string): Promise<TokenResponse> {
  const { data } = await client.post<TokenResponse>("/auth/login", { email, password });
  setTokens(data.access_token, data.refresh_token);
  return data;
}

export function getDingTalkLoginUrl(): string {
  return `${API_BASE_URL.replace(/\/$/, "")}/auth/dingtalk`;
}

export interface HealthResponse {
  status: string;
  app?: string;
  demo_mode?: boolean;
  dingtalk_oauth_enabled?: boolean;
  dingtalk_api_configured?: boolean;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const { data } = await client.get<HealthResponse>("/health");
  return data;
}

export function getConnectionErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (!error.response) {
      return "Cannot reach the backend. Confirm it is running on port 8000 and VITE_API_BASE_URL is correct.";
    }
    return `Backend returned ${error.response.status}.`;
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "Cannot reach the backend.";
}

export async function completeDingTalkLogin(
  accessToken: string,
  refreshToken: string
): Promise<AuthUser> {
  setTokens(accessToken, refreshToken);
  return fetchCurrentUser();
}

export async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    return null;
  }

  try {
    const { data } = await client.post<AccessTokenResponse>("/auth/refresh", {
      refresh_token: refreshToken,
    });
    setTokens(data.access_token, refreshToken);
    return data.access_token;
  } catch {
    clearTokens();
    return null;
  }
}

export async function logout(): Promise<void> {
  const refreshToken = getRefreshToken();
  if (refreshToken) {
    try {
      await client.post("/auth/logout", { refresh_token: refreshToken });
    } catch {
      // Ignore network errors during logout.
    }
  }
  clearTokens();
}

export async function fetchCurrentUser(): Promise<AuthUser> {
  const { data } = await client.get<AuthUser>("/auth/me");
  return data;
}

export interface DingTalkOAuthStatus {
  enabled: boolean;
  authorize_url?: string | null;
  missing_settings: string[];
}

export async function fetchDingTalkOAuthStatus(): Promise<DingTalkOAuthStatus> {
  const { data } = await client.get<DingTalkOAuthStatus>("/auth/dingtalk/status");
  return data;
}

export async function registerUser(payload: RegisterPayload): Promise<AuthUser> {
  const { data } = await client.post<AuthUser>("/auth/register", payload);
  return data;
}

export default client;
