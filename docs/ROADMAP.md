# NoteGen 路线图：先把项目做成真东西

> 2026-06-10 制定，2026-06-11 重排：答辩还有一年，论文相关全部推迟（阶段 A 移到最后）。
> 当前定位：一个能给人用、能写进简历、面试能讲 40 分钟的完整项目。
> 原则：每个阶段结束时项目都处于「可演示、可部署」状态，不留半成品分支。

## 已完成（2026-06-11）

前端 NotebookLM 风格重设计全量落地（landing / /notebooks 笔记本库 / 三栏工作台，
见 `docs/frontend-redesign.md`）；视频 QA 上线并端到端验证（BM25 + Qwen + 时间戳引用，
qa 高优队列）；后端服务层 7 处修复（SSE 轻量轮询、upload 配额前置、idem 时序等）。

2026-06-12 pipeline 质量升级：①平台元数据白捡（`src/platform_meta.py`）——创作者
CC 字幕直通跳过 ASR（AI 字幕默认仍走 whisper，`--use-auto-subs` 可开）、B 站分段/
YouTube 章节锚定切分（LLM 只做章内摘要/quiz）；②阶段 C#1 的 bge-m3 路线落地
（`src/embeddings.py`）——pipeline 末尾 chunk 向量落盘，QA 检索升级 BM25+dense
RRF hybrid（向量缺失回落 BM25），另送 `--chunker semantic` 供 benchmark 对比。

2026-06-14/15 产品闭环状态：阶段 C 前三项已经进入可用实现态——`ChatPanel`
视频问答接入 `/api/notes/{id}/ask`，Word 导出接入 `/api/export/docx`，公开分享
接入 `/s/{token}` 只读页与 share token API。当前最优先级不再是继续堆功能，而是
**v1 发布收敛**：清理/提交当前大批改动、同步文档、跑完整本地 smoke，并留下
可复现演示脚本。

## 当前优先级 · v1 发布收敛（现在）

| # | 事项 | 目标 |
|---|---|---|
| 1 | 工作树收敛 | 将当前服务硬化、前端重设计、QA/export/share、pipeline 质量升级、benchmark/docs 分组成可审阅提交；至少形成一个可回滚的 v1 checkpoint |
| 2 | 文档追平实现 | README、ROADMAP、frontend-redesign 不再把已落地功能写成 future work；补演示启动 checklist 与常见 503/Redis 说明 |
| 3 | 端到端 smoke | Redis + API + worker + web 全部启动后，验证注册登录、/notebooks、/notes、视频 seek、书签、导出、分享、QA、/history 诊断 |
| 4 | 演示资产 | 精修 3 张截图 + 1 个短 GIF/录屏；明确 `web/public/videos` 这类本地大素材不入库、不进镜像 |
| 5 | 发布记录 | 新增一次 memory/browser-validation 记录，作为下一轮开发的真实基线 |

## 阶段 B · 可用性硬化（答辩后 2–3 周）

让「能实际用」从口号变成事实。全部是已知短板，无技术风险，按序做：

