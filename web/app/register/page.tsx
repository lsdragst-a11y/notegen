"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, CheckCircle2, Eye, EyeOff, UserPlus } from "lucide-react";

import { BrandMark } from "@/components/brand/BrandMark";
import { AccountCompanion, type AccountCompanionState } from "@/components/auth/AccountCompanion";
import { Button, IconButton, Input } from "@/components/ui";
import { useAuth } from "@/components/AuthContext";
import { apiRegister } from "@/lib/auth";
import { ApiError } from "@/lib/api";

type AuthFocus = "email" | "password" | "idle";
type AuthStatus = "idle" | "error" | "success";

function companionState(focus: AuthFocus, passwordVisible: boolean, status: AuthStatus): AccountCompanionState {
  if (status === "success") return "success";
  if (status === "error") return "error";
  if (focus === "email") return "emailFocus";
  if (focus === "password") return passwordVisible ? "passwordReveal" : "passwordFocus";
  return "idle";
}

export default function RegisterPage() {
  const { refresh } = useAuth();
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [focus, setFocus] = useState<AuthFocus>("idle");
  const [showPassword, setShowPassword] = useState(false);
  const [authStatus, setAuthStatus] = useState<AuthStatus>("idle");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setAuthStatus("idle");

    if (password.length < 8) {
      setErr("密码至少需要 8 位。");
      setAuthStatus("error");
      return;
    }

    setBusy(true);
    try {
      const r = await apiRegister(email.trim(), password, displayName.trim() || email.trim());
      setDone(r.message);
      setAuthStatus("success");
      await refresh();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "注册失败，请确认后端服务是否已启动。");
      setAuthStatus("error");
    } finally {
      setBusy(false);
    }
  }

  const errorId = err ? "register-error" : undefined;
  const stageStatus = done ? "success" : err ? "error" : authStatus;

  return (
    <main className="relative min-h-screen overflow-hidden bg-[var(--wf-canvas)] text-[var(--wf-text)]">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-64 bg-[radial-gradient(circle_at_50%_0%,color-mix(in_srgb,var(--wf-brand-coral)_16%,transparent),transparent_62%)]" />
      <header className="relative z-10 mx-auto flex h-16 max-w-7xl items-center justify-between px-5 sm:px-6">
        <Link href="/" className="inline-flex items-center gap-2 text-[var(--wf-text)]">
          <BrandMark variant="full" size="sm" label="NoteGen" />
        </Link>
        <Link href="/login?next=/notebooks" className="text-sm font-medium text-[var(--wf-text-secondary)] hover:text-[var(--wf-text)]">
          已有账号
        </Link>
      </header>

      <section className="relative z-10 mx-auto grid max-w-7xl items-center gap-8 px-5 pb-16 pt-8 sm:px-6 lg:grid-cols-[1.05fr_0.95fr]">
        <AccountCompanion state={companionState(focus, showPassword, stageStatus)} variant="register" />

        <div className="mx-auto w-full max-w-md rounded-[2rem] border border-[var(--wf-border)] bg-[color-mix(in_srgb,var(--wf-surface)_94%,transparent)] p-6 shadow-[var(--wf-shadow-lg)] backdrop-blur md:p-8">
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
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--wf-accent)]">Private Workspace</p>
                <h1 className="mt-3 font-[var(--wf-font-display)] text-3xl font-semibold tracking-[-0.03em]">
                  注册
                </h1>
                <p className="mt-2 text-sm leading-6 text-[var(--wf-text-secondary)]">创建账号，把第一个视频笔记空间准备好。</p>
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
                    onChange={(e) => {
                      setEmail(e.target.value);
                      setFocus("email");
                    }}
                    onClick={() => setFocus("email")}
                    onFocus={() => setFocus("email")}
                    onBlur={() => setFocus("idle")}
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
                    onChange={(e) => {
                      setDisplayName(e.target.value);
                      setFocus("email");
                    }}
                    onClick={() => setFocus("email")}
                    onFocus={() => setFocus("email")}
                    onBlur={() => setFocus("idle")}
                  />
                </div>
                <div className="space-y-2">
                  <label htmlFor="register-password" className="text-sm font-medium text-[var(--wf-text)]">
                    密码
                  </label>
                  <div className="relative">
                    <Input
                      id="register-password"
                      name="password"
                      type={showPassword ? "text" : "password"}
                      required
                      minLength={8}
                      autoComplete="new-password"
                      placeholder="至少 8 位"
                      value={password}
                      onChange={(e) => {
                        setPassword(e.target.value);
                        setFocus("password");
                      }}
                      onClick={() => setFocus("password")}
                      onFocus={() => setFocus("password")}
                      onBlur={() => setFocus("idle")}
                      aria-describedby={errorId}
                      invalid={Boolean(err)}
                      className="pr-11"
                    />
                    <IconButton
                      type="button"
                      onClick={() => {
                        setFocus("password");
                        setShowPassword((v) => !v);
                      }}
                      aria-label={showPassword ? "隐藏密码" : "显示密码"}
                      className="absolute right-2 top-1/2 h-8 w-8 -translate-y-1/2 rounded-full"
                      size="sm"
                    >
                      {showPassword ? <EyeOff size={15} aria-hidden="true" /> : <Eye size={15} aria-hidden="true" />}
                    </IconButton>
                  </div>
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
        </div>
      </section>
    </main>
  );
}
