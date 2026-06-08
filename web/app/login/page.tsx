"use client";
import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2, LogIn } from "lucide-react";
import NavBar from "@/components/NavBar";
import FluidBG from "@/components/FluidBG";
import { useAuth } from "@/components/AuthContext";
import { ApiError } from "@/lib/api";

function LoginInner() {
  const { login } = useAuth();
  const router = useRouter();
  const search = useSearchParams();
  const next = search.get("next") || "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [unverified, setUnverified] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setUnverified(false);
    setBusy(true);
    try {
      await login(email.trim(), password);
      router.push(next);
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        setUnverified(true);
        setErr(e.message);
      } else {
        setErr(e instanceof ApiError ? e.message : "登录失败，后端是否启动？");
      }
      setBusy(false);
    }
  }

  return (
    <main className="relative min-h-screen">
      <FluidBG />
      <NavBar />
      <section className="relative z-10 max-w-sm mx-auto px-6 pt-24">
        <div className="apple-card p-7">
          <h1 className="text-xl font-semibold mb-1">登录</h1>
          <p className="text-sm text-[var(--fg-secondary)] mb-5">登录后可生成笔记、管理私有笔记库。</p>
          <form onSubmit={submit} className="space-y-3">
            <input
              type="email" required placeholder="邮箱" value={email}
              onChange={e => setEmail(e.target.value)}
              className="w-full bg-[var(--bg-muted)] border border-[var(--border)] rounded-xl
                         px-3 py-2 text-sm outline-none focus:border-[var(--accent)] transition-colors"
            />
            <input
              type="password" required placeholder="密码" value={password}
              onChange={e => setPassword(e.target.value)}
              className="w-full bg-[var(--bg-muted)] border border-[var(--border)] rounded-xl
                         px-3 py-2 text-sm outline-none focus:border-[var(--accent)] transition-colors"
            />
            {err && (
              <p className="text-xs text-[#ff3b30]">
                {err}
                {unverified && "（注册后看 api 控制台的验证链接完成验证）"}
              </p>
            )}
            <button type="submit" disabled={busy}
                    className="apple-button w-full inline-flex items-center justify-center gap-1.5">
              {busy ? <Loader2 size={14} className="animate-spin" /> : <LogIn size={14} />}
              登录
            </button>
          </form>
          <p className="mt-4 text-xs text-[var(--fg-tertiary)]">
            还没有账号？<Link href="/register" className="text-[var(--accent)] hover:underline">注册</Link>
          </p>
        </div>
      </section>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<main className="min-h-screen" />}>
      <LoginInner />
    </Suspense>
  );
}
