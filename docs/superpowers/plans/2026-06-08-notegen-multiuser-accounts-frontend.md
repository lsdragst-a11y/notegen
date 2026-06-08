# NoteGen 多用户账号 前端实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 notegen web 前端接上子项目 #2 已实现的多用户后端——鉴权 UI、公私笔记分流、我的笔记库、提交历史。

**Architecture:** 浏览器（Next.js :3000）直连 FastAPI（:8000），靠 httpOnly 会话 cookie `ng_session` 鉴权。所有 `fetch` 走 `credentials:'include'`，SSE 走 `withCredentials:true`。公开笔记沿用 Next 静态（`/notes/...`、`/videos/...`），私有笔记经鉴权端点 `/api/notes/{id}/file/*` 托管。`localhost:3000` 与 `localhost:8000` 是 same-site（SameSite 不区分端口），故 cookie 在 `<img>`/`<video>` 这类 no-cors 子资源上也会自动带上——私有媒体只需换 URL，无需 `crossOrigin` 改造。

**Tech Stack:** Next.js 16 (App Router) + React 19 + TypeScript + Tailwind v4 + framer-motion + lucide-react + Plyr。无前端测试 runner——验证 = `npx tsc --noEmit` + 跑起来 curl/浏览器走查。

---

## 验证约定（全计划通用，呼应用户偏好）

- 本仓库前端**没有** jest/vitest/playwright。每个任务的硬门是 `cd web && npx tsc --noEmit` 零报错（外加 `npm run lint` 选做）。
- 涉及鉴权/数据链路的任务，附 `curl` 冒烟（需后端四组件起着，见下）。**跨源 cookie 是否真带上只能在浏览器 DevTools→Network 里确认**——这一步交给用户视觉走查，执行者不要声称"已浏览器验证"。
- 纯 UI/渲染任务（登录表单样式、卡片、表格）：typecheck 通过后 `npm run dev` 给出 localhost URL，**视觉走查交给用户**。
- 每个任务结束后单独 commit（约定式提交，中文，`feat(web)/fix(web)/refactor(web)`）。

**起后端做 e2e/curl 冒烟（来自 native-redis 记忆，顺序固定）：**
```
E:\claudeproject\redis\redis-server.exe          # 1. redis
.venv\Scripts\python.exe scripts\run_worker.py   # 2. worker
.venv\Scripts\python.exe server.py               # 3. api  -> 127.0.0.1:8000
cd web; npm run dev                               # 4. web  -> localhost:3000
```
seed admin 默认凭据：`admin@notegen.local` / `admin12345`。注册新号后看 **api 控制台**打印的 `[VERIFY] http://localhost:3000/verify?token=...`，浏览器打开该链接才能登录。

---

## 后端真实 API 形状（已实现，前端按此对接，勿改后端）

来源：`server.py`、`src/accounts.py`、`src/userdata.py`、`src/authdeps.py`。

**鉴权（cookie 名 `ng_session`，httpOnly SameSite=Lax，7 天滑动）**
| 端点 | 请求 | 成功 | 失败 |
|---|---|---|---|
| `POST /api/auth/register` | `{email,password,display_name}` | 201 `{ok,message}` | 400 格式/密码<8；409 已注册 |
| `GET /api/auth/verify?token=` | — | 200 `{ok,message}` | 400 无效/过期 |
| `POST /api/auth/login` | `{email,password}` | 200 `User`（+Set-Cookie） | 401 邮箱或密码错；403 未验证邮箱 |
| `POST /api/auth/logout` | — | 200 `{ok:true}` | — |
| `GET /api/auth/me` | — | 200 `User` | 401 未登录 |

**数据/队列（除标注外均 `require_user`，匿名→401；越权他人资源→404 不泄露存在性）**
| 端点 | 说明 |
|---|---|
| `POST /api/probe` `{url}` | **无需鉴权**，返回可下画质 list（匿名也能探） |
| `POST /api/generate` `{url,quality}` | →`{job_id}`；401；409 在飞已有 1 单；503 队列不可用 |
| `POST /api/upload` (multipart `file,title?,uploader?`) | →`{job_id,...}`；401/409/503 |
| `GET /api/jobs/{id}` | job 状态快照（含 `queue_ahead`）；非 owner→404 |
| `GET /api/jobs/{id}/events` | SSE 进度流；非 owner→404 |
| `GET /api/notes/public` | `NoteView[]`（开放，无需鉴权） |
| `GET /api/notes/mine` | `NoteView[]`（我的私有库） |
| `GET /api/history` | `HistoryItem[]`（我的全量提交，时间倒序） |
| `POST /api/jobs/{id}/retry` | 仅 `failed/interrupted`→`{job_id}`；否则 409 |
| `GET /api/notes/{id}/file/{path}` | 私有笔记文件（含 `video.mp4` Range）；非 owner/匿名/不存在→404 |
| `DELETE /api/notes/{id}` | 私有仅 owner；公开仅 admin（非 admin→403） |

**JSON 形状（注意 SQLite 整数字段）**
- `User` = `{ id:string, email:string, display_name:string, role:"user"|"admin", email_verified:number(0/1), created_at:number }`（已剥 `password_hash`）
- `NoteView` = `{ id, title, domain, duration_sec, chunks, chapters, uploader, webpage_url, visibility:"public"|"private" }`
- `HistoryItem` = `{ id, user_id, source, is_local:number(0/1), quality, status:"queued"|"running"|"done"|"failed"|"interrupted", note_id:string|null, error:string|null, created_at, updated_at, finished_at:number|null }`

