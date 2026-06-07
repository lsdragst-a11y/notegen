# 设计：notegen 多用户 + 账号 + 历史（方案 A：FastAPI + SQLite + 服务端会话）

日期：2026-06-07
状态：设计待评审
路线图：企业级 notegen 子项目 **#2**（依赖 #1 服务骨架）

## 背景与动机

子项目 #1 把 notegen 从「CLI + 静态托管」硬化成「在线提交 → Redis+RQ 队列 → 异步处理 →
发布笔记」的服务（见 `2026-06-07-notegen-service-queue-design.md`）。但 #1 全程**无身份**：
笔记是公开静态目录 `web/public/notes/{id}/`（知道路径即可读），job 全局 keyed by job_id，
`/api/notes` 列出所有人所有笔记。

子项目 #2 引入**身份与按用户的数据隔离**：账号注册/登录、私有笔记库、提交历史。部署野心仍
限定「本机/单 GPU、重架构演示」——把企业级鉴权与多租户数据模式做正确，而非真扛流量/真发邮件。

## 已确认的关键决断（brainstorming 收敛）

1. **全鉴权，机制 = 邮箱 + 密码**（非 OAuth）：bcrypt 存密码 + 服务端会话 cookie；邮箱验证走
   **dev 控制台链接**（不接真 SMTP，上云时再换邮件服务）。
2. **笔记可见性 = 私有为主 + 公开展示区**：新生成笔记默认私有（鉴权后才能读）；现有 demo /
   已生成笔记作为公开画床人人可看。
3. **关系型数据存 SQLite**（users/sessions/note 归属/job 历史）；Docker 被本机 hypervisor 封死
   （见 env 记忆），Postgres 容器路不通，SQLite 文件库零额外服务进程，子项目 #3 上云可平滑换 Postgres。
4. **历史 = 提交历史全量**：每次提交都记（排队中/进行中/完成/失败），完成的可看笔记、失败的可重试。
5. **总体路线 = 手搓最小依赖**（方案 A）：FastAPI + 标准库 `sqlite3` + `bcrypt` + 服务端会话 cookie，
   不引入 SQLAlchemy/fastapi-users 等框架，不重塑现有「纯 FastAPI + 裸 Redis」栈。

## 目标架构

```
                         ┌─────────────── SQLite (data/notegen.db, WAL) ───────────────┐
                         │ users / email_verifications / sessions / notes / jobs(历史)  │
                         └───────▲───────────────────────────────▲─────────────────────┘
                                 │ 读写身份/归属/历史              │ 终态镜像 job 历史
[Next.js web] --cookie--> [FastAPI api 进程] --enqueue(带 user_id)--> [Redis 队列 + job 运行态]
   auth context              │ current_user 依赖                         │ 并发=1 单 worker
   /login /register          │ 私有笔记鉴权托管                          ▼
   /library /history         │ /api/notes/{id}/file/*           [RQ SimpleWorker @ GPU]
                             ▼                                          │ subprocess pipeline
                   公开笔记 web/public/notes/（静态）            私有笔记 data/user_notes/{uid}/{id}/
```

**职责分离（核心不变量）**：job 的实时进度（percent/stage/events/log）仍**只在 Redis**（热路径
不变，沿用 #1 的 SSE 形态）；SQLite `jobs` 表只在 **enqueue 时**与**终态转换时**镜像一行，作为
durable 的「我的历史」。两套存储各司其职，不重复承载实时进度。

## 数据模型（SQLite，WAL 模式）

```sql
users(
  id TEXT PRIMARY KEY,              -- uuid
  email TEXT UNIQUE NOT NULL,       -- 小写归一后存储
  password_hash TEXT NOT NULL,     -- bcrypt
  display_name TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'user',   -- 'user' | 'admin'（admin 托管公开展示区）
  email_verified INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL
)
email_verifications(
  token TEXT PRIMARY KEY,           -- secrets.token_urlsafe
  user_id TEXT NOT NULL,
  expires_at REAL NOT NULL
)
sessions(
  token TEXT PRIMARY KEY,           -- secrets.token_urlsafe，httpOnly cookie 携带
  user_id TEXT NOT NULL,
  created_at REAL NOT NULL,
  expires_at REAL NOT NULL,
  last_seen REAL NOT NULL
)
notes(
  id TEXT PRIMARY KEY,             -- = 现有 note 目录名（如 BV..._p0）
  owner_id TEXT NOT NULL,          -- 公开展示区 = seed admin 用户
  visibility TEXT NOT NULL,        -- 'private' | 'public'
  storage_path TEXT NOT NULL,      -- 公开: web/public/notes/{id}; 私有: data/user_notes/{uid}/{id}
  title TEXT, domain TEXT, duration_sec INTEGER,
  chunks INTEGER, chapters INTEGER, uploader TEXT, webpage_url TEXT,
  created_at REAL NOT NULL
)
jobs(
  id TEXT PRIMARY KEY,             -- = Redis job_id
  user_id TEXT NOT NULL,
  source TEXT NOT NULL, is_local INTEGER NOT NULL, quality TEXT NOT NULL,
  status TEXT NOT NULL,            -- 'queued'|'running'|'done'|'failed'|'interrupted'
  note_id TEXT,                    -- 完成前 NULL
  error TEXT,
  created_at REAL NOT NULL, updated_at REAL NOT NULL, finished_at REAL
)
```

