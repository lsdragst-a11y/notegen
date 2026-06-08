"use client";
import { useState } from "react";
import Link from "next/link";
import { Loader2, UserPlus, CheckCircle2 } from "lucide-react";
import NavBar from "@/components/NavBar";
import FluidBG from "@/components/FluidBG";
import { apiRegister } from "@/lib/auth";
import { ApiError } from "@/lib/api";

export default function RegisterPage() {
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
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "注册失败，后端是否启动？");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="relative min-h-screen">
      <FluidBG />
      <NavBar />
      <section className="relative z-10 max-w-sm mx-auto px-6 pt-24">
        <div className="apple-card p-7">
          {done ? (
            <div className="text-center">
              <CheckCircle2 size={32} className="text-[#30d158] mx-auto mb-3" />
              <h1 className="text-lg font-semibold mb-1">注册成功</h1>
              <p className="text-sm text-[var(--fg-secondary)]">{done}</p>
              <p className="mt-2 text-xs text-[var(--fg-tertiary)]">
                开发环境不发真邮件——验证链接打印在 api 进程控制台（`[VERIFY] ...`），
                打开后即可登录。
              </p>
              <Link href="/login" className="apple-button inline-flex mt-4">去登录</Link>
            </div>
          ) : (
            <>
              <h1 className="text-xl font-semibold mb-1">注册</h1>
              <p className="text-sm text-[var(--fg-secondary)] mb-5">邮箱 + 密码，验证后即可使用。</p>
              <form onSubmit={submit} className="space-y-3">
                <input type="email" required placeholder="邮箱" value={email}
                       onChange={e => setEmail(e.target.value)}
                       className="w-full bg-[var(--bg-muted)] border border-[var(--border)] rounded-xl
                                  px-3 py-2 text-sm outline-none focus:border-[var(--accent)] transition-colors" />
                <input type="text" placeholder="显示名（可选）" value={displayName}
                       onChange={e => setDisplayName(e.target.value)}
                       className="w-full bg-[var(--bg-muted)] border border-[var(--border)] rounded-xl
                                  px-3 py-2 text-sm outline-none focus:border-[var(--accent)] transition-colors" />
                <input type="password" required placeholder="密码（至少 8 位）" value={password}
                       onChange={e => setPassword(e.target.value)}
                       className="w-full bg-[var(--bg-muted)] border border-[var(--border)] rounded-xl
                                  px-3 py-2 text-sm outline-none focus:border-[var(--accent)] transition-colors" />
                {err && <p className="text-xs text-[#ff3b30]">{err}</p>}
                <button type="submit" disabled={busy}
                        className="apple-button w-full inline-flex items-center justify-center gap-1.5">
                  {busy ? <Loader2 size={14} className="animate-spin" /> : <UserPlus size={14} />}
                  注册
                </button>
              </form>
              <p className="mt-4 text-xs text-[var(--fg-tertiary)]">
                已有账号？<Link href="/login" className="text-[var(--accent)] hover:underline">登录</Link>
              </p>
            </>
          )}
        </div>
      </section>
    </main>
  );
}
