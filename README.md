# NoteGen — 视频学习笔记生成与问答系统

[![CI](https://github.com/lsdragst-a11y/notegen/actions/workflows/ci.yml/badge.svg)](https://github.com/lsdragst-a11y/notegen/actions/workflows/ci.yml)

提交一个视频链接（B 站 / YouTube / 本地文件），NoteGen 自动产出**带时间戳跳转的结构化学习笔记**，并提供 NotebookLM 风格的三栏学习工作台：章节导航 + 逐字稿、知识点笔记、视频联动播放，外加**基于笔记内容的多轮问答**（答案带时间戳引用，点击跳转视频）。

支持中英双语切换、导出 Markdown / Word、免登录分享链接、书签与学习进度。

> 本项目同时是一篇毕业论文的实证 codebase（论文 draft 在 `paper/draft.md`，已推迟至答辩前定稿）。路线图见 [docs/ROADMAP.md](docs/ROADMAP.md)。

## 功能

- **结构化笔记**：摘要卡、按章节组织的知识点速览（带时间戳）、术语表、章末小结、每章关键帧
- **三栏工作台**：左栏「章节｜逐字稿」（逐字稿随播放高亮、章节带学习进度勾选）、中栏笔记 + 问答面板、右栏视频（章节 chip、倍速记忆、画中画）
- **视频问答**：BM25 + bge-m3 向量 hybrid 检索（RRF 融合，向量缺失自动回落 BM25）+ Qwen 生成，强制时间戳引用，支持多轮追问与推荐问题；模型在 worker 内常驻，首问冷加载后秒级响应
- **平台元数据白捡**：创作者上传的 CC 字幕存在时直接采用、跳过 ASR（零 WER 零 GPU 时间，AI/自动字幕默认仍走 whisper）；B 站分段 / YouTube 章节存在时切分边界与标题直接锚定，LLM 只做章内摘要/quiz（`--no-platform-subs` / `--no-platform-chapters` 可关）
- **多模态章节切分**：Qwen2.5-VL 视觉 caption 以自然语言喂给 segment LLM，三层自适应 gate 防 PPT 翻页误判；LLM 失败自动回退 TextTiling；另有 `--chunker semantic`（bge-m3 句向量）可与 TextTiling 对比评测
- **ASR 两层修复**：视频 metadata 自动构建术语字典 + LCP 连续重复段去重（处理 faster-whisper 卡片回路失败模式）
- **双语输出**：ASR 后验语言校正 + Qwen 翻译填 `_zh`/`_en` 字段，前端一键切换
- **导出与分享**：导出 Markdown / Word（docx）；生成免登录只读分享链接 `/s/{token}`，可随时撤销
- **多用户**：注册（邮箱验证）/ 登录、私有笔记鉴权托管、书签分类、任务历史与失败重试

## 架构

```
┌─ 离线 pipeline（GPU 子进程，worker 串行调度）─────────────────────┐
│ yt-dlp 下载 → ffmpeg 抽音频 → faster-whisper large-v3 ASR        │
│   → 术语修正 + LCP 去重 → chunk（字符 / TextTiling）             │
│   → Chinese-CLIP 关键帧 + Qwen2.5-VL caption（三层 gate）        │
│   → Qwen2.5-7B-AWQ 层级章节切分（retry + repair，回退 TextTiling）│
│   → 章节标题/摘要 + 双语翻译 → 结构化笔记 JSON + Markdown        │
└──────────────────────────────────────────────────────────────────┘
┌─ 在线服务 ────────────────────────────────────────────────────────┐
│ server.py（FastAPI :8000）── SQLite（users/notes/jobs/shares…）  │
│       │ enqueue                                                   │
│ Redis/RQ 双队列（qa 高优 + default）── run_worker.py 单 worker   │
│   （单 worker = 并发 1，守住单 GPU 串行铁律；QA 模型常驻，       │
│     跑 pipeline 前自动卸载让出 VRAM）                             │
└──────────────────────────────────────────────────────────────────┘
┌─ 前端（web/，Next.js App Router :3000）──────────────────────────┐
│ / 营销页 · /notebooks 笔记本库 · /notes/[id] 工作台              │
│ /s/[token] 分享只读页 · /generate 提交 · /history · /bookmarks   │
└──────────────────────────────────────────────────────────────────┘
```

## 快速开始

### 环境要求

- Windows 11 + NVIDIA GPU（已在 RTX 4080 Laptop / 12GB VRAM 验证）；Linux 理论可行未测
- Python 3.10、Node.js 18+、Docker Desktop（仅跑 Redis）、ffmpeg（PATH 可调用）
- 浏览器登录态供 yt-dlp 借 cookies（B 站 / YouTube 反爬）

### 安装

```powershell
# 1. Python venv + 依赖
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# PyTorch 按 CUDA 版本单独装：
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# 2. 模型本地副本（默认从 hf-mirror.com 下载到 models/，约 18GB）
#    Qwen2.5-7B-Instruct-AWQ / Qwen2.5-VL-7B-Instruct-AWQ /
#    faster-whisper-large-v3 / chinese-clip-vit-base-patch16
#    可选 bge-m3（QA hybrid 检索 + 语义切分，缺失自动回落 BM25/TextTiling）：
#    HF_ENDPOINT=https://hf-mirror.com huggingface-cli download BAAI/bge-m3 --local-dir models/bge-m3

# 3. 前端依赖
cd web; npm install
```

### 启动（4 个组件，按序）

```powershell
docker compose up -d redis                  # 1. Redis（队列后端，AOF 持久化）
.\.venv\Scripts\python.exe server.py        # 2. API → http://127.0.0.1:8000
.\.venv\Scripts\python.exe scripts\run_worker.py   # 3. Worker（GPU 机器，只起一个）
cd web; npm run dev                         # 4. Web → http://localhost:3000
```

打开 `http://localhost:3000` 注册账号（验证链接打印在 API 控制台），提交视频链接即可。

- 健康检查：`GET /api/health` 返回 `{ok, redis, queue_depth}`
- Redis 未起时 `/api/generate` 返回 503，起好后重试即可
- **不要起多个 worker**：单 worker 串行是单 GPU 形态的前提假设

### 演示前 checklist

按下面顺序确认一遍，基本就能避免现场翻车：

1. `docker compose up -d redis` 后访问 `http://127.0.0.1:8000/api/health`，确认 `redis=true`、`disk.low=false`。
2. API 控制台启动后注册一个测试账号；未配置 SMTP 时，复制控制台打印的 `/verify?token=...` 链接完成验证。
3. 只启动一个 worker：`.\.venv\Scripts\python.exe scripts\run_worker.py`。看到 `监听 qa + default 队列` 即可。
4. 前端 `cd web; npm run dev` 后打开 `http://localhost:3000/notebooks`，确认能看到公开示例和「新建笔记本」入口。
5. 打开一个已有笔记，检查视频章节跳转、逐字稿高亮、书签、Markdown/Word 导出、分享链接 `/s/{token}`。
6. 登录状态下问一个问题；若排队提示 GPU 忙，等当前 pipeline/QA 结束即可。Redis 未起或连不上时问答/生成会返回 503。
7. 到 `/history` 看任务诊断；失败任务应显示阶段、日志尾部、重试入口。

常见故障：

- `503 队列服务暂不可用`：Redis 没启动或 `NOTEGEN_REDIS_URL` 指错。
- `507 磁盘空间不足`：`NOTEGEN_MIN_FREE_RATIO` 水位触发，先清理 raw/audio/videos 或降低阈值。
- 登录后仍显示服务离线：确认 API 在 `127.0.0.1:8000`，前端 `NEXT_PUBLIC_API_URL` 没烧错。
- GPU OOM：确认没有第二个 worker，也没有其它进程常驻大模型。

### 不起服务，直接跑单视频

```powershell
.\.venv\Scripts\python.exe src/pipeline.py "https://www.bilibili.com/video/BV1xxxx" `
    --summarizer neural --chunker texttile --chunk-chars 800 `
    --chapters --keyframes --mm-alpha 0.3 `
    --llm-chapters --vlm-captions
```

输出在 `data/outputs/<video_id>.large-v3.neural.texttile.mm.vl.md`。

## API 概览

| 分组 | 端点 |
|---|---|
| 认证 | `POST /api/auth/register` · `GET /api/auth/verify` · `POST /api/auth/login` · `GET /api/auth/me` · 登出 |
| 任务 | `POST /api/probe`（画质探测）· `POST /api/generate` · `POST /api/upload` · `GET /api/jobs/{id}` · `GET /api/jobs/{id}/events`（SSE 进度）· `GET /api/history` · `POST /api/jobs/{id}/retry` |
| 笔记 | `GET /api/notes/public` · `GET /api/notes/mine` · `GET /api/notes/{id}/file/{path}`（私有鉴权托管）· `DELETE /api/notes/{id}` |
| 问答 | `POST /api/notes/{id}/ask`（多轮 history）→ `GET /api/qa/{qa_id}` 轮询 |
| 分享 | `POST/GET/DELETE /api/notes/{id}/share` · `GET /api/shared/{token}[/file/{path}]`（免登录） |
| 导出 | `POST /api/export/docx`（markdown → Word，免登录） |
| 书签 | `GET/PUT/DELETE /api/bookmarks` · 分类 CRUD |
| 运维 | `GET /api/health` |

接口契约细节（QA 状态机等）见 `docs/frontend-redesign.md` §5。

## 目录结构

```
notegen/
├── server.py            FastAPI 后端（鉴权/任务/笔记/问答/分享/导出）
├── src/
│   ├── pipeline.py      离线 pipeline 串联入口
│   ├── download.py / asr.py / summarize.py / segment_llm.py
│   │                    下载 → ASR 修复 → chunk → LLM 章节切分（粒度旋钮在
│   │                    segment_llm.py 顶部常量块）
│   ├── keyframe.py / caption_vl.py   CLIP 关键帧 + VL caption 三层 gate
│   ├── qa.py            视频问答（BM25 jieba 检索 + Qwen 生成 + 引用校验）
│   ├── jobqueue.py      Redis/RQ 双队列（qa 高优 + default）、job/qa 状态机
│   ├── worker_tasks.py  worker 进程任务体（QA 模型常驻 / VRAM 互斥）
│   ├── db.py / accounts.py / authdeps.py / userdata.py
│   │                    SQLite + 注册登录会话 + notes/jobs/bookmarks/shares 仓储
│   └── service_common.py / object_store.py   路径与产物 publish
├── scripts/
│   ├── run_worker.py    RQ worker 入口（监听 qa + default 两队列）
│   ├── md_to_docx.py    markdown → Word 转换器（导出接口复用，无 pandoc）
│   ├── test_*.py        单测（无 GPU 子集进 CI，见下）
│   └── eval_*.py / aggregate_eval.py   论文评估脚本
├── web/                 Next.js 前端（NotebookLM 风格三栏工作台）
├── docs/                ROADMAP.md · frontend-redesign.md
├── paper/               论文 draft 与自动生成的评估表
├── data/                （gitignored）raw / outputs / user_notes / redis
└── models/              （gitignored）本地模型副本 ~18GB
```

## 测试与 CI

无 GPU、无真 Redis 即可跑的单测子集（fakeredis + 临时 SQLite + TestClient）：

```powershell
.\.venv\Scripts\python.exe scripts\test_service_common.py
.\.venv\Scripts\python.exe scripts\test_jobqueue.py
.\.venv\Scripts\python.exe scripts\test_qa_unit.py
.\.venv\Scripts\python.exe scripts\test_accounts_unit.py
.\.venv\Scripts\python.exe scripts\test_userdata_unit.py
.\.venv\Scripts\python.exe scripts\test_shares_unit.py
.\.venv\Scripts\python.exe scripts\test_auth_api.py
.\.venv\Scripts\python.exe scripts\test_export_unit.py
.\.venv\Scripts\python.exe scripts\test_maintenance_unit.py
.\.venv\Scripts\python.exe scripts\test_ratelimit_unit.py
.\.venv\Scripts\python.exe scripts\test_mailer_unit.py
.\.venv\Scripts\python.exe scripts\test_backup_unit.py
.\.venv\Scripts\python.exe scripts\test_platform_meta_unit.py
.\.venv\Scripts\python.exe scripts\test_retrieval_hybrid_unit.py
.\.venv\Scripts\python.exe scripts\test_votefix_unit.py
.\.venv\Scripts\python.exe scripts\test_quality_filters_unit.py
.\.venv\Scripts\python.exe scripts\test_hardening_api.py
cd web; npx tsc --noEmit
```

GitHub Actions（`.github/workflows/ci.yml`）在每次 push / PR 时跑同样的子集 + 全量 `py_compile` + 前端类型检查。GPU 路径（pipeline / QA 生成）无法在 runner 上验证，靠本机手测。

## 运维（阶段 B 硬化）

- **磁盘治理**：server 启动后每日自动清 `data/raw`、`data/audio` 中超过 7 天的文件，
  以及无活跃任务引用的本地上传（24h 宽限）；`data/outputs` 是论文 benchmark 产物，刻意不碰。
  手动触发：`python scripts/run_maintenance.py [--dry-run]`。
  磁盘剩余 <15% 时 `/api/generate`、`/api/upload` 返回 507 拒单，`/api/health` 带 `disk` 字段
- **限速**：登录 10 次/分、注册 10 次/10 分（按 IP，内存滑动窗口，429 + Retry-After）
- **上传上限**：默认 4096MB，Content-Length 预检 + 落盘计数双保险（413）
- **邮件验证**：配齐 `NOTEGEN_SMTP_*` 走真邮件（QQ：`smtp.qq.com:465` + 授权码），
  未配置维持 dev 行为——验证链接打印在 API 控制台
- **日志**：loguru 写 `logs/server.log`、`logs/worker.log`（10MB 轮转留 10 份；未装 loguru 自动回落 stdlib logging）
- **worker 守护**：`powershell -ExecutionPolicy Bypass -File scripts\run_worker_forever.ps1`
  崩溃自动重启（指数退避 5s→60s），记录在 `logs/worker_restarts.log`
- **备份**：server 每日把 SQLite（在线快照）+ `data/user_notes` + `web/public/notes`
  打包成 zip 滚动留 7 份，默认排除视频；建议 `NOTEGEN_BACKUP_DIR` 指到第二块盘。
  手动：`python scripts/run_backup.py [--include-videos]`。
  恢复：解压后 `notegen.db` 放回 `data/`，`user_notes/` → `data/user_notes/`，`web_notes/` → `web/public/notes/`
- **compose 全栈**：`docker compose --profile full up -d --build` 一键起 redis + api + web
  （worker 留宿主机跑 GPU，连 `127.0.0.1:6379` 无需改动）；`docker compose up -d redis` 老流程不变。
  局域网他机访问：构建时传 `NEXT_PUBLIC_API_URL=http://<宿主机IP>:8000`，api 配 `NOTEGEN_CORS_ORIGINS`

## 配置（环境变量）

| 变量 | 默认 | 说明 |
|---|---|---|
| `NOTEGEN_REDIS_URL` | `redis://127.0.0.1:6379/0` | 队列后端 |
| `NOTEGEN_DB_PATH` | `data/notegen.db` | SQLite 路径 |
| `NOTEGEN_COOKIE_SECURE` | `0` | 生产置 1（HTTPS 下 Secure cookie） |
| `NOTEGEN_VERIFY_BASE` | `http://localhost:3000` | 邮箱验证链接 base |
| `NOTEGEN_SMTP_HOST` / `_PORT` / `_USER` / `_PASS` / `_FROM` | 未配置 | SMTP 发信（PORT 默认 465，FROM 默认同 USER，PASS 填授权码） |
| `NOTEGEN_LOGIN_LIMIT` / `NOTEGEN_REGISTER_LIMIT` | `10/60` / `10/600` | 限速「次数/秒窗口」 |
| `NOTEGEN_MAX_UPLOAD_MB` | `4096` | 上传大小上限 |
| `NOTEGEN_RAW_RETENTION_DAYS` | `7` | raw/audio 保留天数 |
| `NOTEGEN_AUTO_MAINTENANCE` | `1` | 置 0 关闭每日自动清理（raw 里有要长留的素材时） |
| `NOTEGEN_AUTO_BACKUP` | `1` | 置 0 关闭每日自动备份 |
| `NOTEGEN_BACKUP_DIR` / `_KEEP` / `_INCLUDE_VIDEOS` | `backups/` / `7` / `0` | 备份目录（建议第二块盘）/ 滚动份数 / 是否含视频 |
| `NOTEGEN_CORS_ORIGINS` | 空 | 逗号分隔的额外放行来源（局域网他机访问前端时） |
| `NOTEGEN_MIN_FREE_RATIO` | `0.15` | 磁盘水位线（低于即拒单） |
| `NOTEGEN_LOG_LEVEL` | `INFO` | 日志级别 |
| `NEXT_PUBLIC_API_URL`（web） | `http://localhost:8000` | 前端指向的 API |

## 已知局限

- 单 GPU + 单 worker 串行排队是当前产品形态的前提（多租户/横向扩展明确不做，见 ROADMAP）
- ASR 同音字隐式错字是自动指标盲区；英文长视频上 LLM 切分偶发 catch-all（自动回退 TextTiling 兜底）
- Windows 上 faster-whisper 退出阶段偶发 `STATUS_FATAL_APP_EXIT`，批量脚本带 retry-once 兜底
- 未配置 SMTP 时邮箱验证链接打印在控制台（dev 模式）

## 开源声明

代码、benchmark gold 标注、评估脚本开源。视频原始素材受版权保护，benchmark 列表（BV 号 / YouTube ID）在 `paper/draft.md` 附录供独立复现。
