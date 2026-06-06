# 设计：notegen 从 dev 原型升级为企业级任务队列服务（方案 A：Redis + RQ）

日期：2026-06-07
状态：设计待评审
分支：`feature/service-hardening`

## 背景与动机

notegen 现状是「本机 CLI 跑管线 → 静态托管结果」的 demo，但仓库根目录的 `server.py`
其实已经是一个**dev 级的在线服务原型**：FastAPI 暴露 `/api/generate`、`/api/upload`、
`/api/probe`、`/api/jobs/{id}`、`/api/jobs/{id}/events`(SSE)、`/api/notes`，前端
(`web/lib/notes.ts::fetchNote`) 也已接上。

本项目的目标是把这个 dev 原型**硬化成企业级在线服务**：用户在线提交 → 异步处理 →
拿到笔记。部署野心限定为「**本机/单 GPU，重架构演示**」——worker 跑在现有 GPU 机器，
重点是把企业级架构模式（队列/并发控制/持久化/重试/幂等/可观测）做正确，而非真扛大流量。

这是「企业级 notegen」整体路线图的**子项目 #1（服务骨架）**。后续 #2 多用户/账号、
#3 工程基建/部署、#4 产品向功能，各自独立 spec → plan → 实现。

## 现状弱点（server.py 体检）

| 现状 | 缺口 | 严重度 |
|---|---|---|
| Job 状态全在内存 `_jobs` dict（注释自承「重启丢失」） | 进程重启/崩溃 → 任务记录蒸发 | 高 |
| 每请求 `threading.Thread` 直接跑、无并发控制 | 同时两请求 → 两份 7B 模型抢同一 GPU → 黑屏/花屏崩溃 | 严重（真 bug） |
| subprocess + 解析 stdout `[N/4]` 模糊匹配 | 脆弱；`run()` 干净的 18-stage 接缝没用上 | 中 |
| 无重试 / 无幂等 / 无失败留痕 | 任务挂了只能重提；同 URL 重复算 | 中 |

**前置已完成**：并发崩溃 bug 已在 commit `6744d69` 用模块级 `Semaphore(1)` 临时封堵
（`_run_pipeline` 抢闸 → `_run_pipeline_impl`），作为「并发=1 最小队列」。本项目用
Redis+RQ 正式替换它。

## 目标架构

```
[Next.js web] --POST /api/generate--> [FastAPI api 进程]
                                            | enqueue (RQ)
                                            v
                                       [Redis]  ← 队列 + job 状态/进度（AOF 持久化）
                                            ^
                                            | 消费（并发=1：单 worker）
                                       [RQ SimpleWorker 进程 @ GPU 机器]
                                            | subprocess（崩溃隔离）
                                            v
                                  [pipeline.py run() 18 stages]
                                            | 结构化 progress marker → stdout
                                            v
                              data/outputs → _publish_to_web → web/public/notes/{id}
[Next.js web] <--SSE /api/jobs/{id}/events-- [api 读 Redis 进度]
```

**保留**已验证好用的部分：pipeline 跑 subprocess、output-fallback 兜底、`_publish_to_web` 链路、SSE 进度形态、前端 `fetchNote`。

## 关键技术决断

### A. Windows worker：RQ `SimpleWorker`（不 fork）+ subprocess pipeline（已确认保留）
标准 RQ 靠 `os.fork()`，Windows 无。用 `rq.worker.SimpleWorker`（同进程消费、不 fork）。
pipeline 仍以 subprocess 执行——其 PyTorch/ctranslate2 在 Windows 退出时偶发 crash
（exit code 3221226505，现有代码靠「扫 data/outputs 兜底」处理），subprocess 隔离保证
worker 本体不被带崩。**不改成 in-process import `run()`**：隔离价值 > 回调干净度。

### B. 部署粒度：混合（已确认）
Windows 上 GPU 透传进 Docker 很痛。**Redis 跑 Docker（一条命令），api / worker / web
原生跑**（本就配好原生环境，worker 直接吃 GPU）。全容器化留到子项目 #3（Linux 云）。

### C. 并发=1 由「单 worker 进程」保证
取代信号量。只起一个 SimpleWorker 进程消费默认队列，天然串行，契合「大模型串行加载」铁律。

## 组件

1. **`src/jobqueue.py`（新建）**：Redis 连接 + RQ `Queue` 封装；`enqueue_generate(url, opts) -> job_id`；
   `job_state(job_id) -> dict`；幂等 key 计算 `idempotency_key(url, opts)`；progress 读写
   helper（`job:{id}` Redis hash：stage/percent/msg/note_id/log[]/events[]）。
2. **`src/worker_tasks.py`（新建）**：RQ 任务函数 `run_generate(job_id, source, opts)`——
   等价于现 `_run_pipeline_impl`，但进度写 Redis（而非内存 `_emit`）。复用 `_publish_to_web`、
   output-fallback、duration 估时、`_adaptive_chunk_chars`、`_normalize_quality`（从 server.py 提取为可复用模块）。