`notes` 的展示字段（title/domain/…）是**列表展示冗余**，发布时从 filesystem meta 写入，避免列表
页逐目录读文件。

## 鉴权与会话

- **注册** `POST /api/auth/register {email,password,display_name}` → 建 user（`email_verified=0`）
  + 写 `email_verifications` token → 控制台打印 `[VERIFY] http://localhost:3000/verify?token=…`，
  不发真邮件。返回 201（不下发会话）。
- **验证** `GET /api/auth/verify?token=…` → token 有效且未过期 → 置 `email_verified=1`，删 token。
- **登录** `POST /api/auth/login {email,password}` → bcrypt 校验 + 查 `email_verified=1` → 建
  `sessions` 行 + 下发 httpOnly cookie `ng_session`（SameSite=Lax，7 天滑动过期，prod 加 Secure）
  → 返回 profile。**未验证 → 403「请先验证邮箱」**（演示里如嫌烦可放宽，spec 默认严格）。
- **登出** `POST /api/auth/logout` → 删 session 行 + 清 cookie。
- **当前用户** `GET /api/auth/me` → 读 cookie → session → user，供前端 auth context；无会话 → 401。
- 密码哈希用 `bcrypt`（**需新增到 `requirements.txt`**：#1 venv 当前未装；`sqlite3` 为标准库已具备
  3.40.1，无需新依赖）。错误信息统一「邮箱或密码错误」，不区分「邮箱不存在」与「密码错」（防枚举）。
- FastAPI 依赖：`current_user(request) -> User|None`；`require_user`（401）；`require_admin`（403）。

**为何服务端会话而非 JWT**：撤销即删行、无需密钥轮换、安全面小、易审查——贴合本机单机演示。

## 笔记存储与托管（私有/公开分流）

- **公开展示区**：现有 `web/public/notes/`（+ `web/public/videos/`）**不动**，继续 Next.js 静态托管。
  一个**幂等迁移脚本** `scripts/migrate_seed_public_notes.py` 扫已有目录 → 插 `notes` 行
  `visibility='public', owner_id=seed_admin`。可重跑（按 id upsert）。
- **私有笔记**：worker 改为发布到 `data/user_notes/{uid}/{note_id}/`（出公开目录，静态不可达）。
  视频也一并放进该私有目录（如 `video.mp4`），不再写 `web/public/videos/`。因此 **enqueue 必须携带
  user_id**，worker 据此选发布目标 + 插 `notes` 行 `visibility='private'`。
- **私有托管端点** `GET /api/notes/{id}/file/{path:path}`（**只服务私有笔记**；公开笔记继续走
  Next.js 静态，不绕 API）：
  - 查 `notes` 行确认 `visibility='private'` → `require_user` + owner 校验（非 owner / 未登录 / 笔记
    不存在 → 一律 **404**，不泄露存在性）→ 流式吐文件。
  - **视频支持 HTTP Range**（Plyr 拖拽 seek 需要 206 Partial Content）。
  - `path` 做越级校验（无 `..`、绝对路径、符号链接逃逸），只允许该 note 目录内。
- 前端 `web/lib/notes.ts::fetchNote`：私有笔记把资源 URL 指向该 API 端点（`credentials:'include'`，
  #1 已开 `allow_credentials`）；公开笔记沿用静态路径。

## API 变更

| 端点 | 变更 |
|---|---|
| `POST /api/generate` `/api/upload` | 加 `require_user`，注入 user_id 到 job opts；匿名 → 401 |
| `GET /api/jobs/{id}` `/events` | `require_user` + 仅 owner；他人 job → 404 |
| `GET /api/notes` | 拆为 `GET /api/notes/public`（开放）+ `GET /api/notes/mine`（鉴权，我的私有库）|
| `GET /api/history`（新） | 从 SQLite `jobs` 读我的全量提交（各状态，时间倒序）|
| `DELETE /api/notes/{id}` | 加鉴权：仅 owner（公开区仅 admin）；保留既有路径越级校验 |
| `POST /api/jobs/{id}/retry`（新） | 校验 owner → 用同 source/opts 重新 enqueue |
| `GET /api/auth/*`（新） | register / verify / login / logout / me |
| `GET /api/notes/{id}/file/*`（新） | 私有笔记鉴权托管（含视频 Range）|

