"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, CheckCircle2, UserPlus } from "lucide-react";

import { BrandMark } from "@/components/brand/BrandMark";
import NavBar from "@/components/NavBar";
import { Button, Card, Chip, Input } from "@/components/ui";
import { useAuth } from "@/components/AuthContext";
import { apiRegister } from "@/lib/auth";
import { ApiError } from "@/lib/api";

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

    if (password.length < 8) {
      setErr("密码至少需要 8 位。");
      return;
    }

    setBusy(true);
    try {
      const r = await apiRegister(email.trim(), password, displayName.trim() || email.trim());
      setDone(r.message);
      await refresh();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "注册失败，请确认后端服务是否已启动。");
    } finally {
      setBusy(false);
    }
  }

  const errorId = err ? "register-error" : undefined;

  return (
    <main className="min-h-screen bg-[var(--wf-canvas)] text-[var(--wf-text)]">
      <NavBar />
      <section className="mx-auto grid max-w-7xl items-center gap-12 px-5 py-14 sm:px-6 md:py-20 lg:grid-cols-[0.95fr_1.05fr]">
        <div className="max-w-xl">
          <Chip variant="accent" className="gap-2">
            <BrandMark size="sm" className="text-[var(--wf-text)]" />
            Private Workspace
          </Chip>
          <h1 className="mt-6 font-[var(--wf-font-display)] text-5xl font-semibold leading-[1.05] tracking-[-0.03em] text-[var(--wf-text)] md:text-6xl">
            为你的学习视频
            <br />
            建一个私有空间
          </h1>
          <p className="mt-6 max-w-lg text-base leading-8 text-[var(--wf-text-secondary)]">
            注册后，每次提交的视频、生成的笔记和运行历史都会归到你的账号下，方便持续复习和追踪进度。
          </p>
        </div>

        <Card className="mx-auto w-full max-w-md" padding="lg">
          {done ? (
            <div className="text-center">
              <CheckCircle2 size={36} className="mx-auto mb-4 text-[var(--wf-accent)]" aria-hidden="true" />
              <h2 className="font-[var(--wf-font-display)] text-2xl font-semibold tracking-[-0.02em]">
                注册成功
              </h2>
              <p className="mt-3 text-sm leading-6 text-[var(--wf-text-secondary)]">{done}</p>
              <p className="mt-3 text-xs leading-5 text-[var(--wf-text-tertiary)]">
                开发环境不发送真实邮件。验证链接会打印在 api 进程控制台，打开后即可登录。
              </p>
              <Link
                href="/login?next=/notebooks"
                className="mt-6 inline-flex items-center gap-1.5 rounded-[var(--wf-radius-button)] bg-[var(--wf-accent)] px-4 py-2 text-sm font-semibold text-[var(--wf-on-accent)] transition-colors hover:bg-[var(--wf-accent-hover)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--wf-focus-ring)]"
              >
                去登录 <ArrowRight size={14} aria-hidden="true" />
              </Link>
            </div>
          ) : (
            <>
              <div className="mb-7">
                <h2 className="font-[var(--wf-font-display)] text-2xl font-semibold tracking-[-0.02em]">
                  注册
                </h2>
                <p className="mt-2 text-sm text-[var(--wf-text-secondary)]">创建 NoteGen 账号。</p>
              </div>
              <form onSubmit={submit} className="space-y-4">
                <div className="space-y-2">
                  <label htmlFor="register-email" className="text-sm font-medium text-[var(--wf-text)]">
                    邮箱
                  </label>
                  <Input
                    id="register-email"
                    name="email"
                    type="email"
                    required
                    autoComplete="email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    aria-describedby={errorId}
                    invalid={Boolean(err)}
                  />
                </div>
                <div className="space-y-2">
                  <label htmlFor="register-display-name" className="text-sm font-medium text-[var(--wf-text)]">
                    显示名
                  </label>
                  <Input
                    id="register-display-name"
                    name="displayName"
                    type="text"
                    autoComplete="name"
                    placeholder="可选"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <label htmlFor="register-password" className="text-sm font-medium text-[var(--wf-text)]">
                    密码
                  </label>
                  <Input
                    id="register-password"
                    name="password"
                    type="password"
                    required
                    minLength={8}
                    autoComplete="new-password"
                    placeholder="至少 8 位"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    aria-describedby={errorId}
                    invalid={Boolean(err)}
                  />
                </div>
                {err ? (
                  <p id={errorId} className="text-xs leading-5 text-[var(--wf-danger)]" role="alert">
                    {err}
                  </p>
                ) : null}
                <Button type="submit" loading={busy} className="w-full">
                  <UserPlus size={14} aria-hidden="true" />
                  注册
                </Button>
              </form>
              <p className="mt-5 text-sm text-[var(--wf-text-tertiary)]">
                已有账号？
                <Link
                  href="/login?next=/notebooks"
                  className="ml-1 inline-flex items-center gap-1 font-medium text-[var(--wf-accent)] hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--wf-focus-ring)]"
                >
                  登录 <ArrowRight size={12} aria-hidden="true" />
                </Link>
              </p>
            </>
          )}
        </Card>
      </section>
    </main>
  );
}