**私有笔记目录结构**（`src/service_common.publish_private`）：`data/user_notes/{uid}/{id}/` 下有 `summary.json`、`chapters.json`、`meta.json`、`keyframes/`、`video.mp4`。文件端点 path 相对该目录。公开笔记 JSON+keyframes 在 `web/public/notes/{id}/`，但视频在 `web/public/videos/{id}.mp4`（不同 base）。

---

## File Structure

**新增**
- `web/lib/auth.ts` — 鉴权 API client（register/verify/login/logout/me），全 `credentials:'include'`
- `web/components/AuthContext.tsx` — 全局 auth context（`user`/`loading`/`login`/`logout`/`refresh`）
- `web/components/RequireAuth.tsx` — 客户端路由守卫（未登录跳 `/login?next=`）
- `web/components/UserMenu.tsx` — NavBar 登录态用户下拉
- `web/app/login/page.tsx` `web/app/register/page.tsx` `web/app/verify/page.tsx`
- `web/app/library/page.tsx` — 我的私有笔记
- `web/app/history/page.tsx` — 提交历史

**修改**
- `web/lib/types.ts` — 加 `User` / `NoteView` / `HistoryItem`，`NoteBundle` 加 `keyframeBase`/`isPrivate`
- `web/lib/api.ts` — 全 FastAPI 调用加 credentials；SSE `withCredentials`；`deleteNote` 改打 FastAPI；新增 `fetchMyNotes`/`fetchHistory`/`retryJob`；`ApiError`
- `web/lib/notes.ts` — `fetchNote` 公→私 fallback；导入 `API_BASE`
- `web/app/layout.tsx` — 包 `AuthProvider`
- `web/components/NavBar.tsx` — 鉴权态右栏
- `web/app/page.tsx` — 提交动作门控（匿名→/login）+ 公开卡删除仅 admin
- `web/components/NotesContent.tsx` / `web/components/VlogTimeline.tsx` — keyframe URL 由 `keyframeBase` 决定
- `web/app/notes/[id]/page.tsx` — 传 `keyframeBase`

**删除**
- `web/app/api/notes/[id]/route.ts` — 旧的 Next 同源 `fs.rm` 删除路由是无鉴权后门，改走 FastAPI DELETE 后移除

---

## Task 1: User/NoteView/HistoryItem 类型 + 鉴权 API client

**Files:**
- Modify: `web/lib/types.ts`
- Create: `web/lib/auth.ts`

- [ ] **Step 1: 在 `web/lib/types.ts` 末尾追加类型**

```ts
export interface User {
  id: string;
  email: string;
  display_name: string;
  role: "user" | "admin";
  email_verified: number;   // SQLite INTEGER 0/1，用 !! 转 bool
  created_at: number;
}

export interface NoteView {
  id: string;
  title: string;
  domain: string;
  duration_sec: number;
  chunks: number;
  chapters: number;
  uploader: string;
  webpage_url: string;
  visibility: "public" | "private";
}

export type JobStatus = "queued" | "running" | "done" | "failed" | "interrupted";

export interface HistoryItem {
  id: string;
  user_id: string;
  source: string;
  is_local: number;          // 0/1
  quality: string;
  status: JobStatus;
  note_id: string | null;
  error: string | null;
  created_at: number;
  updated_at: number;
  finished_at: number | null;
}
```

- [ ] **Step 2: 新建 `web/lib/auth.ts`**

```ts
import { API_BASE, ApiError, parseError } from "./api";
import type { User } from "./types";

export async function apiRegister(
  email: string, password: string, display_name: string,
): Promise<{ ok: boolean; message: string }> {
  const r = await fetch(`${API_BASE}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password, display_name }),
  });
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
  return r.json();
}

export async function apiVerify(token: string): Promise<{ ok: boolean; message: string }> {
  const r = await fetch(`${API_BASE}/api/auth/verify?token=${encodeURIComponent(token)}`, {
    credentials: "include",
  });
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
  return r.json();
}

export async function apiLogin(email: string, password: string): Promise<User> {
  const r = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password }),
  });
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
  return r.json();
}

export async function apiLogout(): Promise<void> {
  await fetch(`${API_BASE}/api/auth/logout`, { method: "POST", credentials: "include" });
}

/** 200→User；401→null（未登录，正常态）；其它→抛。 */
export async function apiMe(): Promise<User | null> {
  const r = await fetch(`${API_BASE}/api/auth/me`, { credentials: "include" });
  if (r.status === 401) return null;
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
  return r.json();
}
```

- [ ] **Step 3: typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: 报错 `Module '"./api"' has no exported member 'ApiError'/'parseError'` —— 这两个在 Task 2 加；本步只确认类型本身无误，**Task 2 完成后再回跑应全绿**。可先临时确认 types.ts 部分：`npx tsc --noEmit` 后只剩 api.ts 相关缺失即可。

- [ ] **Step 4: commit**

```bash
git add web/lib/types.ts web/lib/auth.ts
git commit -m "feat(web): User/NoteView/HistoryItem 类型 + 鉴权 API client"
```

---

## Task 2: api.ts —— 凭据化全部 FastAPI 调用 + ApiError + 数据/重试端点

**Files:**
- Modify: `web/lib/api.ts`

- [ ] **Step 1: 在 `web/lib/api.ts` 顶部（`API_BASE` 之后）加错误工具**

```ts
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

