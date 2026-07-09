// Thin fetch wrapper. Auth is token-based: the token is stored in
// localStorage and sent as `Authorization: Token <token>`.

const TOKEN_KEY = "mito_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  data: unknown;
  constructor(status: number, message: string, data: unknown) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  // When true, `body` is sent as-is (FormData) without JSON headers.
  isForm?: boolean;
}

function extractMessage(data: unknown, fallback: string): string {
  if (data && typeof data === "object") {
    const obj = data as Record<string, unknown>;
    if (typeof obj.detail === "string") return obj.detail;
    // Surface the first field error DRF returns.
    const first = Object.values(obj)[0];
    if (Array.isArray(first) && typeof first[0] === "string") return first[0];
    if (typeof first === "string") return first;
  }
  return fallback;
}

export async function apiRequest<T>(
  path: string,
  { method = "GET", body, isForm = false }: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Token ${token}`;

  let payload: BodyInit | undefined;
  if (body !== undefined) {
    if (isForm) {
      payload = body as FormData;
    } else {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }
  }

  const res = await fetch(`/api${path}`, { method, headers, body: payload });

  if (res.status === 204) return undefined as T;

  const text = await res.text();
  const data = text ? JSON.parse(text) : null;

  if (!res.ok) {
    throw new ApiError(res.status, extractMessage(data, res.statusText), data);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => apiRequest<T>(path),
  post: <T>(path: string, body?: unknown) =>
    apiRequest<T>(path, { method: "POST", body }),
  postForm: <T>(path: string, body: FormData) =>
    apiRequest<T>(path, { method: "POST", body, isForm: true }),
  patch: <T>(path: string, body?: unknown) =>
    apiRequest<T>(path, { method: "PATCH", body }),
  patchForm: <T>(path: string, body: FormData) =>
    apiRequest<T>(path, { method: "PATCH", body, isForm: true }),
  del: <T>(path: string) => apiRequest<T>(path, { method: "DELETE" }),
};
