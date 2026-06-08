"use client";
import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useAuth } from "./AuthContext";

/** 包住受保护页面：加载中转圈，未登录跳 /login?next=当前路径。 */
export default function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !user) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [loading, user, pathname, router]);

  if (loading) {
    return (
      <main className="min-h-screen flex items-center justify-center text-[var(--fg-tertiary)]">
        <Loader2 size={20} className="animate-spin" />
      </main>
    );
  }
  if (!user) return null;
  return <>{children}</>;
}
