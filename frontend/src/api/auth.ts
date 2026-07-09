import type { CurrentUser } from "../types";
import { api, setToken } from "./client";

interface LoginResponse {
  token: string;
  user: CurrentUser;
}

export async function login(
  username: string,
  password: string,
): Promise<CurrentUser> {
  const res = await api.post<LoginResponse>("/auth/login/", {
    username,
    password,
  });
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
