"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, CheckCircle2, Loader2, LogIn, Sparkles } from "lucide-react";
import NavBar from "@/components/NavBar";
import { useAuth } from "@/components/AuthContext";
import { ApiError } from "@/lib/api";

function LoginInner() {
  const { login } = useAuth();
  const router = useRouter();
  const search = useSearchParams();
  const next = search.get("next") || "/notebooks";
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
    <main className="min-h-screen bg-[var(--bg)]">
      <NavBar />
      <section className="mx-auto grid max-w-7xl items-center gap-12 px-5 py-14 sm:px-6 md:py-20 lg:grid-cols-[0.95fr_1.05fr]">
        <div className="max-w-xl">
          <div className="inline-flex h-8 items-center gap-2 rounded-[8px] border border-[var(--border)] bg-[var(--bg-elevated)] px-3 text-xs font-medium text-[var(--fg-secondary)]">
            <Sparkles size={14} className="text-[var(--accent)]" />
            NoteGen Account
          </div>
          <h1 className="mt-6 text-5xl font-semibold leading-[1.05] md:text-6xl">
            回到你的<br />视频笔记工作台。
          </h1>
          <p className="mt-6 text-base leading-8 text-[var(--fg-secondary)]">
            登录后可以生成私有笔记、查看任务进度，并把每个视频沉淀成自己的复习资料。
          </p>
          <div className="mt-8 space-y-3 text-sm text-[var(--fg-secondary)]">
            {["私有笔记库", "提交历史与诊断", "支持链接和本地视频"].map(item => (
              <div key={item} className="flex items-center gap-2">
                <CheckCircle2 size={16} className="text-[var(--accent)]" />
                {item}
              </div>
            ))}
          </div>
        </div>

        <div className="mx-auto w-full max-w-md rounded-[8px] border border-[var(--border)] bg-[var(--bg-elevated)] p-6 shadow-[0_18px_60px_rgba(0,0,0,0.08)] sm:p-8">
          <div className="mb-7">
            <h2 className="text-2xl font-semibold">登录</h2>
            <p className="mt-2 text-sm text-[var(--fg-secondary)]">进入 NoteGen 工作台。</p>
          </div>
          <form onSubmit={submit} className="space-y-3">
            <input
              type="email"
              required
              placeholder="邮箱"
              value={email}
              onChange={e => setEmail(e.target.value)}
              className="h-11 w-full rounded-[8px] border border-[var(--border)] bg-[var(--bg)] px-3 text-sm outline-none transition-colors placeholder:text-[var(--fg-tertiary)] focus:border-[var(--accent)]"
            />
            <input
              type="password"
              required
              placeholder="密码"
              value={password}
              onChange={e => setPassword(e.target.value)}
              className="h-11 w-full rounded-[8px] border border-[var(--border)] bg-[var(--bg)] px-3 text-sm outline-none transition-colors placeholder:text-[var(--fg-tertiary)] focus:border-[var(--accent)]"
            />
            {err && (
              <p className="text-xs leading-5 text-[#ff3b30]">
                {err}
                {unverified && "（注册后看 api 控制台的验证链接完成验证）"}
              </p>
            )}
            <button
              type="submit"
              disabled={busy}
              className="apple-button inline-flex w-full items-center justify-center gap-1.5"
            >
              {busy ? <Loader2 size={14} className="animate-spin" /> : <LogIn size={14} />}
              登录
            </button>
          </form>
          <p className="mt-5 text-sm text-[var(--fg-tertiary)]">
            还没有账号？
            <Link href="/register" className="ml-1 inline-flex items-center gap-1 text-[var(--accent)] hover:underline">
              注册 <ArrowRight size={12} />
            </Link>
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