**幂等 key 变更**：#1 的 `idempotency_key(source,opts)` 全局去重 → **加 user_id**，使两个用户提交
同一 URL 各得各自私有笔记，互不复用。

## 多用户队列

- 单一全局 FIFO 队列 + 并发=1 不变（串行 GPU 铁律，见 serial-model-loading 记忆）；各用户共享队列。
- **公平**：每用户**在飞 1 个**上限（已有 queued/running job 时第 2 个提交拒绝「你已有任务在处理中」），
  防单用户霸队。`queue_position` 仍报「前面还有 N 个」。
- worker 完成/失败时：更新 Redis（不变）**并**镜像写 SQLite `jobs` 终态 + `notes` 行（若 done）。

## 前端（Next.js）

- **Auth context**：打 `/api/auth/me` 初始化；受保护路由（`/library` `/history` 提交页）未登录跳 `/login`。
- **页面**：`/login`、`/register`、`/verify`（消费验证链接）；`/`（home）= 公开展示区；
  `/library` = 我的私有笔记（鉴权）；`/history` = 提交历史表（状态/时间/看笔记/重试）。
- **NavBar**：登出态显示登录/注册；登录态显示用户菜单 + 我的笔记/历史/登出。
- **笔记页** `/notes/[id]`：私有经鉴权 API 取数（cookie 自动带）；公开沿用静态。

## 错误处理与边界

- 未鉴权访问受保护 API → 401，前端跳 `/login`；访问他人 note/job → **404**（不泄露存在性）。
- 未验证登录 → 403「请先验证邮箱」+ 可重发链接；会话过期 → 401 → 重登。
- 迁移脚本幂等可重跑（按 note id upsert）。
- 并发=1 保持 + 每用户在飞 1 上限。
- **SQLite 并发**：api 与 worker 都写库 → 开 **WAL** + 短连接（每操作开关），worker 仅在状态转换写，
  量小无锁压力；`busy_timeout` 设几秒兜并发写。
- 私有文件托管：路径越级 / 符号链接逃逸严格拦截。
- bcrypt 校验对「邮箱不存在」也走一次假哈希比较，避免时序侧信道泄露用户是否存在（尽力，非强保证）。

## 测试与验收（沿用 `scripts/` assert 脚本风格，不碰 GPU）

- **单元（纯函数 / 临时 SQLite）**：密码 hash/verify；session 创建/查找/过期；`idempotency_key` 现按
  用户隔离；authz 判定（owner / 非 owner / admin）；邮箱验证 token 流（生成/消费/过期）；可见性过滤。
- **集成（fakeredis + 临时 SQLite，mock pipeline subprocess）**：注册→验证→登录→enqueue→SQLite 历史
  出行→（mock 完成）私有 note 行写入→非 owner 取 note 文件返回 404→公开 note 匿名可读；每用户在飞 1
  上限触发；幂等同用户同 URL 命中、不同用户不命中。
- **手动 e2e**：起 redis→api→worker→web；注册两个账号各自验证登录，各提交一个短视频
  （`--quality 360p` 省时），验证：各自只见自己的历史/私有库，公开展示区两人共享，私有笔记 URL
  换账号访问 404。

## 非目标（YAGNI，留后续子项目）

- OAuth / 社交登录；真 SMTP / 找回密码邮件（只 dev 链接）；改邮箱；2FA。
- 超出「每用户在飞 1」的限流 / 配额；分享链接（私有转公开链接，留 #4 产品向）。
- 对象存储（MinIO）——文件系统够用，`storage_path` 已为将来抽 storage 接口留口。
- user/admin 之外的细粒度 RBAC；多 worker / 横向扩容（#3）。

## 关联

- 依赖子项目 #1：`server.py`、`src/jobqueue.py`、`src/worker_tasks.py`、`src/service_common.py`、
  `web/lib/notes.ts`、`web/lib/api.ts`。
- serial-model-loading 记忆：并发=1 根本约束（多用户共享单队列）。
- env hypervisor-disabled 记忆：Docker 不可用 → 选 SQLite 而非 Postgres 容器。
- 实现分支待定（#1 在 `feature/service-hardening` 未合 main）：建议基于该分支新建
  `feature/multiuser-accounts`，由用户决策。
