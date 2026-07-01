"use client";

import { Suspense, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, Eye, EyeOff, LogIn } from "lucide-react";

import { useAuth } from "@/components/AuthContext";
import { AccountCompanion, type AccountCompanionState } from "@/components/auth/AccountCompanion";
import { BrandMark } from "@/components/brand/BrandMark";
import { Button, IconButton, Input } from "@/components/ui";
import { ApiError } from "@/lib/api";

function getSafeNextPath(value: string | null) {
  if (!value || !value.startsWith("/") || value.startsWith("//")) {
    return "/notebooks";
  }
  return value;
}

type AuthFocus = "email" | "password" | "idle";
type AuthStatus = "idle" | "error" | "success";

function companionState(focus: AuthFocus, passwordVisible: boolean, status: AuthStatus): AccountCompanionState {
  if (status === "success") return "success";
  if (status === "error") return "error";
  if (focus === "email") return "emailFocus";
  if (focus === "password") return passwordVisible ? "passwordReveal" : "passwordFocus";
  return "idle";
}

function LoginInner() {
  const { login } = useAuth();
  const router = useRouter();
  const search = useSearchParams();
  const next = getSafeNextPath(search.get("next"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [unverified, setUnverified] = useState(false);
  const [busy, setBusy] = useState(false);
  const [focus, setFocus] = useState<AuthFocus>("idle");
  const [showPassword, setShowPassword] = useState(false);
  const [authStatus, setAuthStatus] = useState<AuthStatus>("idle");

  function updateFocusFromTarget(target: EventTarget | null) {
    if (!(target instanceof HTMLInputElement)) return;
    if (target.name === "email") setFocus("email");
    if (target.name === "password") setFocus("password");
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setUnverified(false);
    setAuthStatus("idle");
    setBusy(true);

    try {
      await login(email.trim(), password);
      setAuthStatus("success");
      router.push(next);
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        setUnverified(true);
        setErr(e.message);
      } else {
        setErr(e instanceof ApiError ? e.message : "登录失败，请确认后端服务是否已启动。");
      }
      setAuthStatus("error");
      setBusy(false);
    }
  }

  const errorId = err ? "login-error" : undefined;
  const stageStatus = err ? "error" : authStatus;

  return (
    <main className="relative isolate min-h-[100dvh] overflow-hidden bg-[var(--wf-canvas)] text-[var(--wf-text)]">
      <div className="wf-paper-atmosphere" aria-hidden="true" />
      <div className="relative z-10">
        <header className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 sm:px-6">
          <Link href="/" className="inline-flex items-center gap-2 text-[var(--wf-text)]">
            <BrandMark variant="full" size="sm" label="NoteGen" />
          </Link>
          <Link href="/register" className="text-sm font-medium text-[var(--wf-text-secondary)] hover:text-[var(--wf-text)]">
            创建账号
          </Link>
        </header>

        <section className="mx-auto px-5 pb-16 pt-6 sm:px-6 lg:pt-10">
          <div className="wf-auth-workbench mx-auto max-w-7xl overflow-hidden rounded-[2.5rem] px-4 py-5 sm:px-6 lg:px-8 lg:py-8">
            <div className="wf-auth-connector" aria-hidden="true" />
            <div className="relative z-10 grid items-center gap-7 lg:grid-cols-[1.08fr_0.92fr]">
              <div className="relative min-w-0">
                <div className="pointer-events-none absolute -left-4 top-8 hidden rounded-full border border-[color-mix(in_srgb,var(--wf-brand-coral)_24%,transparent)] bg-[color-mix(in_srgb,var(--wf-surface)_70%,transparent)] px-3 py-1 font-mono text-xs tabular-nums text-[var(--wf-accent)] shadow-[var(--wf-shadow-sm)] md:block">
                  03:11 工作台打开
                </div>
                <AccountCompanion state={companionState(focus, showPassword, stageStatus)} variant="login" />
              </div>

              <div className="relative min-w-0">
                <div className="pointer-events-none absolute -left-5 top-10 hidden h-3 w-3 rounded-full bg-[var(--wf-brand-coral)] shadow-[0_0_22px_color-mix(in_srgb,var(--wf-brand-coral)_62%,transparent)] lg:block" />
                <div className="mb-4 flex items-center justify-between rounded-full border border-[var(--wf-border)] bg-[color-mix(in_srgb,var(--wf-surface)_72%,transparent)] px-4 py-2 text-xs text-[var(--wf-text-tertiary)] shadow-[var(--wf-shadow-sm)] backdrop-blur">
                  <span className="font-mono tabular-nums text-[var(--wf-accent)]">00:00</span>
                  <span>回到你的笔记工作台</span>
                </div>
                <div className="wf-auth-form-card relative mx-auto w-full max-w-md overflow-hidden rounded-[2rem] p-6 backdrop-blur md:p-8">
            <div className="relative z-10">
              <div className="mb-7">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--wf-accent)]">NoteGen Account</p>
                <h1 className="mt-3 font-[var(--wf-font-display)] text-3xl font-semibold tracking-[-0.03em]">
                  登录
                </h1>
                <p className="mt-2 text-sm leading-6 text-[var(--wf-text-secondary)]">
                  回到视频笔记工作台，继续整理时间线、书签和问答。
                </p>
              </div>
              <form
                onSubmit={submit}
                onClickCapture={(e) => updateFocusFromTarget(e.target)}
                onFocusCapture={(e) => updateFocusFromTarget(e.target)}
                onInputCapture={(e) => updateFocusFromTarget(e.target)}
                className="space-y-4"
              >
                <div className="space-y-2">
                  <label htmlFor="login-email" className="text-sm font-medium text-[var(--wf-text)]">
                    邮箱
                  </label>
                  <Input
                    id="login-email"
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
                    aria-describedby={errorId}
                    invalid={Boolean(err)}
                  />
                </div>
                <div className="space-y-2">
                  <label htmlFor="login-password" className="text-sm font-medium text-[var(--wf-text)]">
                    密码
                  </label>
                  <div className="relative">
                    <Input
                      id="login-password"
                      name="password"
                      type={showPassword ? "text" : "password"}
                      required
                      autoComplete="current-password"
                      placeholder="输入密码"
                      value={password}
                      onChange={(e) => {
                        setPassword(e.target.value);
                        setFocus("password");
                      }}
                      onClick={() => setFocus("password")}
                      onFocus={() => setFocus("password")}
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
                  <p id={errorId} className="rounded-[var(--wf-radius-sm)] border border-[var(--wf-danger-border)] bg-[var(--wf-danger-surface)] px-3 py-2 text-xs leading-5 text-[var(--wf-danger)]" role="alert">
                    {err}
                    {unverified ? "（注册后请在 api 控制台打开验证链接完成邮箱验证。）" : null}
                  </p>
                ) : null}
                <Button type="submit" loading={busy} className="w-full">
                  <LogIn size={14} aria-hidden="true" />
                  {busy ? "正在回到笔记页..." : "登录"}
                </Button>
              </form>
              <p className="mt-5 text-sm text-[var(--wf-text-tertiary)]">
                还没有账号？
                <Link
                  href="/register"
                  className="ml-1 inline-flex items-center gap-1 font-medium text-[var(--wf-accent)] hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--wf-focus)]"
                >
                  注册 <ArrowRight size={12} aria-hidden="true" />
                </Link>
              </p>
            </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<main className="min-h-[100dvh] bg-[var(--wf-canvas)]" />}>
      <LoginInner />
    </Suspense>
  );
}
