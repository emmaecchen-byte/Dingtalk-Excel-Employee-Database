/** Backend origin without trailing slash, e.g. http://172.16.20.7:8000 */
export function getBackendOrigin(): string {
  const env = import.meta.env.VITE_API_BASE_URL?.trim();
  if (env) {
    return env.replace(/\/$/, "");
  }
  return "";
}

/** Axios base URL — absolute when VITE_API_BASE_URL is set, otherwise Vite proxy path. */
export function getApiBaseUrl(): string {
  const origin = getBackendOrigin();
  return origin ? `${origin}/api` : "/api";
}

export const API_BASE_URL = getApiBaseUrl();
