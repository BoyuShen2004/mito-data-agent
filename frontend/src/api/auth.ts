import type { CurrentUser } from "../types";
import { api, setToken } from "./client";

interface AuthResponse {
  token: string;
  user: CurrentUser;
}

export type LoginPortal = "requester" | "annotator";

export async function login(
  username: string,
  password: string,
  portal?: LoginPortal,
): Promise<CurrentUser> {
  const res = await api.post<AuthResponse>("/auth/login/", {
    username,
    password,
    ...(portal ? { portal } : {}),
  });
  setToken(res.token);
  return res.user;
}

export interface RegisterInput {
  username: string;
  password: string;
  email?: string;
  role: "annotator" | "requester";
  institution_name?: string;
}

export async function register(data: RegisterInput): Promise<CurrentUser> {
  const res = await api.post<AuthResponse>("/auth/register/", data);
  setToken(res.token);
  return res.user;
}

export async function logout(): Promise<void> {
  try {
    await api.post("/auth/logout/");
  } finally {
    setToken(null);
  }
}

export function fetchMe(): Promise<CurrentUser> {
  return api.get<CurrentUser>("/auth/me/");
}
