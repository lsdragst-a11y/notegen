import { API_BASE, ApiError, parseError } from "./api";
import type { User } from "./types";

export async function apiRegister(
  email: string, password: string, display_name: string,
): Promise<{ ok: boolean; message: string }> {
  const r = await fetch(`${API_BASE}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password, display_name }),
  });
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
  return r.json();
}

export async function apiVerify(token: string): Promise<{ ok: boolean; message: string }> {
  const r = await fetch(`${API_BASE}/api/auth/verify?token=${encodeURIComponent(token)}`, {
    credentials: "include",
  });
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
  return r.json();
}

export async function apiLogin(email: string, password: string): Promise<User> {
  const r = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password }),
  });
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
  return r.json();
}

export async function apiLogout(): Promise<void> {
  await fetch(`${API_BASE}/api/auth/logout`, { method: "POST", credentials: "include" });
}

/** 200→User；401→null（未登录，正常态）；其它→抛。 */
export async function apiMe(): Promise<User | null> {
  const r = await fetch(`${API_BASE}/api/auth/me`, { credentials: "include" });
  if (r.status === 401) return null;
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
  return r.json();
}
