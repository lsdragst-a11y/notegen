"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { ArrowRight, CheckCircle2, Eye, EyeOff, UserPlus } from "lucide-react";

import { useAuth } from "@/components/AuthContext";
import { AccountCompanion, type AccountCompanionState } from "@/components/auth/AccountCompanion";
import { BrandMark } from "@/components/brand/BrandMark";
import { Button, IconButton, Input } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { apiRegister } from "@/lib/auth";

type AuthFocus = "email" | "password" | "idle";
type AuthStatus = "idle" | "error" | "success";
type RegisterErrors = {
  email?: string;
  password?: string;
  form?: string;
};

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
  const [errors, setErrors] = useState<RegisterErrors>({});
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [focus, setFocus] = useState<AuthFocus>("idle");
  const [showPassword, setShowPassword] = useState(false);
  const [authStatus, setAuthStatus] = useState<AuthStatus>("idle");

  function updateFocusFromTarget(target: EventTarget | null) {
    if (!(target instanceof HTMLInputElement)) return;
    if (target.name === "email" || target.name === "displayName") setFocus("email");
    if (target.name === "password") setFocus("password");
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErrors({});
    setAuthStatus("idle");

    if (password.length < 8) {
      setErrors({ password: "密码至少需要 8 位。" });
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
      setErrors({ form: e instanceof ApiError ? e.message : "注册失败，请确认后端服务是否已启动。" });
      setAuthStatus("error");
    } finally {
      setBusy(false);
    }
  }

  const formErrorId = errors.form ? "register-form-error" : undefined;
  const passwordErrorId = errors.password ? "register-password-error" : undefined;
  const stageStatus = done ? "success" : errors.form || errors.password || errors.email ? "error" : authStatus;

  return (
    <main className="relative isolate min-h-[100dvh] overflow-hidden bg-[var(--wf-canvas)] text-[var(--wf-text)]">
      <div className="wf-paper-atmosphere" aria-hidden="true" />
      <div className="relative z-10">
        <header className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 sm:px-6">
          <Link href="/" className="inline-flex items-center gap-2 text-[var(--wf-text)]">
            <BrandMark variant="full" size="sm" label="NoteGen" />
          </Link>
          <Link href="/login?next=/notebooks" className="text-sm font-medium text-[var(--wf-text-secondary)] hover:text-[var(--wf-text)]">
            已有账号
          </Link>
        </header>

        <section className="mx-auto px-5 pb-16 pt-6 sm:px-6 lg:pt-10">
          <div className="wf-auth-workbench mx-auto max-w-7xl overflow-visible px-1 py-5 sm:px-4 lg:px-8 lg:py-8">
            <div className="wf-auth-desk-layers" aria-hidden="true">
              <span className="wf-auth-desk-layers__note" />
              <span className="wf-auth-desk-layers__bookmark" />
              <span className="wf-auth-desk-layers__stamp" />
            </div>
            <div className="wf-auth-connector" aria-hidden="true" />
            <div className="wf-auth-stage relative z-10 min-h-[43rem]">
              <div className="wf-auth-companion-layer relative min-w-0">
                <AccountCompanion state={companionState(focus, showPassword, stageStatus)} variant="register" />
              </div>

              <div className="wf-auth-form-dock relative min-w-0">
                <div className="wf-auth-time-pill mb-4 flex items-center justify-between rounded-full border border-[var(--wf-border)] bg-[color-mix(in_srgb,var(--wf-surface)_72%,transparent)] px-4 py-2 text-xs text-[var(--wf-text-tertiary)] shadow-[var(--wf-shadow-sm)] backdrop-blur">
                  <span className="font-mono tabular-nums text-[var(--wf-accent)]">00:04</span>
                  <span>准备第一本私有视频笔记</span>
                </div>
                <div className="wf-auth-form-card relative mx-auto w-full max-w-md overflow-hidden rounded-[1.35rem] p-6 backdrop-blur md:p-8">
            <div className="relative z-10">
              {done ? (
                <div className="text-center">
                  <CheckCircle2 size={36} className="mx-auto mb-4 text-[var(--wf-accent)]" aria-hidden="true" />
                  <h2 className="font-[var(--wf-font-display)] text-2xl font-semibold tracking-[-0.02em]">
                    注册成功
                  </h2>
                  <p className="mt-3 text-sm leading-6 text-[var(--wf-text-secondary)]">{done}</p>
                  <p className="mt-3 rounded-[var(--wf-radius-sm)] border border-[var(--wf-border)] bg-[color-mix(in_srgb,var(--wf-surface-muted)_52%,transparent)] px-3 py-2 text-xs leading-5 text-[var(--wf-text-tertiary)]">
                    开发环境不发送真实邮件。验证链接会打印在 api 进程控制台，打开后即可登录。
                  </p>
                  <Link
                    href="/login?next=/notebooks"
                    className="wf-button mt-6"
                    data-size="md"
                    data-variant="primary"
                  >
                    <span className="wf-button__content">
                      去登录 <ArrowRight size={14} aria-hidden="true" />
                    </span>
                  </Link>
                </div>
              ) : (
                <>
                  <div className="mb-7">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--wf-accent)]">Private Workspace</p>
                    <h1 className="mt-3 font-[var(--wf-font-display)] text-3xl font-semibold tracking-[-0.03em]">
                      注册
                    </h1>
                    <p className="mt-2 text-sm leading-6 text-[var(--wf-text-secondary)]">
                      创建账号，把第一个视频笔记空间准备好。
                    </p>
                  </div>
                  <form
                    onSubmit={submit}
                    onClickCapture={(e) => updateFocusFromTarget(e.target)}
                    onFocusCapture={(e) => updateFocusFromTarget(e.target)}
                    onInputCapture={(e) => updateFocusFromTarget(e.target)}
                    aria-describedby={formErrorId}
                    className="space-y-4"
                  >
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
                        invalid={Boolean(errors.email)}
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
                          aria-describedby={passwordErrorId}
                          invalid={Boolean(errors.password)}
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
                      {errors.password ? (
                        <p id={passwordErrorId} className="text-xs leading-5 text-[var(--wf-danger)]" role="alert">
                          {errors.password}
                        </p>
                      ) : null}
                    </div>
                    {errors.form ? (
                      <p id={formErrorId} className="rounded-[var(--wf-radius-sm)] border border-[var(--wf-danger-border)] bg-[var(--wf-danger-surface)] px-3 py-2 text-xs leading-5 text-[var(--wf-danger)]" role="alert">
                        {errors.form}
                      </p>
                    ) : null}
                    <Button type="submit" loading={busy} className="w-full">
                      <UserPlus size={14} aria-hidden="true" />
                      {busy ? "正在创建笔记空间..." : "注册"}
                    </Button>
                  </form>
                  <p className="mt-5 text-sm text-[var(--wf-text-tertiary)]">
                    已有账号？
                    <Link
                      href="/login?next=/notebooks"
                      className="ml-1 inline-flex items-center gap-1 font-medium text-[var(--wf-accent)] hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--wf-focus)]"
                    >
                      登录 <ArrowRight size={12} aria-hidden="true" />
                    </Link>
                  </p>
                </>
              )}
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