/** 从 FastAPI 错误响应里抽 detail 文案，失败回落到状态码。 */
export async function parseError(r: Response): Promise<string> {
  try {
    const j = await r.json();
    if (j && typeof j.detail === "string") return j.detail;
  } catch { /* 非 JSON */ }
  return `${r.status}`;
}
```

- [ ] **Step 2: 给 `postGenerate` / `postProbe` 加 credentials，错误用 ApiError**

`postGenerate` body 内 fetch 加 `credentials: "include"`，并把 `if (!r.ok) throw new Error(...)` 改为：
```ts
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
```
`postProbe` 同样加 `credentials: "include"`（probe 后端虽不鉴权，带上无害且统一），错误保持原样或同改 ApiError。

- [ ] **Step 3: `postUpload`（XHR）加 withCredentials**

在 `xhr.open("POST", ...)` 之后加一行：
```ts
    xhr.withCredentials = true;
```

- [ ] **Step 4: `fetchJob` 加 credentials**

```ts
export async function fetchJob(jobId: string): Promise<JobEvent> {
  const r = await fetch(`${API_BASE}/api/jobs/${jobId}`, { credentials: "include" });
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
  return r.json();
}
```

- [ ] **Step 5: `subscribeJob`（SSE）加 withCredentials**

```ts
  const es = new EventSource(`${API_BASE}/api/jobs/${jobId}/events`, { withCredentials: true });
