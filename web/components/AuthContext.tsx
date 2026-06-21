"use client";
import { createContext, useContext, useEffect, useState, useCallback } from "react";
import type { User } from "@/lib/types";
import { apiLogin, apiLogout, apiMe } from "@/lib/auth";
import { ApiError } from "@/lib/api";

interface AuthCtx {
  user: User | null;
  loading: boolean;
  /** apiMe() 因网络/服务端错误失败——无法判定登录态，区别于「确定未登录」。 */
  offline: boolean;
  login: (email: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);

  // apiMe() 只在 401 返回 null（确定未登录），网络/500 一律抛——映射成 offline，
  // 且不清空已有 user，避免一次瞬时抖动把会话内已登录用户在客户端「登出」。
  const refresh = useCallback(async () => {
    try { setUser(await apiMe()); setOffline(false); }
    catch { setOffline(true); }
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try { const u = await apiMe(); if (alive) { setUser(u); setOffline(false); } }
      catch { if (alive) setOffline(true); }
      finally { if (alive) setLoading(false); }
    })();
    return () => { alive = false; };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    try {
      const u = await apiLogin(email, password);
      setUser(u);
      setOffline(false);
      return u;
    } catch (e) {
      setOffline(!(e instanceof ApiError));
      throw e;
    }
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    setUser(null);
  }, []);

  return (
    <Ctx.Provider value={{ user, loading, offline, login, logout, refresh }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAuth(): AuthCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth must be used within AuthProvider");
  return v;
}
