"use client";
import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Loader2, WifiOff, RotateCw } from "lucide-react";
import { useAuth } from "./AuthContext";
import { Button } from "@/components/ui";

/**
 * 包住受保护页面：加载中转圈，未登录跳 /login?next=当前路径。
 * 后端连不上（offline）时不弹登录页——此时无法判定登录态，弹了也连不上，
 * 改为给离线提示 + 重试，避免把已登录用户误踢去登录。
 */
export default function RequireAuth({
  allowUnauthenticated = false,
  children,
}: {
  allowUnauthenticated?: boolean;
  children: React.ReactNode;
}) {
  const { user, loading, offline, refresh } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (allowUnauthenticated) return;
    if (!loading && !offline && !user) {
      const search = typeof window === "undefined" ? "" : window.location.search;
      router.replace(`/login?next=${encodeURIComponent(`${pathname}${search}`)}`);
    }
  }, [allowUnauthenticated, loading, offline, user, pathname, router]);

  if (allowUnauthenticated) return <>{children}</>;

  if (loading) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-3 bg-[var(--wf-canvas)] px-6 text-center text-[var(--wf-text)]">
        <Loader2 size={20} className="animate-spin text-[var(--wf-accent)]" />
        <div>
          <p className="text-sm font-medium text-[var(--wf-text)]">正在检查登录状态</p>
          <p className="mt-1 text-xs text-[var(--wf-text-tertiary)]">如果服务未启动，会在稍后显示重试入口。</p>
        </div>
      </main>
    );
  }
  if (!user && offline) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-[var(--wf-canvas)] px-6 text-center text-[var(--wf-text)]">
        <WifiOff size={28} className="text-[var(--wf-text-tertiary)]" />
        <div className="space-y-1">
          <p className="text-sm font-medium text-[var(--wf-text)]">无法连接服务器</p>
          <p className="text-xs text-[var(--wf-text-tertiary)]">服务可能未启动或暂时不可用，请稍后重试。</p>
        </div>
        <Button onClick={() => refresh()} size="sm">
          <RotateCw size={13} aria-hidden="true" /> 重试
        </Button>
      </main>
    );
  }
  if (!user) return null;
  return <>{children}</>;
}