```

- [ ] **Step 6: `deleteNote` 改打 FastAPI（鉴权）**

```ts
export async function deleteNote(id: string): Promise<void> {
  const r = await fetch(`${API_BASE}/api/notes/${encodeURIComponent(id)}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
}
```

- [ ] **Step 7: 新增 `fetchMyNotes` / `fetchHistory` / `retryJob`（文件末尾）**

```ts
import type { NoteView, HistoryItem } from "./types";

export async function fetchMyNotes(): Promise<NoteView[]> {
  const r = await fetch(`${API_BASE}/api/notes/mine`, { credentials: "include" });
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
  return r.json();
}

export async function fetchHistory(): Promise<HistoryItem[]> {
  const r = await fetch(`${API_BASE}/api/history`, { credentials: "include" });
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
  return r.json();
}

export async function retryJob(jobId: string): Promise<{ job_id: string }> {
  const r = await fetch(`${API_BASE}/api/jobs/${jobId}/retry`, {
    method: "POST",
    credentials: "include",
  });
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
  return r.json();
}
```

- [ ] **Step 8: typecheck（连带 Task 1 应全绿）**

Run: `cd web && npx tsc --noEmit`
Expected: PASS（无报错）。

- [ ] **Step 9: commit**

```bash
git add web/lib/api.ts
git commit -m "feat(web): 全部 FastAPI 调用凭据化 + ApiError + mine/history/retry 客户端"
```

---

## Task 3: AuthContext + Provider，layout 注入

**Files:**
- Create: `web/components/AuthContext.tsx`
- Modify: `web/app/layout.tsx`

- [ ] **Step 1: 新建 `web/components/AuthContext.tsx`**

```tsx
"use client";
import { createContext, useContext, useEffect, useState, useCallback } from "react";
import type { User } from "@/lib/types";
import { apiLogin, apiLogout, apiMe } from "@/lib/auth";

interface AuthCtx {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try { setUser(await apiMe()); }
    catch { setUser(null); }
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try { const u = await apiMe(); if (alive) setUser(u); }
      catch { if (alive) setUser(null); }
      finally { if (alive) setLoading(false); }
    })();
    return () => { alive = false; };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const u = await apiLogin(email, password);
    setUser(u);
    return u;
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    setUser(null);
  }, []);

  return <Ctx.Provider value={{ user, loading, login, logout, refresh }}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth must be used within AuthProvider");
  return v;
}
```

- [ ] **Step 2: `web/app/layout.tsx` 包 AuthProvider**

import 处加：
```tsx
import { AuthProvider } from "@/components/AuthContext";
```
body 内包裹（在 LangProvider 外层）：
```tsx
      <body className="min-h-full flex flex-col">
        <AuthProvider>
          <LangProvider>{children}</LangProvider>
        </AuthProvider>
      </body>
```

- [ ] **Step 3: typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: PASS。

- [ ] **Step 4: commit**

```bash
git add web/components/AuthContext.tsx web/app/layout.tsx
git commit -m "feat(web): 全局 AuthContext + Provider 注入 layout"
```

---

## Task 4: RequireAuth 路由守卫

**Files:**
- Create: `web/components/RequireAuth.tsx`

- [ ] **Step 1: 新建 `web/components/RequireAuth.tsx`**

```tsx
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
```

- [ ] **Step 2: typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: PASS。

- [ ] **Step 3: commit**

```bash
git add web/components/RequireAuth.tsx
git commit -m "feat(web): RequireAuth 客户端路由守卫"
```

---

## Task 5: 登录页 /login

**Files:**
- Create: `web/app/login/page.tsx`

- [ ] **Step 1: 新建 `web/app/login/page.tsx`**

```tsx
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
```

- [ ] **Step 2: typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: PASS。

- [ ] **Step 3: commit**

```bash
git add web/app/login/page.tsx
git commit -m "feat(web): 登录页 /login（含未验证 403 提示）"
```

---

## Task 6: 注册页 /register

**Files:**
- Create: `web/app/register/page.tsx`

- [ ] **Step 1: 新建 `web/app/register/page.tsx`**

```tsx
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
```

- [ ] **Step 2: typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: PASS。

- [ ] **Step 3: commit**

```bash
git add web/app/register/page.tsx
git commit -m "feat(web): 注册页 /register（dev 控制台验证链接提示）"
```

---

## Task 7: 验证页 /verify

**Files:**
- Create: `web/app/verify/page.tsx`

- [ ] **Step 1: 新建 `web/app/verify/page.tsx`**

```tsx
"use client";
import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import NavBar from "@/components/NavBar";
import FluidBG from "@/components/FluidBG";
import { apiVerify } from "@/lib/auth";

function VerifyInner() {
  const search = useSearchParams();
  const token = search.get("token") || "";
  const [state, setState] = useState<"pending" | "ok" | "fail">("pending");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (!token) { setState("fail"); setMsg("缺少验证 token"); return; }
    apiVerify(token)
      .then(r => { setState("ok"); setMsg(r.message); })
      .catch(e => { setState("fail"); setMsg(e?.message || "验证失败"); });
  }, [token]);

  return (
    <main className="relative min-h-screen">
      <FluidBG />
      <NavBar />
      <section className="relative z-10 max-w-sm mx-auto px-6 pt-24">
        <div className="apple-card p-7 text-center">
          {state === "pending" && <Loader2 size={32} className="text-[var(--accent)] animate-spin mx-auto" />}
          {state === "ok" && <CheckCircle2 size={32} className="text-[#30d158] mx-auto" />}
          {state === "fail" && <AlertCircle size={32} className="text-[#ff3b30] mx-auto" />}
          <h1 className="text-lg font-semibold mt-3 mb-1">
            {state === "pending" ? "验证中…" : state === "ok" ? "邮箱验证成功" : "验证失败"}
          </h1>
          <p className="text-sm text-[var(--fg-secondary)]">{msg}</p>
          {state !== "pending" && (
            <Link href="/login" className="apple-button inline-flex mt-4">去登录</Link>
          )}
        </div>
      </section>
    </main>
  );
}

export default function VerifyPage() {
  return (
    <Suspense fallback={<main className="min-h-screen" />}>
      <VerifyInner />
    </Suspense>
  );
}
```

- [ ] **Step 2: typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: PASS。

- [ ] **Step 3: commit**

```bash
git add web/app/verify/page.tsx
git commit -m "feat(web): 邮箱验证页 /verify"
```

---

## Task 8: NavBar 鉴权态 + UserMenu

**Files:**
- Create: `web/components/UserMenu.tsx`
- Modify: `web/components/NavBar.tsx`

- [ ] **Step 1: 新建 `web/components/UserMenu.tsx`**

```tsx
"use client";
import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { User as UserIcon, BookMarked, History, LogOut, ChevronDown } from "lucide-react";
import { useAuth } from "./AuthContext";

export default function UserMenu() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  if (!user) return null;

  async function doLogout() {
    setOpen(false);
    await logout();
    router.push("/");
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(o => !o)}
        className="inline-flex items-center gap-1.5 text-xs text-[var(--fg-secondary)]
                   hover:text-[var(--fg)] px-2 py-1.5 rounded-md hover:bg-[var(--bg-muted)] transition-colors"
      >
        <span className="w-5 h-5 rounded-full bg-[var(--bg-muted)] inline-flex items-center justify-center">
          <UserIcon size={12} />
        </span>
        <span className="max-w-[12ch] truncate">{user.display_name}</span>
        <ChevronDown size={12} />
      </button>
      {open && (
        <div className="absolute right-0 mt-1.5 w-44 glass rounded-xl border border-[var(--border)]
                        shadow-[var(--shadow-lg)] py-1.5 z-40">
          <Link href="/library" onClick={() => setOpen(false)}
                className="flex items-center gap-2 px-3 py-2 text-xs text-[var(--fg-secondary)]
                           hover:bg-[var(--bg-muted)] hover:text-[var(--fg)] transition-colors">
            <BookMarked size={13} /> 我的笔记
          </Link>
          <Link href="/history" onClick={() => setOpen(false)}
                className="flex items-center gap-2 px-3 py-2 text-xs text-[var(--fg-secondary)]
                           hover:bg-[var(--bg-muted)] hover:text-[var(--fg)] transition-colors">
            <History size={13} /> 提交历史
          </Link>
          <button onClick={doLogout}
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs text-[var(--fg-secondary)]
                             hover:bg-[var(--bg-muted)] hover:text-[var(--fg)] transition-colors">
            <LogOut size={13} /> 登出
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: `web/components/NavBar.tsx` 右栏改鉴权态**

顶部 import 加：
```tsx
import { useAuth } from "./AuthContext";
import UserMenu from "./UserMenu";
```
组件体顶部加：
```tsx
  const { user, loading } = useAuth();
```
把现有 `<LangToggle /><ThemeToggle />` 那段替换为（保留多模态链接、LangToggle、ThemeToggle，在它们左侧插入鉴权区）：
```tsx
        <LangToggle />
        <ThemeToggle />
        {!loading && (user ? (
          <UserMenu />
        ) : (
          <div className="flex items-center gap-1.5">
            <Link href="/login"
                  className="text-xs text-[var(--fg-secondary)] hover:text-[var(--fg)]
                             px-2.5 py-1.5 rounded-md hover:bg-[var(--bg-muted)] transition-colors">
              登录
            </Link>
            <Link href="/register" className="apple-button text-xs">注册</Link>
          </div>
        ))}
```

- [ ] **Step 3: typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: PASS。

- [ ] **Step 4: commit**

```bash
git add web/components/UserMenu.tsx web/components/NavBar.tsx
git commit -m "feat(web): NavBar 鉴权态右栏 + UserMenu 下拉"
```

- [ ] **Step 5: 视觉走查（交给用户）**

起后端四组件 + `npm run dev`，访问 `http://localhost:3000`：未登录 NavBar 显示「登录/注册」；用 seed admin 登录后显示用户菜单。**跨源 cookie 是否真存上请在 DevTools→Application→Cookies 看 `localhost:8000` 下有 `ng_session`。**

---

## Task 9: 首页提交门控 + 公开卡删除仅 admin

**Files:**
- Modify: `web/app/page.tsx`

- [ ] **Step 1: 引入 auth**

顶部 import 加：
```tsx
import { useAuth } from "@/components/AuthContext";
```
`LandingPage()` 体内（`const router = useRouter();` 下一行）加：
```tsx
  const { user } = useAuth();
```

- [ ] **Step 2: `handleSubmit` 开头门控匿名**

在 `handleSubmit` 里 `if (!probed) {...}` 之后、`setHint(null)` 之前插入：
```tsx
    if (!user) { router.push("/login?next=/"); return; }
```

- [ ] **Step 3: `handleSubmitFile` 开头门控匿名**

在 `handleSubmitFile` 里 `if (!file) {...}` 之后插入：
```tsx
    if (!user) { router.push("/login?next=/"); return; }
```

- [ ] **Step 4: 删除按钮仅 admin —— 给 NoteCard 传 canDelete**

map 渲染处给 `<NoteCard ... />` 加 prop：
```tsx
                canDelete={user?.role === "admin"}
```
`NoteCard` 的 props 类型加 `canDelete: boolean;`，函数签名解构加 `canDelete`，把删除按钮整段（`<button ... title="删除笔记" ...>...<Trash2/></button>`）包成条件渲染：
```tsx
          {canDelete && (
            <button
              type="button"
              onClick={(e) => { e.preventDefault(); e.stopPropagation(); onDelete(); }}
              title="删除笔记"
              className="absolute top-3 right-3 w-7 h-7 rounded-full
                         bg-[var(--bg-muted)] text-[var(--fg-tertiary)]
                         hover:bg-[#ff3b30] hover:text-white
                         inline-flex items-center justify-center
                         opacity-0 group-hover:opacity-100 transition-all z-10"
            >
              <Trash2 size={13} />
            </button>
          )}
```

- [ ] **Step 5: typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: PASS。

- [ ] **Step 6: commit**

```bash
git add web/app/page.tsx
git commit -m "feat(web): 首页提交动作门控匿名→/login + 公开卡删除仅 admin"
```

- [ ] **Step 7: 视觉走查（交给用户）**

匿名点「生成笔记」应跳 `/login?next=/`；登录普通用户提交应进 `/generate`；公开演示卡的删除按钮仅 admin 可见。

---

## Task 10: 我的笔记库 /library

**Files:**
- Create: `web/app/library/page.tsx`

- [ ] **Step 1: 新建 `web/app/library/page.tsx`**

```tsx
"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { BookMarked, Layers, Hash, Clock, ArrowRight, Trash2, Loader2 } from "lucide-react";
import NavBar from "@/components/NavBar";
import FluidBG from "@/components/FluidBG";
import RequireAuth from "@/components/RequireAuth";
import { fetchMyNotes, deleteNote } from "@/lib/api";
import { formatDuration } from "@/lib/notes";
import type { NoteView } from "@/lib/types";

function LibraryInner() {
  const [notes, setNotes] = useState<NoteView[]>([]);
  const [loading, setLoading] = useState(true);
  const [delId, setDelId] = useState<string | null>(null);

  useEffect(() => {
    fetchMyNotes().then(setNotes).catch(console.error).finally(() => setLoading(false));
  }, []);

  async function remove(id: string) {
    setDelId(id);
    try {
      await deleteNote(id);
      setNotes(n => n.filter(x => x.id !== id));
    } catch (e) {
      alert(`删除失败：${String(e)}`);
    } finally {
      setDelId(null);
    }
  }

  return (
    <main className="relative min-h-screen">
      <FluidBG />
      <NavBar />
      <section className="relative z-10 max-w-6xl mx-auto px-6 pt-20 pb-32">
        <h1 className="text-xl font-semibold mb-5 flex items-center gap-2">
          <BookMarked size={18} className="text-[var(--accent)]" /> 我的笔记
        </h1>
        {loading ? (
          <div className="text-sm text-[var(--fg-tertiary)]">加载中…</div>
        ) : notes.length === 0 ? (
          <div className="apple-card p-8 text-center">
            <p className="text-sm text-[var(--fg-secondary)]">还没有私有笔记。</p>
            <Link href="/" className="apple-button inline-flex mt-4">去生成一个</Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {notes.map(item => (
              <article key={item.id} className="apple-card group p-5 h-full flex flex-col relative">
                <button
                  type="button"
                  onClick={() => remove(item.id)}
                  disabled={delId === item.id}
                  title="删除笔记"
                  className="absolute top-3 right-3 w-7 h-7 rounded-full bg-[var(--bg-muted)]
                             text-[var(--fg-tertiary)] hover:bg-[#ff3b30] hover:text-white
                             inline-flex items-center justify-center opacity-0 group-hover:opacity-100
                             transition-all z-10 disabled:opacity-60"
                >
                  {delId === item.id ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
                </button>
                <Link href={`/notes/${item.id}`} className="flex flex-col h-full">
                  <div className="flex items-start justify-between gap-3">
                    <span className="tag-chip">{item.domain}</span>
                    <span className="inline-flex items-center gap-1 text-xs text-[var(--fg-tertiary)] tabular-nums">
                      <Clock size={11} /> {formatDuration(item.duration_sec)}
                    </span>
                  </div>
                  <h3 className="mt-3 text-base font-semibold leading-snug line-clamp-2 flex-1">{item.title}</h3>
                  {item.uploader && <p className="mt-1 text-xs text-[var(--fg-tertiary)]">{item.uploader}</p>}
                  <div className="mt-4 pt-4 border-t border-[var(--border)] flex items-center gap-3 text-xs text-[var(--fg-secondary)]">
                    <span className="inline-flex items-center gap-1"><Layers size={11} /> {item.chapters} 章</span>
                    <span className="inline-flex items-center gap-1"><Hash size={11} /> {item.chunks} 段</span>
                    <span className="ml-auto inline-flex items-center gap-1 text-[var(--accent)] font-medium group-hover:gap-1.5 transition-all">
                      打开 <ArrowRight size={12} />
                    </span>
                  </div>
                </Link>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

export default function LibraryPage() {
  return <RequireAuth><LibraryInner /></RequireAuth>;
}
```

- [ ] **Step 2: typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: PASS。

- [ ] **Step 3: commit**

```bash
git add web/app/library/page.tsx
git commit -m "feat(web): 我的笔记库 /library（鉴权 + 私有笔记网格 + 删除）"
```

- [ ] **Step 4: 视觉走查（交给用户）**

登录后访问 `/library`，未登录访问应跳 `/login?next=/library`。私有笔记需先跑通一单生成（见 e2e）才有数据。

---

## Task 11: 提交历史 /history

**Files:**
- Create: `web/app/history/page.tsx`

- [ ] **Step 1: 新建 `web/app/history/page.tsx`**

```tsx
"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { History as HistoryIcon, RotateCw, ExternalLink, Loader2 } from "lucide-react";
import NavBar from "@/components/NavBar";
import FluidBG from "@/components/FluidBG";
import RequireAuth from "@/components/RequireAuth";
import { fetchHistory, retryJob } from "@/lib/api";
import type { HistoryItem, JobStatus } from "@/lib/types";

const STATUS_LABEL: Record<JobStatus, string> = {
  queued: "排队中", running: "进行中", done: "完成", failed: "失败", interrupted: "中断",
};
const STATUS_CLASS: Record<JobStatus, string> = {
  queued: "text-[var(--fg-tertiary)] bg-[var(--bg-muted)]",
  running: "text-[var(--accent)] bg-[color-mix(in_srgb,var(--accent)_12%,transparent)]",
  done: "text-[#30d158] bg-[rgba(48,209,88,0.12)]",
  failed: "text-[#ff3b30] bg-[rgba(255,59,48,0.12)]",
  interrupted: "text-[#ff9f0a] bg-[rgba(255,159,10,0.12)]",
};

function fmtDate(ts: number): string {
  const d = new Date(ts * 1000);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getMonth() + 1}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function sourceLabel(it: HistoryItem): string {
  if (it.is_local) return "本地上传";
  return it.source.length > 48 ? it.source.slice(0, 48) + "…" : it.source;
}

function HistoryInner() {
  const router = useRouter();
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [retryId, setRetryId] = useState<string | null>(null);

  useEffect(() => {
    fetchHistory().then(setItems).catch(console.error).finally(() => setLoading(false));
  }, []);

  async function doRetry(id: string) {
    setRetryId(id);
    try {
      const { job_id } = await retryJob(id);
      router.push(`/generate?job=${job_id}`);
    } catch (e) {
      alert(`重试失败：${String(e)}`);
      setRetryId(null);
    }
  }

  return (
    <main className="relative min-h-screen">
      <FluidBG />
      <NavBar />
      <section className="relative z-10 max-w-4xl mx-auto px-6 pt-20 pb-32">
        <h1 className="text-xl font-semibold mb-5 flex items-center gap-2">
          <HistoryIcon size={18} className="text-[var(--accent)]" /> 提交历史
        </h1>
        {loading ? (
          <div className="text-sm text-[var(--fg-tertiary)]">加载中…</div>
        ) : items.length === 0 ? (
          <div className="apple-card p-8 text-center">
            <p className="text-sm text-[var(--fg-secondary)]">还没有提交记录。</p>
            <Link href="/" className="apple-button inline-flex mt-4">去生成一个</Link>
          </div>
        ) : (
          <div className="apple-card divide-y divide-[var(--border)] overflow-hidden p-0">
            {items.map(it => (
              <div key={it.id} className="flex items-center gap-3 px-4 py-3">
                <span className={`shrink-0 text-[11px] font-medium px-2 py-0.5 rounded-full ${STATUS_CLASS[it.status]}`}>
                  {STATUS_LABEL[it.status]}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm truncate">{sourceLabel(it)}</div>
                  <div className="text-[11px] text-[var(--fg-tertiary)] tabular-nums">
                    {fmtDate(it.created_at)}{it.error ? ` · ${it.error.slice(0, 40)}` : ""}
                  </div>
                </div>
                {it.status === "done" && it.note_id && (
                  <Link href={`/notes/${it.note_id}`}
                        className="shrink-0 inline-flex items-center gap-1 text-xs text-[var(--accent)] hover:underline">
                    <ExternalLink size={12} /> 看笔记
                  </Link>
                )}
                {(it.status === "failed" || it.status === "interrupted") && (
                  <button onClick={() => doRetry(it.id)} disabled={retryId === it.id}
                          className="shrink-0 inline-flex items-center gap-1 text-xs text-[var(--fg-secondary)]
                                     hover:text-[var(--fg)] disabled:opacity-60">
                    {retryId === it.id ? <Loader2 size={12} className="animate-spin" /> : <RotateCw size={12} />}
                    重试
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

export default function HistoryPage() {
  return <RequireAuth><HistoryInner /></RequireAuth>;
}
```

- [ ] **Step 2: typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: PASS。

- [ ] **Step 3: commit**

```bash
git add web/app/history/page.tsx
git commit -m "feat(web): 提交历史 /history（状态徽章 + 看笔记/重试）"
```

- [ ] **Step 4: 视觉走查（交给用户）**

登录后访问 `/history`。完成的可点「看笔记」；失败/中断的可「重试」→ 跳 `/generate`（注意每用户在飞 1 上限，已有在跑会 409）。

---

## Task 12: 私有笔记渲染（fetchNote 公→私 fallback + keyframeBase）

**Files:**
- Modify: `web/lib/types.ts`（`NoteBundle` 加字段——见下，实际 `NoteBundle` 定义在 `lib/notes.ts`）
- Modify: `web/lib/notes.ts`
- Modify: `web/components/NotesContent.tsx`
- Modify: `web/components/VlogTimeline.tsx`
- Modify: `web/app/notes/[id]/page.tsx`

- [ ] **Step 1: `web/lib/notes.ts` —— 导入 API_BASE，扩 NoteBundle，改写 fetchNote**

文件顶部 import 区加：
```ts
import { API_BASE } from "./api";
```
`NoteBundle` 接口加两字段：
```ts
export interface NoteBundle {
  id: string;
  summary: Chunk[];
  chapters: Chapter[];
  overview: Overview | null;
  meta: NoteMeta | null;
  videoUrl: string;
  keyframeBase: string;   // 末尾带 /，拼 keyframe.rel
  isPrivate: boolean;
}
```
把整个 `fetchNote` 替换为公开优先、私有 fallback：
```ts
export async function fetchNote(id: string): Promise<NoteBundle> {
  // 1) 公开静态优先（既有行为）
  const pub = `${PUBLIC_BASE}/notes/${id}`;
  const pubSummary = await fetch(`${pub}/summary.json`, { cache: "no-store" }).catch(() => null);
  if (pubSummary && pubSummary.ok) {
    const [chaptersR, metaR] = await Promise.all([
      fetch(`${pub}/chapters.json`, { cache: "no-store" }),
      fetch(`${pub}/meta.json`, { cache: "no-store" }).catch(() => null),
    ]);
    if (!chaptersR.ok) throw new Error("chapters.json missing");
    const summary: Chunk[] = await pubSummary.json();
    const chaptersData: ChaptersFile = await chaptersR.json();
    let meta: NoteMeta | null = null;
    if (metaR && metaR.ok) { try { meta = await metaR.json(); } catch { meta = null; } }
    return {
      id, summary,
      chapters: chaptersData.chapters || [],
      overview: chaptersData.overview || null,
      meta,
      videoUrl: `${PUBLIC_BASE}/videos/${id}.mp4`,
      keyframeBase: `${pub}/keyframes/`,
      isPrivate: false,
    };
  }

  // 2) 私有：经鉴权文件端点（cookie 自动带，same-site）
  const priv = `${API_BASE}/api/notes/${id}/file`;
  const [summaryR, chaptersR, metaR] = await Promise.all([
    fetch(`${priv}/summary.json`, { credentials: "include", cache: "no-store" }),
    fetch(`${priv}/chapters.json`, { credentials: "include", cache: "no-store" }),
    fetch(`${priv}/meta.json`, { credentials: "include", cache: "no-store" }).catch(() => null),
  ]);
  if (!summaryR.ok) {
    throw new Error(summaryR.status === 404 ? "笔记不存在或无权访问" : "summary.json missing");
  }
  if (!chaptersR.ok) throw new Error("chapters.json missing");
  const summary: Chunk[] = await summaryR.json();
  const chaptersData: ChaptersFile = await chaptersR.json();
  let meta: NoteMeta | null = null;
  if (metaR && metaR.ok) { try { meta = await metaR.json(); } catch { meta = null; } }
  return {
    id, summary,
    chapters: chaptersData.chapters || [],
    overview: chaptersData.overview || null,
    meta,
    videoUrl: `${priv}/video.mp4`,
    keyframeBase: `${priv}/keyframes/`,
    isPrivate: true,
  };
}
```

- [ ] **Step 2: `web/components/NotesContent.tsx` —— noteId 改 keyframeBase**

Props 接口里 `noteId: string;` 改为 `keyframeBase: string;`；函数解构 `noteId,` 改为 `keyframeBase,`。
第 ~55 行 lightbox src：
```ts
      src: `${keyframeBase}${c.keyframe.rel}`,
```
对应 `useMemo` 依赖 `[summary, noteId]` 改为 `[summary, keyframeBase]`。
第 ~158 行 `<img>`：
```tsx
                      <img src={`${keyframeBase}${kfRel}`}
```
向 VlogTimeline 传参（~216 行）`noteId={noteId}` 改为 `keyframeBase={keyframeBase}`。

- [ ] **Step 3: `web/components/VlogTimeline.tsx` —— noteId 改 keyframeBase**

Props 接口 `noteId: string;` 改为 `keyframeBase: string;`；解构 `noteId,` 改为 `keyframeBase,`。
第 ~86 行 `<img>`：
```tsx
                      <img src={`${keyframeBase}${kfRel}`}
```

- [ ] **Step 4: `web/app/notes/[id]/page.tsx` —— 传 keyframeBase**

`<NotesContent ... />`（~229 行）把 `noteId={id}` 改为：
```tsx
            keyframeBase={bundle.keyframeBase}
```
（`videoUrl` 已从 `bundle.videoUrl` 传入 VideoPlayer/MiniPlayer，私有 URL 自动生效，无需额外改。）

- [ ] **Step 5: typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: PASS。

- [ ] **Step 6: commit**

```bash
git add web/lib/notes.ts web/components/NotesContent.tsx web/components/VlogTimeline.tsx web/app/notes/[id]/page.tsx
git commit -m "feat(web): 私有笔记经鉴权端点渲染（fetchNote 公→私 fallback + keyframeBase）"
```

- [ ] **Step 7: 视觉走查（交给用户）**

公开笔记 `/notes/{公开id}` 应与改造前一致（静态路径）。私有笔记（自己生成的）`/notes/{私有id}` 应能读出文字、章节、关键帧图、视频可播可拖（Range）。**换另一个账号访问同一私有 id 应报"笔记不存在或无权访问"（后端 404）。**

---

## Task 13: 清理无鉴权删除后门

**Files:**
- Delete: `web/app/api/notes/[id]/route.ts`

- [ ] **Step 1: 删除文件**

```bash
git rm web/app/api/notes/[id]/route.ts
```
理由：该 Next 同源 `DELETE` 直接 `fs.rm` 公开目录、**无任何鉴权**，是后门。Task 2 已把 `deleteNote` 改打 FastAPI（鉴权）。注意：**只删 `[id]/route.ts`（DELETE），保留 `web/app/api/notes/route.ts`（GET 公开画廊列表，只读、首页用）。**

- [ ] **Step 2: 确认无残留引用**

Run（应无结果）：`cd web && npx tsc --noEmit && npm run lint`
Expected: PASS，且无对已删路由的引用。

- [ ] **Step 3: commit**

```bash
git commit -m "refactor(web): 移除无鉴权的 Next 删除路由后门，删除改走鉴权 FastAPI"
```

---

## 收尾验收（全部任务后，交给用户的端到端 e2e）

沿用 spec 的手动 e2e（需 GPU；`--quality 360p` 省时）：
1. 起四组件（redis→worker→api→web）。
2. 注册两个账号 A/B → 各看 api 控制台 `[VERIFY]` 链接 → `/verify` → 登录。
3. A、B 各提交一个短视频 → worker 串行跑 → 各自 `/history` 只见自己的、`/library` 只见自己的私有笔记。
4. A 复制自己私有 `/notes/{id}` 链接，B 登录访问 → 报无权（后端 404）；登出匿名访问 → 同样无权。
5. 首页公开画廊匿名可读；admin 登录可删公开卡、普通用户看不到删除键。
6. A 在飞时再提交第二单 → 前端弹 409「你已有任务在处理中」。

**诚实声明：** 执行者无法驱动浏览器，跨源 cookie / 私有视频 Range / 视觉细节这些只能由用户在浏览器里走查确认；执行者只负责 `tsc --noEmit` + curl 冒烟。

---

## Self-Review（写计划时自查）

**Spec 覆盖：** 鉴权 UI（login/register/verify ✓ Task 5-7）、auth context+受保护路由（✓ Task 3-4）、NavBar 登录态（✓ Task 8）、`/library` 我的私有库（✓ Task 10）、`/history` 提交历史含重试（✓ Task 11）、笔记页公私分流（✓ Task 12）、首页公开展示区+提交门控（✓ Task 9）、私有文件经 `/api/notes/{id}/file/*`（✓ Task 12 fetchNote + 媒体 URL）。

**关键技术取舍记录：**
- same-site cookie 流转：`localhost:3000`↔`localhost:8000` 同站，cookie 在 no-cors 子资源（img/video）自动带，故私有媒体只换 URL，**不引入 `crossOrigin`**。真跨站部署（#3 上云）需另加 `use-credentials`+媒体 CORS，本计划范围外。
- 首页公开画廊继续用 Next 同源 `GET /api/notes`（fs，离线后端也能列、无鉴权），不切 `/api/notes/public`——零额外耦合、贴合既有「不依赖 backend 在线」设计。
- 删除统一走 FastAPI（鉴权），移除 Next 删除后门（Task 13）。

**类型一致性：** `User.email_verified`/`HistoryItem.is_local` 为 `number`（SQLite INTEGER）；`ApiError`/`parseError` 在 api.ts 定义、auth.ts 复用；`NoteBundle` 新增 `keyframeBase`(末尾带 `/`)+`isPrivate`，三处消费（NotesContent/VlogTimeline 拼 `${keyframeBase}${rel}`，page 传 `bundle.keyframeBase`）签名一致。

**占位符扫描：** 无 TODO/TBD；每个代码步给出完整可粘贴代码或精确替换点。

---

## 执行选项

计划已存 `docs/superpowers/plans/2026-06-08-notegen-multiuser-accounts-frontend.md`。两种执行方式：

1. **Subagent-Driven（推荐）** — 每任务派新 subagent，任务间审查，迭代快。REQUIRED SUB-SKILL: superpowers:subagent-driven-development。
2. **Inline Execution** — 本会话内按 executing-plans 批量执行 + 检查点。REQUIRED SUB-SKILL: superpowers:executing-plans。

> 注：前端纯 UI 任务（Task 5/6/7/9/10/11）按 [[feedback-ui-live-iteration]] 也可直接实现 + 起站让用户看真效果——本计划主要作结构留档与 API 对接依据，不作为逐字逐句的死闸门。