| # | 事项 | 现状 → 目标 |
|---|---|---|
| 1 | ~~docker-compose 全栈~~ ✅ 2026-06-11 | redis 默认起（老流程不变）+ api/web 挂 `--profile full`（docker/Dockerfile.api 轻依赖镜像 + web/ 多阶段构建，notes/videos 用 volume 不进镜像）；worker 留宿主机跑 GPU；caddy 留注释待域名 |
| 2 | HTTPS + 域名 | dev cookie 明文 → Caddy 自动证书，`NOTEGEN_COOKIE_SECURE=1`（待有域名/公网入口再做） |
| 3 | ~~真邮件验证~~ ✅ 2026-06-11 | `src/mailer.py`：配 `NOTEGEN_SMTP_*` 走 SMTP_SSL（QQ/163 授权码），未配置维持控制台 fallback |
| 4 | ~~失败任务与磁盘治理~~ ✅ 2026-06-11 | `src/maintenance.py`：server 启动后每日清 7 天前 raw/audio + 孤儿上传（24h 宽限，活跃 job 受保护；outputs 是论文产物不碰）；磁盘 <15% → generate/upload 507，/api/health 暴露 disk；手动 `scripts/run_maintenance.py --dry-run` |
| 5 | ~~监控与日志~~ ✅ 部分 2026-06-11 | loguru 结构化日志（logs/server.log、worker.log 轮转，未装回落 stdlib）+ `run_worker_forever.ps1` 崩溃自动重启（指数退避）。Uptime Kuma 待公网部署再加 |
| 6 | ~~备份~~ ✅ 2026-06-11 | `src/backup.py`：SQLite 在线快照 + user_notes + web/public/notes 每日打 zip 滚动留 7（默认不含视频）；`NOTEGEN_BACKUP_DIR` 指第二块盘；手动 `scripts/run_backup.py`，`NOTEGEN_AUTO_BACKUP=0` 关 |
| 7 | ~~安全收尾~~ ✅ 2026-06-11 | `src/ratelimit.py` 内存滑动窗口（零依赖，弃 slowapi）：登录 10/分、注册 10/10 分按 IP 429；上传上限 4096MB（头预检+计数双保险 413）；bcrypt rounds=12 显式钉死 |

**出口标准**：连续 14 天无人工干预正常服务；拔电重启后 5 分钟内全栈自愈。

## 阶段 C · 亮点功能（按「简历价值 ÷ 工作量」排序）

1. **~~视频 QA（时间戳引用）~~ ✅** — NotebookLM 的灵魂功能已落地：pipeline 末尾落 bge-m3 chunk 向量；QA 检索 BM25+dense RRF，缺向量回落 BM25；Qwen 生成强制引用 chunk 时间戳；RQ `qa` 高优队列与单 worker 串行避免抢 GPU。
2. **~~导出 docx~~ ✅** — `web/lib/export.ts` 构造 Markdown，`POST /api/export/docx` 复用 `scripts/md_to_docx.py` 转 Word。PDF 暂不做，避免引入排版/字体复杂度。
3. **~~公开分享链接~~ ✅** — `note_shares` token + `/s/{token}` 只读页已落地；撤销分享后链接立即失效。
4. **Audio Overview 彩蛋** — 章节摘要 → edge-tts 合成双人对话播客。工作量小、演示惊艳，但先等 v1 收敛和 smoke 完成。

## 阶段 D · 工程素养（穿插做，每项 ≤ 半天）

GitHub Actions CI（`tsc --noEmit` + 不依赖 GPU 的 pytest 子集：jobqueue / accounts / userdata / service_common / qa）；README 配英文版；CHANGELOG 与版本号；首页放 3 张精修截图 + 1 个 GIF。

## 阶段 A · 论文（推迟：距答辩约一年，临近前 2-3 个月再启动）

论文 `paper/draft.md` 转 LaTeX 定稿；附录 B / §6.4 用 `aggregate_eval.py` 最后刷一遍；
3 分钟 demo 视频；届时项目本体已远超 draft 描述的范围（QA、在线服务、重设计前端都是
新增素材），写作时记得把这些补进系统与评估章节。

## 明确不做的事

多租户计费、K8s、横向扩展 worker、对象存储上云。单 GPU 机 + 单 worker 串行排队是当前产品形态的前提假设（论文 §7 也是这么写的），过早抽象只会拖慢 A/B/C 三个阶段。等真有并发需求，瓶颈也在 GPU 而不在架构。

## 里程碑

| 时间 | 节点 |
|---|---|
| 6 月中 | P0/P1 + 阶段 B + 阶段 C1-C3 已基本落地；进入 v1 收敛 |
| 下一步 | 清理提交、文档追平、完整本地 smoke、截图/GIF |
| 有公网入口后 | HTTPS + 域名 + Uptime Kuma |
| 暑期 | QA 质量打磨 / Audio Overview / 简历作品集包装 |