3. **`server.py`（改造）**：`/api/generate`、`/api/upload` 改为 `enqueue` 到 RQ（删 `threading.Thread`
   与 `_PIPELINE_GATE`）；`/api/jobs/{id}`、`/events` 改为读 Redis；其余端点不变。
4. **`pipeline.py`（小改）**：`run()` 的 18-stage 循环每跑完一个 stage `print` 一行
   **机器可读 marker**：`[PROGRESS] {"stage":"asr","i":4,"n":18,"msg":"..."}`。替换 worker 端
   脆弱的 `[N/4]` 模糊匹配。stage 名取自函数名映射表。不改 `run()` 签名（marker 走 stdout，
   subprocess 边界友好）。
5. **worker 启动脚本 + `docker-compose.yml`（新建）**：compose 只含 `redis`（开 AOF）；
   `scripts/run_worker.py` 起 SimpleWorker；README 记 `redis up → api → worker → web` 启动顺序。

## 数据流

1. **提交**：`POST /api/generate {url,quality}` → 算 `idempotency_key` → 查 Redis：已有完成
   note 或 in-flight job → 返回该 job_id（幂等命中，不重复算）；否则 `enqueue` + 写 `job:{id}`
   hash（stage=queued）→ 返回 job_id。`/api/upload` 同理（先落盘 data/raw 再 enqueue local 模式）。
2. **消费**：SimpleWorker 取 job → `run_generate` → subprocess `pipeline.py` → 读 stdout 的
   `[PROGRESS]` marker + 原有 `[asr]`/`[pegasus]`/`[clip]` 细粒度行 → 写 Redis job hash。
3. **进度**：`GET /api/jobs/{id}/events` SSE → api 轮询 Redis job hash 的 events 增量推前端（形态同现状）。
4. **完成**：worker `_publish_to_web(stem)` → 写 note_id、stage=done → 前端跳 `/notes/{note_id}`。
5. **队列位置**：`/api/jobs/{id}` 额外返回「前面还有 N 个」（RQ queue 中该 job 之前的数量）。

## 错误处理与边界

- **transient（下载/网络失败）**：RQ `Retry(max=2, interval=[10,30])` 自动重试。
- **致命（视频损坏/pipeline 真错）**：stage=failed + reason + 末 50 行 log 入 Redis，不重试；
  前端「重试」按钮 = 重新 enqueue 同 key。
- **pipeline crash 但产物完整**（Windows cleanup exit 3221226505）：**保留**现有扫 `data/outputs`
  兜底逻辑 → 文件在就 publish，stage=done 并附 returncode 说明。
- **worker 进程崩**：Redis 持久化 → 重启 worker 后队列任务不丢；正在跑的 job 标记 `interrupted`，可手动重提。
- **Redis 不可用**：api enqueue 抛错 → 返回 503 + 友好提示；前端提示稍后再试。`/api/health` 增报 Redis 连通性 + 队列深度。
- **重复提交同 URL**：幂等 key 命中 → 返回已有 job/note。
- **path 安全**：`/api/notes/{id}` 删除已有的越级校验（无 `/`、`\`、`..`）保留。

## 测试与验收（项目无 pytest 约定，沿用 scripts/ assert 脚本风格）

- **单元**：`idempotency_key` 稳定性、`[PROGRESS]` marker 解析、job 状态机转换（queued→running→done/failed）——纯函数 assert。
- **集成（不碰 GPU）**：mock pipeline subprocess（替换 `run_generate` 内的 subprocess 调用为
  假实现，如本项目验证信号量时的手法），验 enqueue→worker→Redis 状态→done 全链路、幂等命中、
  重试触发、并发=1 串行（起两 worker job 验最大并发 1）。
- **手动 e2e**：`docker compose up redis` → api → worker → web；提交一个短视频（`--quality 360p` 省时）
  看进度推进到笔记；并发提交两个验证第二个「前面还有 1 个」并串行执行。

## 非目标（YAGNI，留给后续子项目）

- 账号 / 多用户 / 登录 / 每人笔记库（子项目 #2）
- 对象存储（MinIO）——文件系统够用，但 `_publish_to_web` 后续可抽 storage 接口
- k8s / 多 worker / GPU 自动扩容 / Prometheus-Grafana（子项目 #3）
- 云部署、公网鉴权限流（子项目 #3）
- Redis pub/sub 实时推送——先沿用 SSE + Redis 轮询，够用

## 关联

- 现有 `server.py`（dev 原型）、`src/pipeline.py`（`run()` + `_STAGES` 18 阶段 + `PipelineConfig/State`）
- [[feedback-serial-model-loading]]：大模型严格串行——并发=1 的根本约束
- [[feedback-low-quality-for-eval]]：跑批/验证用 `--quality 360p`
- commit `6744d69`：并发=1 信号量临时补丁（本项目正式替换它）
