"use client";
import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Loader2, WifiOff, RotateCw } from "lucide-react";
import { useAuth } from "./AuthContext";

/**
 * 包住受保护页面：加载中转圈，未登录跳 /login?next=当前路径。
 * 后端连不上（offline）时不弹登录页——此时无法判定登录态，弹了也连不上，
 * 改为给离线提示 + 重试，避免把已登录用户误踢去登录。
 */
export default function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading, offline, refresh } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !offline && !user) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [loading, offline, user, pathname, router]);

  if (loading) {
    return (
      <main className="min-h-screen flex items-center justify-center text-[var(--fg-tertiary)]">
        <Loader2 size={20} className="animate-spin" />
      </main>
    );
  }
  if (!user && offline) {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center gap-4 text-center px-6">
        <WifiOff size={28} className="text-[var(--fg-tertiary)]" />
        <div className="space-y-1">
          <p className="text-sm font-medium text-[var(--fg)]">无法连接服务器</p>
          <p className="text-xs text-[var(--fg-tertiary)]">服务可能未启动或暂时不可用，请稍后重试。</p>
        </div>
        <button onClick={() => refresh()} className="apple-button text-xs inline-flex items-center gap-1.5">
          <RotateCw size={13} /> 重试
        </button>
      </main>
    );
  }
  if (!user) return null;
  return <>{children}</>;
}
