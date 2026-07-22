import { clearTokens, getRefreshToken, saveTokens } from "@/lib/auth";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const BASE_URL = API_BASE_URL;
const REFRESH_PATH = "/api/v1/auth/refresh";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** In-flight refresh, shared so parallel 401s exchange the token only once. */
let refreshing: Promise<boolean> | null = null;

async function exchangeRefreshToken(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;
  const response = await fetch(`${BASE_URL}${REFRESH_PATH}`, {
    method: "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) return false;
  saveTokens(await response.json());
  return true;
}

function refreshOnce(): Promise<boolean> {
  refreshing ??= exchangeRefreshToken().finally(() => {
    refreshing = null;
  });
  return refreshing;
}

function send(path: string, options: RequestInit): Promise<Response> {
  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  return fetch(`${BASE_URL}${path}`, {
    // Always hit the network: authenticated data must reflect the latest
    // mutations, never a cached GET response.
    cache: "no-store",
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  retryOn401 = true,
): Promise<T> {
  const response = await send(path, options);

  // The access token expires after 30 minutes. Without this the page would
  // silently render empty panels, because each caller catches its own failure.
  if (response.status === 401 && retryOn401 && path !== REFRESH_PATH) {
    if (await refreshOnce()) {
      return apiFetch<T>(path, options, false);
    }
    if (getRefreshToken()) clearTokens();
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(response.status, body.detail ?? "Request failed");
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json();
}
