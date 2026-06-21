"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, CheckCircle2, Loader2, Sparkles, UserPlus } from "lucide-react";
import NavBar from "@/components/NavBar";
import { apiRegister } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/components/AuthContext";

export default function RegisterPage() {
  const { refresh } = useAuth();
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (password.length < 8) { setErr("密码至少 8 位"); return; }
    setBusy(true);
    try {
      const r = await apiRegister(email.trim(), password, displayName.trim() || email.trim());
      setDone(r.message);
      await refresh();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "注册失败，后端是否启动？");
    } finally {
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
            Private Workspace
          </div>
          <h1 className="mt-6 text-5xl font-semibold leading-[1.05] md:text-6xl">
            为你的学习视频<br />建一个私有空间。
          </h1>
          <p className="mt-6 text-base leading-8 text-[var(--fg-secondary)]">
            注册后，每次提交的视频、生成的笔记和运行历史都会归到你的账号下。
          </p>
        </div>

        <div className="mx-auto w-full max-w-md rounded-[8px] border border-[var(--border)] bg-[var(--bg-elevated)] p-6 shadow-[0_18px_60px_rgba(0,0,0,0.08)] sm:p-8">
          {done ? (
            <div className="text-center">
              <CheckCircle2 size={36} className="mx-auto mb-4 text-[#30d158]" />
              <h2 className="text-2xl font-semibold">注册成功</h2>
              <p className="mt-3 text-sm leading-6 text-[var(--fg-secondary)]">{done}</p>
              <p className="mt-3 text-xs leading-5 text-[var(--fg-tertiary)]">
                开发环境不发真邮件。验证链接会打印在 api 进程控制台，打开后即可登录。
              </p>
              <Link href="/login?next=/notebooks" className="apple-button mt-6 inline-flex items-center gap-1.5">
                去登录 <ArrowRight size={14} />
              </Link>
            </div>
          ) : (
            <>
              <div className="mb-7">
                <h2 className="text-2xl font-semibold">注册</h2>
                <p className="mt-2 text-sm text-[var(--fg-secondary)]">创建 NoteGen 账号。</p>
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
                  type="text"
                  placeholder="显示名（可选）"
                  value={displayName}
                  onChange={e => setDisplayName(e.target.value)}
                  className="h-11 w-full rounded-[8px] border border-[var(--border)] bg-[var(--bg)] px-3 text-sm outline-none transition-colors placeholder:text-[var(--fg-tertiary)] focus:border-[var(--accent)]"
                />
                <input
                  type="password"
                  required
                  placeholder="密码（至少 8 位）"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className="h-11 w-full rounded-[8px] border border-[var(--border)] bg-[var(--bg)] px-3 text-sm outline-none transition-colors placeholder:text-[var(--fg-tertiary)] focus:border-[var(--accent)]"
                />
                {err && <p className="text-xs leading-5 text-[#ff3b30]">{err}</p>}
                <button type="submit" disabled={busy}
                        className="apple-button inline-flex w-full items-center justify-center gap-1.5">
                  {busy ? <Loader2 size={14} className="animate-spin" /> : <UserPlus size={14} />}
                  注册
                </button>
              </form>
              <p className="mt-5 text-sm text-[var(--fg-tertiary)]">
                已有账号？
                <Link href="/login?next=/notebooks" className="ml-1 inline-flex items-center gap-1 text-[var(--accent)] hover:underline">
                  登录 <ArrowRight size={12} />
                </Link>
              </p>
            </>
          )}
        </div>
      </section>
    </main>
  );
}
