"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, CheckCircle2, LogIn } from "lucide-react";

import { BrandMark } from "@/components/brand/BrandMark";
import NavBar from "@/components/NavBar";
import { Button, Card, Chip, Input } from "@/components/ui";
import { useAuth } from "@/components/AuthContext";
import { ApiError } from "@/lib/api";

function getSafeNextPath(value: string | null) {
  if (!value || !value.startsWith("/") || value.startsWith("//")) {
    return "/notebooks";
  }
  return value;
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
        setErr(e instanceof ApiError ? e.message : "登录失败，请确认后端服务是否已启动。");
      }
      setBusy(false);
    }
  }

  const errorId = err ? "login-error" : undefined;

  return (
    <main className="min-h-screen bg-[var(--wf-canvas)] text-[var(--wf-text)]">
      <NavBar />
      <section className="mx-auto grid max-w-7xl items-center gap-12 px-5 py-14 sm:px-6 md:py-20 lg:grid-cols-[0.95fr_1.05fr]">
        <div className="max-w-xl">
          <Chip variant="accent" className="gap-2">
            <BrandMark size="sm" className="text-[var(--wf-text)]" />
            NoteGen Account
          </Chip>
          <h1 className="mt-6 font-[var(--wf-font-display)] text-5xl font-semibold leading-[1.05] tracking-[-0.03em] text-[var(--wf-text)] md:text-6xl">
            回到你的
            <br />
            视频笔记工作台
          </h1>
          <p className="mt-6 max-w-lg text-base leading-8 text-[var(--wf-text-secondary)]">
            登录后可以继续生成私有笔记、查看任务进度，并把每个视频沉淀成自己的复习资料。
          </p>
          <div className="mt-8 space-y-3 text-sm text-[var(--wf-text-secondary)]">
            {["私有笔记库", "提交历史与任务诊断", "支持链接和本地视频"].map((item) => (
              <div key={item} className="flex items-center gap-2">
                <CheckCircle2 size={16} className="text-[var(--wf-accent)]" aria-hidden="true" />
                <span>{item}</span>
              </div>
            ))}
          </div>
        </div>

        <Card className="mx-auto w-full max-w-md" padding="lg">
          <div className="mb-7">
            <h2 className="font-[var(--wf-font-display)] text-2xl font-semibold tracking-[-0.02em]">
              登录
            </h2>
            <p className="mt-2 text-sm text-[var(--wf-text-secondary)]">进入 NoteGen 工作台。</p>
          </div>
          <form onSubmit={submit} className="space-y-4">
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
                onChange={(e) => setEmail(e.target.value)}
                aria-describedby={errorId}
                invalid={Boolean(err)}
              />
            </div>
            <div className="space-y-2">
              <label htmlFor="login-password" className="text-sm font-medium text-[var(--wf-text)]">
                密码
              </label>
              <Input
                id="login-password"
                name="password"
                type="password"
                required
                autoComplete="current-password"
                placeholder="输入密码"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-describedby={errorId}
                invalid={Boolean(err)}
              />
            </div>
            {err ? (
              <p id={errorId} className="text-xs leading-5 text-[var(--wf-danger)]" role="alert">
                {err}
                {unverified ? "（注册后请在 api 控制台打开验证链接完成邮箱验证。）" : null}
              </p>
            ) : null}
            <Button type="submit" loading={busy} className="w-full">
              <LogIn size={14} aria-hidden="true" />
              登录
            </Button>
          </form>
          <p className="mt-5 text-sm text-[var(--wf-text-tertiary)]">
            还没有账号？
            <Link
              href="/register"
              className="ml-1 inline-flex items-center gap-1 font-medium text-[var(--wf-accent)] hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--wf-focus-ring)]"
            >
              注册 <ArrowRight size={12} aria-hidden="true" />
            </Link>
          </p>
        </Card>
      </section>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-[var(--wf-canvas)]" />}>
      <LoginInner />
    </Suspense>
  );
}
