# notegen 服务队列升级 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 notegen 的 dev 原型 `server.py`（内存 job 状态 + `threading.Thread` + 信号量）硬化为 Redis+RQ 在线任务队列服务：提交 URL/文件 → 异步处理 → 拿笔记。

**Architecture:** FastAPI（api 进程）`enqueue` 到 RQ → Redis（队列 + job 状态/进度，AOF 持久化）→ 单个 RQ `SimpleWorker`（不 fork，Windows 友好；并发=1 由单 worker 天然保证）消费 → subprocess 跑 `pipeline.py`（崩溃隔离）→ 结构化 `[PROGRESS]` marker 写回 Redis → 前端 SSE 读 Redis 进度。Redis 跑 Docker，api/worker/web 原生跑（混合部署）。

**Tech Stack:** Python 3 / FastAPI / RQ (SimpleWorker) / redis-py / fakeredis（测试）/ Docker Compose（仅 redis）。测试沿用项目 `scripts/test_*.py` assert 脚本风格（无 pytest），用 `.venv/Scripts/python.exe` 跑。

**Spec:** `docs/superpowers/specs/2026-06-07-notegen-service-queue-design.md`

**Branch:** `feature/service-hardening`（已含 commit `6744d69` 信号量补丁 + `8952d7a` spec）

---

## File Structure

新建：
- `src/progress.py` — `[PROGRESS]` marker 的 stage 标签表 + emit（pipeline 用）+ parse/interpolate（worker 用）。纯函数，无重依赖。
- `src/service_common.py` — 从 `server.py` 提取的可复用 helper（路径常量 + `normalize_quality` / `adaptive_chunk_chars` / `estimate_pipeline_seconds` / `probe_duration` / `publish_to_web`）。被 server.py 与 worker_tasks.py 共用。
- `src/jobqueue.py` — Redis 连接 + RQ Queue 封装；job hash 读写（`job:{id}`）；事件/日志 list；`idempotency_key`；`enqueue_generate`；`queue_position`。
- `src/worker_tasks.py` — RQ 任务 `run_generate(job_id, source, opts)`：spawn pipeline subprocess、解析 stdout 写 Redis、output-fallback、publish、状态机收尾。
- `scripts/run_worker.py` — 起单个 `SimpleWorker` 消费 default 队列。
- `docker-compose.yml` — 仅 `redis`（开 AOF）。
- 测试：`scripts/test_progress_marker.py`、`scripts/test_jobqueue.py`、`scripts/test_worker_integration.py`。

修改：
- `requirements.txt` — 加 `rq` / `redis` / `fakeredis`。
- `src/pipeline.py` — `run()` 的 18-stage 循环每个 stage 前 emit `[PROGRESS]` marker（不改 `run()` 签名）。
- `server.py` — `/api/generate`、`/api/upload` 改 enqueue；`/api/jobs/{id}`、`/events` 改读 Redis；`/api/health` 加 Redis/队列深度；删 `_jobs`/`_jobs_lock`/`_PIPELINE_GATE`/`_run_pipeline`/`_run_pipeline_impl`/`_emit` 与已搬到 service_common 的 helper。
- `README.md`（或新建片段）— 记 `redis → api → worker → web` 启动顺序。

---

## Task 1: 依赖 + Redis 容器 + 连通性

**Files:**
- Modify: `requirements.txt`
- Create: `docker-compose.yml`

- [ ] **Step 1: 在 requirements.txt 追加队列依赖**

在 `requirements.txt` 末尾（`pyyaml` 之后）追加：

```text

# 在线任务队列（service-hardening 子项目）
rq>=1.16,<2.0
redis>=5.0,<6.0
fakeredis>=2.20  # 仅测试用：无需真 Redis 跑集成断言
```

- [ ] **Step 2: 安装依赖**

Run: `.venv/Scripts/python.exe -m pip install "rq>=1.16,<2.0" "redis>=5.0,<6.0" "fakeredis>=2.20"`
Expected: 成功安装；`Successfully installed rq-... redis-... fakeredis-...`

- [ ] **Step 3: 验证可导入**

Run: `.venv/Scripts/python.exe -c "import rq, redis, fakeredis; from rq import SimpleWorker, Queue, Retry; print('ok', rq.__version__)"`
Expected: 打印 `ok 1.x.x`，无 ImportError。

- [ ] **Step 4: 写 docker-compose.yml**

Create `docker-compose.yml`:

```yaml
# 子项目 #1 只容器化 Redis（一条命令起队列后端）。api / worker / web 原生跑——
# worker 要直吃本机 GPU，Windows 下 GPU 透传进容器很痛，全容器化留到子项目 #3。
services:
  redis:
    image: redis:7-alpine
    # 开 AOF 持久化：worker/进程重启后队列与 job 状态不丢
    command: ["redis-server", "--appendonly", "yes"]
    ports:
      - "6379:6379"
    volumes:
      - ./data/redis:/data
    restart: unless-stopped
```

- [ ] **Step 5: 起 Redis 并验证连通**

Run: `docker compose up -d redis`
Then: `.venv/Scripts/python.exe -c "import redis; r=redis.Redis.from_url('redis://127.0.0.1:6379/0'); print(r.ping())"`
Expected: `docker compose` 拉起 redis 容器；ping 打印 `True`。
（若环境无 Docker：用任意本机 Redis 亦可；连通性命令返回 True 即过。）

- [ ] **Step 6: Commit**

```bash
git add requirements.txt docker-compose.yml
git commit -m "build(service): 加 rq/redis/fakeredis 依赖 + 仅-redis 的 docker-compose（AOF）"
```

---

## Task 2: pipeline `[PROGRESS]` marker + 解析器

**Files:**
- Create: `src/progress.py`
- Modify: `src/pipeline.py:1500-1549`（`_STAGES` 后、`run()` 循环内）
- Test: `scripts/test_progress_marker.py`

机器可读 marker 形如 `[PROGRESS] {"stage":"asr","label":"语音识别","i":4,"n":18}`，替换 worker 端脆弱的 `[N/4]` 模糊匹配。stage key 取自函数名（去 `_stage_` 前缀），label 取自映射表。worker 用 `(i-1)/n`、`i/n` 算 stage 百分比带，再用既有 `[asr]`/`[pegasus]`/`[clip]` 细行在带内插值。

- [ ] **Step 1: 写失败测试**

Create `scripts/test_progress_marker.py`:

```python
"""Pure-function test：[PROGRESS] marker 的 emit 格式 + parse + 带内插值。
无 GPU / 无 Redis。Run: .venv/Scripts/python.exe scripts/test_progress_marker.py"""
import io
import sys
import os
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import progress as P  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

# (a) emit 打印一行可被 parse 还原
buf = io.StringIO()
with redirect_stdout(buf):
    P.emit_progress("asr", "语音识别", 4, 18)
line = buf.getvalue().strip()
check(line.startswith("[PROGRESS] "), f"(a) emit 前缀 -> {line!r}")
parsed = P.parse_progress_marker(line)
check(parsed == {"stage": "asr", "label": "语音识别", "i": 4, "n": 18},
      f"(a) parse 还原 -> {parsed!r}")

# (b) 非 marker 行 parse 返回 None
check(P.parse_progress_marker("[asr] 12.0s / 100.0s") is None, "(b) 普通行 -> None")
check(P.parse_progress_marker("") is None, "(b) 空行 -> None")
check(P.parse_progress_marker("[PROGRESS] not-json") is None, "(b) 坏 json -> None")

# (c) stage 百分比带：i/n 映射到 [lo, hi]
lo, hi = P.stage_band(4, 18)
check(lo == round(3 / 18 * 100) and hi == round(4 / 18 * 100),
      f"(c) band(4,18) -> {(lo, hi)}")
check(P.stage_band(18, 18) == (round(17 / 18 * 100), 100), "(c) 末 stage hi=100")

# (d) 带内插值
check(P.interpolate(20, 60, 0.0) == 20, "(d) frac=0 -> lo")
check(P.interpolate(20, 60, 1.0) == 60, "(d) frac=1 -> hi")
check(P.interpolate(20, 60, 0.5) == 40, "(d) frac=0.5 -> 中点")
check(P.interpolate(20, 60, 2.0) == 60, "(d) frac>1 截到 hi")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ===")
    sys.exit(1)
print("=== ALL CHECKS PASSED ===")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe scripts/test_progress_marker.py`
Expected: FAIL —`ModuleNotFoundError: No module named 'progress'`。

- [ ] **Step 3: 写 src/progress.py**

Create `src/progress.py`:

```python
"""[PROGRESS] marker：pipeline 子进程 emit、worker 解析 + 进度带插值。
marker 形如：[PROGRESS] {"stage":"asr","label":"语音识别","i":4,"n":18}
i 为 1-based stage 序号，n 为总 stage 数。"""
from __future__ import annotations

import json
from typing import Optional

_MARKER = "[PROGRESS] "

# _stage_xxx 函数名（去前缀）-> 中文展示标签
STAGE_LABELS = {
    "prepare_video": "准备视频",
    "extract_audio": "抽取音频",
    "build_asr_context": "构建 ASR 上下文",
    "asr": "语音识别",
    "chunk": "切分段落",
    "summarize": "生成摘要",
    "qwen_asr_fix": "ASR 纠错",
    "keyframes": "抽取关键帧",
    "llm_headline": "生成标题",
    "visual_sims": "视觉相似度",
    "vlm_captions": "视觉描述",
    "classify_category_early": "内容分类",
    "example_detection": "例子检测",
    "chapters": "章节切分",
    "bilingual": "双语生成",
    "write_outputs": "写出产物",
    "classify_category_for_meta": "分类(meta)",
    "write_md": "写笔记",
}


def emit_progress(stage: str, label: str, i: int, n: int) -> None:
    """pipeline 子进程调用：打印一行机器可读 marker 到 stdout。"""
    print(_MARKER + json.dumps(
        {"stage": stage, "label": label, "i": i, "n": n},
        ensure_ascii=False), flush=True)


def parse_progress_marker(line: str) -> Optional[dict]:
    """worker 调用：是 marker 行就返回 dict，否则 None。"""
    if not line or not line.startswith(_MARKER):
        return None
    try:
        return json.loads(line[len(_MARKER):])
    except (ValueError, TypeError):
        return None


def stage_band(i: int, n: int) -> tuple[int, int]:
    """第 i 个 stage（1-based）占的百分比带 [lo, hi]。"""
    lo = round((i - 1) / n * 100)
    hi = round(i / n * 100)
    return lo, hi


def interpolate(lo: int, hi: int, frac: float) -> int:
    """带内线性插值；frac 截断到 [0,1]。"""
    frac = max(0.0, min(1.0, frac))
    return round(lo + (hi - lo) * frac)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe scripts/test_progress_marker.py`
Expected: `=== ALL CHECKS PASSED ===`。

- [ ] **Step 5: 在 pipeline.run() 循环里 emit marker**

Modify `src/pipeline.py`。先在文件顶部 import 区（`from summarize import ...` 之后，约 line 36）加：

```python
from progress import emit_progress, STAGE_LABELS
```

再把 `run()` 里的 stage 循环（约 line 1546-1547）：

```python
    state = PipelineState()
    for stage in _STAGES:
        stage(cfg, state)
```

改为：

```python
    state = PipelineState()
    n_stages = len(_STAGES)
    for idx, stage in enumerate(_STAGES, start=1):
        key = stage.__name__.replace("_stage_", "")
        emit_progress(key, STAGE_LABELS.get(key, key), idx, n_stages)
        stage(cfg, state)
```

- [ ] **Step 6: 验证 pipeline 仍可 import 且 marker 可发**

Run: `.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'src'); import pipeline; from progress import STAGE_LABELS; import inspect; assert len(pipeline._STAGES)==18; print('stages', len(pipeline._STAGES)); print('labels', len(STAGE_LABELS))"`
Expected: `stages 18` 且 `labels 18`（每个 stage 都有标签）。无 ImportError。

- [ ] **Step 7: Commit**

```bash
git add src/progress.py scripts/test_progress_marker.py src/pipeline.py
git commit -m "feat(pipeline): 18-stage [PROGRESS] marker + 解析/插值模块，替换脆弱 [N/4]"
```

---

## Task 3: 从 server.py 提取可复用 helper 到 service_common

**Files:**
- Create: `src/service_common.py`
- Modify: `server.py:30-50,65-80,103-123,315-370`（删被搬走的定义，改为 import）
- Test: `scripts/test_service_common.py`

把 server.py 与 worker 都要用的 helper 提到一个模块：路径常量、`normalize_quality`、`adaptive_chunk_chars`、`estimate_pipeline_seconds`、`probe_duration`、`publish_to_web`。函数名去掉前导下划线（变公共 API）。

- [ ] **Step 1: 写失败测试（纯函数）**

Create `scripts/test_service_common.py`:

```python
"""service_common 纯函数断言（normalize_quality / adaptive_chunk_chars /
estimate_pipeline_seconds）。无 GPU / 无 Redis。
Run: .venv/Scripts/python.exe scripts/test_service_common.py"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import service_common as SC  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

# normalize_quality 白名单
check(SC.normalize_quality("720p") == "720p", "720p 合法")
check(SC.normalize_quality("BEST") == "best", "大小写归一")
check(SC.normalize_quality(None) == "best", "None -> best")
check(SC.normalize_quality("; rm -rf") == "best", "非法 -> best")
check(SC.normalize_quality("") == "best", "空 -> best")

# adaptive_chunk_chars 分档
check(SC.adaptive_chunk_chars(0) == 800, "未知时长 -> 800")
check(SC.adaptive_chunk_chars(300) == 400, "<10min -> 400")
check(SC.adaptive_chunk_chars(1000) == 600, "<25min -> 600")
check(SC.adaptive_chunk_chars(3000) == 800, ">=25min -> 800")

# estimate_pipeline_seconds 单调递增 + 正
check(SC.estimate_pipeline_seconds(0) > 0, "0 时长仍有固定开销")
check(SC.estimate_pipeline_seconds(1200) > SC.estimate_pipeline_seconds(600),
      "时长越长估时越大")

# 路径常量存在
check(SC.ROOT.name == "notegen", f"ROOT 指向项目根 -> {SC.ROOT}")
check(str(SC.PY).endswith("python.exe"), "PY 指向 venv python")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ===")
    sys.exit(1)
print("=== ALL CHECKS PASSED ===")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe scripts/test_service_common.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'service_common'`。

- [ ] **Step 3: 写 src/service_common.py**

Create `src/service_common.py`（内容与 server.py 现有实现等价，函数去前导下划线；`publish_to_web` 整体搬来）:

```python
"""server.py 与 worker_tasks.py 共用的纯/IO helper：路径常量、画质归一、
chunk 粒度、估时、ffprobe 时长、产物 publish 到 web/public。
（原先散在 server.py，提取以便 worker 进程复用。）"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / ".venv" / "Scripts" / "python.exe"
WEB_PUBLIC = ROOT / "web" / "public"
NOTES_DIR = WEB_PUBLIC / "notes"
VIDEOS_DIR = WEB_PUBLIC / "videos"
DATA_OUTPUTS = ROOT / "data" / "outputs"
DATA_RAW = ROOT / "data" / "raw"

_QUALITY_RE = re.compile(r"^(?:best|\d{2,4}p)$")


def normalize_quality(q: Optional[str]) -> str:
    """白名单：'best' or 'NNNp'；非法 → 'best'。"""
    if not q:
        return "best"
    s = q.strip().lower()
    return s if _QUALITY_RE.match(s) else "best"


def adaptive_chunk_chars(video_duration_sec: float) -> int:
    """按视频时长选 chunker 字符上限。"""
    if video_duration_sec <= 0:
        return 800
    if video_duration_sec < 600:
        return 400
    if video_duration_sec < 1500:
        return 600
    return 800


def estimate_pipeline_seconds(video_duration_sec: float) -> int:
    """经验估时（秒）：下载抽音频固定 ~25s + ASR ~0.45x + 后处理 30 + 0.04x。"""
    return int(25 + video_duration_sec * 0.45 + 30 + video_duration_sec * 0.04)


def probe_duration(video_path: Path) -> float:
    """ffprobe 探本地视频时长（秒）。失败返回 0。"""
    try:
        ffmpeg_bin = shutil.which("ffmpeg")
        if ffmpeg_bin:
            ffprobe = str(Path(ffmpeg_bin).with_name("ffprobe.exe"))
        else:
            ffprobe = "ffprobe"
        r = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, timeout=15,
        )
        return float((r.stdout or "").strip() or 0)
    except Exception:
        return 0.0


def publish_to_web(stem: str) -> str:
    """把 data/outputs/{stem}.* + data/raw/{stem}.mp4 copy 到 web/public，返回 note_id。"""
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    short_id = stem
    note_dir = NOTES_DIR / short_id
    note_dir.mkdir(parents=True, exist_ok=True)

    def _pick_latest(pattern: str) -> Optional[Path]:
        cands = sorted(DATA_OUTPUTS.glob(pattern), key=lambda p: -p.stat().st_mtime)
        return cands[0] if cands else None

    for kind in ("summary", "chapters"):
        src = _pick_latest(f"{stem}.large-v3.neural.texttile*.{kind}.json")
        if src:
            shutil.copy(src, note_dir / f"{kind}.json")

    meta_stem = stem.split(".")[0]
    meta_src = DATA_RAW / f"{meta_stem}.meta.json"
    if meta_src.exists():
        shutil.copy(meta_src, note_dir / "meta.json")

    kf_candidates = sorted(
        [p for p in DATA_OUTPUTS.glob(f"{stem}.large-v3.neural.texttile*.keyframes") if p.is_dir()],
        key=lambda p: -p.stat().st_mtime,
    )
    kf_src = kf_candidates[0] if kf_candidates else None
    if kf_src:
        kf_dst = note_dir / "keyframes"
        kf_dst.mkdir(parents=True, exist_ok=True)
        for f in kf_src.iterdir():
            if f.is_file():
                try:
                    shutil.copy(f, kf_dst / f.name)
                except PermissionError:
                    pass

    for cand in [DATA_RAW / f"{meta_stem}_p0.mp4",
                 DATA_RAW / f"{meta_stem}.mp4",
                 *DATA_RAW.glob(f"{meta_stem}*.mp4")]:
        if cand.exists():
            shutil.copy(cand, VIDEOS_DIR / f"{short_id}.mp4")
            break
    return short_id
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe scripts/test_service_common.py`
Expected: `=== ALL CHECKS PASSED ===`。

- [ ] **Step 5: server.py 改用 service_common（删重复定义）**

Modify `server.py`：删除现有的 `_estimate_pipeline_seconds`（44-50）、`_probe_duration`（65-80）、`_adaptive_chunk_chars`（103-112）、`_QUALITY_RE`+`_normalize_quality`（115-123）、`_publish_to_web`（315-370）定义，以及顶部 `ROOT`/`PY`/`WEB_PUBLIC`/`NOTES_DIR`/`VIDEOS_DIR`/`DATA_OUTPUTS`/`DATA_RAW` 常量（30-36）。在 import 区（约 line 28 `from pydantic import BaseModel` 之后）加：

```python
import sys
ROOT = Path(__file__).resolve().parent
SRC_DIR = str(ROOT / "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from service_common import (  # noqa: E402
    PY, WEB_PUBLIC, NOTES_DIR, VIDEOS_DIR, DATA_OUTPUTS, DATA_RAW,
    normalize_quality, adaptive_chunk_chars, estimate_pipeline_seconds,
    probe_duration, publish_to_web,
)
```

然后把 server.py 内对旧名的调用改成新名：`_normalize_quality(` → `normalize_quality(`、`_adaptive_chunk_chars(` → `adaptive_chunk_chars(`、`_estimate_pipeline_seconds(` → `estimate_pipeline_seconds(`、`_probe_duration(` → `probe_duration(`、`_publish_to_web(` → `publish_to_web(`。
（注意：`ROOT` 仍在 server.py 顶部本地定义，保留；删的是从 service_common 重复的那批常量。Task 6 会进一步重写 `_run_pipeline*`，此处只做最小提取替换，保持 server.py 可导入。）

- [ ] **Step 6: 验证 server.py 仍可 import**

Run: `.venv/Scripts/python.exe -c "import server; print('ok', bool(server.app))"`
Expected: `ok True`，无 ImportError / NameError。

- [ ] **Step 7: Commit**

```bash
git add src/service_common.py scripts/test_service_common.py server.py
git commit -m "refactor(server): 提取 quality/chunk/estimate/probe/publish 到 service_common 供 worker 复用"
```

---

## Task 4: jobqueue（Redis 连接 + job 状态 + 幂等 + enqueue）

**Files:**
- Create: `src/jobqueue.py`
- Test: `scripts/test_jobqueue.py`

job hash `job:{id}`（字段 id/source/is_local/quality/stage/percent/msg/note_id/returncode/created）；事件 list `job:{id}:events`（json 串，SSE 增量消费）；日志 list `job:{id}:log`（LTRIM 500）；幂等映射 `idem:{key}` → job_id。RQ 用不解码连接（存 bytes），job hash 用 `decode_responses=True` 连接。两连接可被测试注入。

- [ ] **Step 1: 写失败测试（fakeredis，无真 Redis）**

Create `scripts/test_jobqueue.py`:

```python
"""jobqueue 断言：idempotency_key 稳定性、job hash 读写、状态机、事件 list、
幂等 enqueue 去重。用 fakeredis，无需真 Redis / GPU。
Run: .venv/Scripts/python.exe scripts/test_jobqueue.py"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import fakeredis  # noqa: E402
import jobqueue as JQ  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

# 共享一个 fake server，两连接（解码 / 不解码）都看同一份数据
srv = fakeredis.FakeServer()
kv = fakeredis.FakeStrictRedis(server=srv, decode_responses=True)
rq_conn = fakeredis.FakeStrictRedis(server=srv)
JQ.set_connections(kv=kv, rq=rq_conn)

# (a) idempotency_key：同输入稳定、URL 大小写/空白归一、quality 影响 key
k1 = JQ.idempotency_key("https://X.com/V ", {"quality": "best"})
k2 = JQ.idempotency_key("https://x.com/v", {"quality": "best"})
k3 = JQ.idempotency_key("https://x.com/v", {"quality": "720p"})
check(k1 == k2, "(a) URL 归一后 key 相同")
check(k1 != k3, "(a) quality 不同 -> key 不同")

# (b) create + job_state round-trip
JQ.create_job("job1", "https://x.com/v", {"quality": "best", "is_local": False})
st = JQ.job_state("job1")
check(st is not None and st["stage"] == "queued" and st["percent"] == 0,
      f"(b) 初始状态 queued/0 -> {st}")
check(st["source"] == "https://x.com/v" and st["is_local"] == "0",
      "(b) source/is_local 落库")
check(JQ.job_state("nope") is None, "(b) 不存在 job -> None")

# (c) set_progress 状态机 + 事件增量
JQ.set_progress("job1", stage="running", percent=10, msg="启动")
JQ.set_progress("job1", stage="done", percent=100, msg="完成", note_id="BV123")
st = JQ.job_state("job1")
check(st["stage"] == "done" and st["percent"] == 100 and st["note_id"] == "BV123",
      f"(c) 终态 done/100/note -> {st}")
evs, n = JQ.read_events("job1", 0)
check(len(evs) == 2 and n == 2, f"(c) 两条事件 -> {len(evs)}")
evs2, n2 = JQ.read_events("job1", n)
check(evs2 == [] and n2 == 2, "(c) 增量读：无新事件")

# (d) append_log + LTRIM 500
for i in range(600):
    JQ.append_log("job1", f"line{i}")
st = JQ.job_state("job1")
check(len(st["log"]) == 500 and st["log"][-1] == "line599",
      f"(d) 日志截到 500 + 保留最新 -> {len(st['log'])}")

# (e) enqueue_generate：首次入队 is_new=True；同 URL 再入队命中幂等
jid, is_new = JQ.enqueue_generate("https://y.com/v", {"quality": "best"})
check(is_new is True, "(e) 首次 enqueue is_new=True")
jid2, is_new2 = JQ.enqueue_generate("https://y.com/v", {"quality": "best"})
check(jid2 == jid and is_new2 is False, "(e) 同 URL 命中幂等，返回同 job_id")
check(len(JQ.get_queue()) == 1, "(e) 队列里只有 1 个 job（未重复入队）")

# (f) 失败的 job 不命中幂等（允许重提）
JQ.set_progress(jid, stage="failed", percent=0, msg="boom")
jid3, is_new3 = JQ.enqueue_generate("https://y.com/v", {"quality": "best"})
check(is_new3 is True and jid3 != jid, "(f) failed 后重提 -> 新 job")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ===")
    sys.exit(1)
print("=== ALL CHECKS PASSED ===")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe scripts/test_jobqueue.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'jobqueue'`。

- [ ] **Step 3: 写 src/jobqueue.py**

Create `src/jobqueue.py`:

```python
"""Redis 连接 + RQ 队列封装 + job 状态/进度/事件读写 + 幂等。
- job hash:   job:{id}        （decode_responses 连接读写）
- events:     job:{id}:events （json 串 list，SSE 增量）
- log:        job:{id}:log    （list，LTRIM 500）
- idem 映射:  idem:{key}      → job_id
RQ 用不解码连接（存 pickled bytes）。两连接可被测试经 set_connections 注入。"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from typing import Optional

import redis
from rq import Queue, Retry

REDIS_URL = os.environ.get("NOTEGEN_REDIS_URL", "redis://127.0.0.1:6379/0")
JOB_TIMEOUT = 7200  # pipeline 长视频可能跑十几分钟，给足 2h

_kv = None   # decode_responses=True：job hash / list
_rq = None   # bytes：RQ Queue 专用


def set_connections(kv=None, rq=None) -> None:
    """测试钩子：注入 fakeredis 连接。"""
    global _kv, _rq
    _kv, _rq = kv, rq


def get_kv():
    global _kv
    if _kv is None:
        _kv = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    return _kv


def get_rq():
    global _rq
    if _rq is None:
        _rq = redis.Redis.from_url(REDIS_URL)
    return _rq


def get_queue() -> Queue:
    return Queue("default", connection=get_rq())


def _job_key(jid: str) -> str: return f"job:{jid}"
def _events_key(jid: str) -> str: return f"job:{jid}:events"
def _log_key(jid: str) -> str: return f"job:{jid}:log"
def _idem_key(k: str) -> str: return f"idem:{k}"


def idempotency_key(source: str, opts: dict) -> str:
    """稳定 key：归一化 source + quality + is_local（不含 local_meta 等易变字段）。"""
    norm = (source or "").strip().lower()
    payload = json.dumps(
        {"s": norm, "q": opts.get("quality") or "best", "l": bool(opts.get("is_local"))},
        sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def create_job(jid: str, source: str, opts: dict) -> None:
    get_kv().hset(_job_key(jid), mapping={
        "id": jid, "source": source,
        "is_local": "1" if opts.get("is_local") else "0",
        "quality": opts.get("quality") or "best",
        "stage": "queued", "percent": "0", "msg": "排队中",
        "created": str(time.time()),
    })


def set_progress(jid: str, *, stage=None, percent=None, msg=None,
                 note_id=None, returncode=None) -> None:
    """更新 job hash + 追加一条事件（仅含变化字段 + 时间戳）供 SSE 消费。"""
    kv = get_kv()
    fields = {}
    for k, v in (("stage", stage), ("percent", percent), ("msg", msg),
                 ("note_id", note_id), ("returncode", returncode)):
        if v is not None:
            fields[k] = str(v)
    if fields:
        kv.hset(_job_key(jid), mapping=fields)
    ev = dict(fields)
    ev["t"] = time.time()
    kv.rpush(_events_key(jid), json.dumps(ev, ensure_ascii=False))


def append_log(jid: str, line: str) -> None:
    kv = get_kv()
    kv.rpush(_log_key(jid), line)
    kv.ltrim(_log_key(jid), -500, -1)


def job_state(jid: str) -> Optional[dict]:
    kv = get_kv()
    h = kv.hgetall(_job_key(jid))
    if not h:
        return None
    try:
        h["percent"] = int(h.get("percent", 0))
    except (ValueError, TypeError):
        h["percent"] = 0
    h["log"] = kv.lrange(_log_key(jid), 0, -1)
    return h


def read_events(jid: str, start: int) -> tuple[list, int]:
    """从 start 起读事件 json 串增量，返回 (新事件串列表, 新游标)。"""
    evs = get_kv().lrange(_events_key(jid), start, -1)
    return evs, start + len(evs)


def queue_position(jid: str) -> Optional[int]:
    """job 在 RQ 队列里前面还有几个（0 = 队首待跑）；运行中/已完成 → None。"""
    try:
        return get_queue().get_job_position(jid)
    except Exception:
        return None


def enqueue_generate(source: str, opts: dict) -> tuple[str, bool]:
    """幂等入队。返回 (job_id, is_new)。命中已有 in-flight/done 任务则复用。"""
    kv = get_kv()
    key = idempotency_key(source, opts)
    existing = kv.get(_idem_key(key))
    if existing:
        st = job_state(existing)
        if st and st.get("stage") not in ("failed", "interrupted"):
            return existing, False
    jid = uuid.uuid4().hex[:12]
    create_job(jid, source, opts)
    kv.set(_idem_key(key), jid)
    import worker_tasks  # lazy 避免 import 环
    get_queue().enqueue(
        worker_tasks.run_generate, jid, source, opts,
        job_id=jid, retry=Retry(max=2, interval=[10, 30]),
        job_timeout=JOB_TIMEOUT,
    )
    return jid, True
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe scripts/test_jobqueue.py`
Expected: `=== ALL CHECKS PASSED ===`。
（注：`enqueue_generate` 内 `import worker_tasks` 在 Task 5 才创建。本测试触及 (e)/(f) 会 enqueue → 需 worker_tasks 存在。**先执行下一步占位再回跑**，或本步先跑到 (d) 通过；建议：本 Task 与 Task 5 连续做，Step 4 在 Task 5 的 worker_tasks 落地后回跑确认全绿。）

- [ ] **Step 5: 写占位 worker_tasks 以解开 import（Task 5 会填实现）**

Create `src/worker_tasks.py`（占位，仅让 `import worker_tasks` 成功；Task 5 覆盖）:

```python
"""RQ 任务（Task 5 实现）。"""
def run_generate(job_id, source, opts):
    raise NotImplementedError
```

- [ ] **Step 6: 回跑 jobqueue 测试确认全绿**

Run: `.venv/Scripts/python.exe scripts/test_jobqueue.py`
Expected: `=== ALL CHECKS PASSED ===`（(e)/(f) 入队成功，队列深度断言通过）。

- [ ] **Step 7: Commit**

```bash
git add src/jobqueue.py scripts/test_jobqueue.py src/worker_tasks.py
git commit -m "feat(jobqueue): Redis job 状态/事件/日志 + 幂等 enqueue（fakeredis 断言）"
```

---

## Task 5: worker_tasks（run_generate：subprocess + 解析 + publish + 状态机）

**Files:**
- Modify: `src/worker_tasks.py`（替换 Task 4 的占位）
- Test: `scripts/test_worker_integration.py`

`run_generate` 等价于旧 `_run_pipeline_impl`，但进度写 Redis（经 jobqueue）。subprocess spawn 与 stdout 循环抽到可注入的 `_run_pipeline_subprocess`，output-fallback 抽到 `_scan_output_fallback`，测试 monkeypatch 这两处 + `service_common.publish_to_web` 即可不碰 GPU/文件系统跑全链路。失败（无产物）抛 `PipelineFailed` → RQ 记 failed registry + Retry 兜网络抖动。

- [ ] **Step 1: 写失败/集成测试（fakeredis + mock subprocess）**

Create `scripts/test_worker_integration.py`:

```python
"""worker_tasks 集成断言：enqueue→SimpleWorker→Redis 状态→done 全链路、
output-fallback、失败入 failed registry、幂等命中、并发=1 串行、Retry 配置。
mock 掉 subprocess 与 publish，不碰 GPU/文件系统。用 fakeredis。
Run: .venv/Scripts/python.exe scripts/test_worker_integration.py"""
import sys
import os
import time
import threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import fakeredis  # noqa: E402
from rq import SimpleWorker  # noqa: E402
import jobqueue as JQ  # noqa: E402
import worker_tasks as WT  # noqa: E402
import service_common as SC  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

def fresh():
    srv = fakeredis.FakeServer()
    kv = fakeredis.FakeStrictRedis(server=srv, decode_responses=True)
    rq_conn = fakeredis.FakeStrictRedis(server=srv)
    JQ.set_connections(kv=kv, rq=rq_conn)
    return rq_conn

def run_burst(conn):
    """SimpleWorker 同进程串行消费完队列即退（burst）。"""
    w = SimpleWorker([JQ.get_queue()], connection=conn)
    w.work(burst=True)

# ---- (a) 全链路 success：subprocess 假实现写进度，publish 假实现给 note_id ----
conn = fresh()
def fake_sub_ok(job_id, source, opts):
    JQ.set_progress(job_id, stage="语音识别", percent=30, msg="ASR…")
    return "BVfake", 0  # (stem, returncode)
WT._run_pipeline_subprocess = fake_sub_ok
SC.publish_to_web = lambda stem: stem  # 不复制文件
jid, _ = JQ.enqueue_generate("https://a.com/v", {"quality": "best"})
run_burst(conn)
st = JQ.job_state(jid)
check(st["stage"] == "done" and st["percent"] == 100 and st["note_id"] == "BVfake",
      f"(a) success 全链路 -> {st['stage']}/{st['percent']}/{st.get('note_id')}")

# ---- (b) output-fallback：subprocess 没返回 stem 但 fallback 扫到 ----
conn = fresh()
WT._run_pipeline_subprocess = lambda j, s, o: (None, 3221226505)
WT._scan_output_fallback = lambda job_id, started: "BVrecovered"
SC.publish_to_web = lambda stem: stem
jid, _ = JQ.enqueue_generate("https://b.com/v", {"quality": "best"})
run_burst(conn)
st = JQ.job_state(jid)
check(st["stage"] == "done" and st["note_id"] == "BVrecovered",
      f"(b) crash 但产物完整 -> publish done -> {st.get('note_id')}")

# ---- (c) 失败：无 stem 且 fallback 也无 -> failed + 进 failed registry ----
conn = fresh()
WT._run_pipeline_subprocess = lambda j, s, o: (None, 1)
WT._scan_output_fallback = lambda job_id, started: None
jid, _ = JQ.enqueue_generate("https://c.com/v", {"quality": "best"})
run_burst(conn)
st = JQ.job_state(jid)
check(st["stage"] == "failed", f"(c) 无产物 -> failed -> {st['stage']}")
from rq.registry import FailedJobRegistry  # noqa: E402
reg = FailedJobRegistry(queue=JQ.get_queue())
check(jid in reg.get_job_ids(), "(c) job 进 RQ failed registry")

# ---- (d) 幂等命中：success 后同 URL 再提，复用同 job，不重复跑 ----
conn = fresh()
calls = {"n": 0}
def fake_sub_count(j, s, o):
    calls["n"] += 1
    return "BVidem", 0
WT._run_pipeline_subprocess = fake_sub_count
SC.publish_to_web = lambda stem: stem
jid, new1 = JQ.enqueue_generate("https://d.com/v", {"quality": "best"})
run_burst(conn)
jid2, new2 = JQ.enqueue_generate("https://d.com/v", {"quality": "best"})
check(jid2 == jid and new2 is False, "(d) done 后同 URL 命中幂等")
check(calls["n"] == 1, f"(d) pipeline 只跑了一次 -> {calls['n']}")

# ---- (e) 并发=1：单 SimpleWorker 串行，最大并发恒为 1 ----
conn = fresh()
state = {"cur": 0, "max": 0, "lock": threading.Lock()}
def fake_sub_concurrency(j, s, o):
    with state["lock"]:
        state["cur"] += 1
        state["max"] = max(state["max"], state["cur"])
    time.sleep(0.05)
    with state["lock"]:
        state["cur"] -= 1
    return "BV" + j, 0
WT._run_pipeline_subprocess = fake_sub_concurrency
SC.publish_to_web = lambda stem: stem
JQ.enqueue_generate("https://e1.com/v", {"quality": "best"})
JQ.enqueue_generate("https://e2.com/v", {"quality": "best"})
run_burst(conn)
check(state["max"] == 1, f"(e) 最大并发=1 -> {state['max']}")

# ---- (f) Retry 配置：enqueue 的 job 带 retries_left=2 ----
conn = fresh()
WT._run_pipeline_subprocess = lambda j, s, o: ("BVx", 0)
SC.publish_to_web = lambda stem: stem
jid, _ = JQ.enqueue_generate("https://f.com/v", {"quality": "best"})
job = JQ.get_queue().fetch_job(jid)
check(job is not None and job.retries_left == 2,
      f"(f) Retry(max=2) 已挂 -> retries_left={getattr(job,'retries_left',None)}")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ===")
    sys.exit(1)
print("=== ALL CHECKS PASSED ===")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe scripts/test_worker_integration.py`
Expected: FAIL — 占位 `run_generate` 抛 `NotImplementedError`，(a) 断言不通过（或 worker 把 job 标 failed）。

- [ ] **Step 3: 实现 src/worker_tasks.py（覆盖占位）**

Replace `src/worker_tasks.py` 全文:

```python
"""RQ 任务：run_generate(job_id, source, opts)。
subprocess 跑 pipeline.py（崩溃隔离），解析 stdout 的 [PROGRESS] marker + 既有
[asr]/[pegasus]/[clip] 细行写 Redis 进度。等价于旧 server._run_pipeline_impl，
但状态走 jobqueue（Redis）而非内存。"""
from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

import jobqueue
import service_common as SC
from progress import parse_progress_marker, stage_band, interpolate


class PipelineFailed(Exception):
    """pipeline 跑完无产物：标 failed 并抛出，让 RQ 记 failed registry。"""


def run_generate(job_id: str, source: str, opts: dict) -> Optional[str]:
    started = time.time()
    jobqueue.set_progress(job_id, stage="running", percent=4, msg="启动 pipeline")
    try:
        stem, returncode = _run_pipeline_subprocess(job_id, source, opts)
    except Exception as e:
        jobqueue.set_progress(job_id, stage="failed", percent=0, msg=f"运行错误：{e}")
        raise

    if not stem:
        stem = _scan_output_fallback(job_id, started)
        if stem:
            jobqueue.set_progress(job_id, stage="收尾", percent=98,
                                  msg=f"进程异常退出但输出完整（{stem}），尝试 publish")

    if not stem:
        jobqueue.set_progress(job_id, stage="failed", percent=0,
                              msg=f"pipeline 退出码 {returncode}，未找到输出文件",
                              returncode=returncode)
        raise PipelineFailed(f"job {job_id}: no output (rc={returncode})")

    try:
        note_id = SC.publish_to_web(stem)
    except Exception as e:
        jobqueue.set_progress(job_id, stage="failed", percent=0, msg=f"产出复制失败：{e}")
        raise

    msg = "完成"
    if returncode not in (0, None):
        msg = f"完成（pipeline 退出码 {returncode}，已知 Windows cleanup 问题，不影响输出）"
    jobqueue.set_progress(job_id, stage="done", percent=100, msg=msg,
                          note_id=note_id, returncode=returncode)
    return note_id


def _build_cmd(source: str, opts: dict, chunk_chars: int) -> list[str]:
    is_local = bool(opts.get("is_local"))
    cmd = [
        str(SC.PY), "src/pipeline.py", source,
        *(["--local"] if is_local else []),
        "--chunker", "texttile",
        "--chunk-chars", str(chunk_chars),
        "--chapters",
        "--summarizer", "neural",
        "--keyframes",
        "--llm-chapters",
        "--vlm-captions",
    ]
    quality = opts.get("quality") or "best"
    if not is_local and quality != "best":
        cmd += ["--quality", quality]
    return cmd


def _run_pipeline_subprocess(job_id: str, source: str, opts: dict):
    """spawn pipeline.py，流式解析 stdout 写 Redis 进度。返回 (stem|None, returncode)。
    （测试 monkeypatch 此函数为假实现。）"""
    is_local = bool(opts.get("is_local"))
    local_meta = opts.get("local_meta") or {}

    # Step 0：估时 + 选 chunk_chars
    chunk_chars = 800
    try:
        if is_local:
            dur = float(local_meta.get("duration") or 0)
        else:
            from download import fetch_metadata  # noqa
            jobqueue.set_progress(job_id, stage="探测", percent=2, msg="读取视频元信息")
            dur = float((fetch_metadata(source) or {}).get("duration") or 0)
        if dur > 0:
            chunk_chars = SC.adaptive_chunk_chars(dur)
            est = SC.estimate_pipeline_seconds(dur)
            jobqueue.set_progress(job_id, stage="探测", percent=3,
                                  msg=f"视频 {dur/60:.1f} min · 预计 {est/60:.1f} min · cc={chunk_chars}")
    except Exception as e:
        jobqueue.set_progress(job_id, stage="探测", percent=2, msg=f"元信息读取失败（不影响）：{e}")

    cmd = _build_cmd(source, opts, chunk_chars)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    try:
        proc = subprocess.Popen(
            cmd, cwd=str(SC.ROOT), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
            env=env, bufsize=1,
        )
    except Exception as e:
        jobqueue.set_progress(job_id, stage="failed", percent=0, msg=f"启动失败：{e}")
        return None, -1

    lo, hi = 0, 0          # 当前 stage 的百分比带
    stem: Optional[str] = None
    for line in proc.stdout or []:
        line = line.rstrip()
        if not line:
            continue
        jobqueue.append_log(job_id, line)

        marker = parse_progress_marker(line)
        if marker:
            lo, hi = stage_band(marker["i"], marker["n"])
            jobqueue.set_progress(job_id, stage=marker["label"], percent=lo,
                                  msg=marker["label"])
            continue

        # 细粒度行：在当前 stage 带内插值
        m = re.search(r"\[asr\]\s*([\d.]+)\s*s\s*/\s*([\d.]+)\s*s", line)
        if m:
            frac = float(m.group(1)) / max(float(m.group(2)), 0.1)
            jobqueue.set_progress(job_id, percent=interpolate(lo, hi, frac),
                                  msg=f"语音识别 {float(m.group(1)):.0f}s/{float(m.group(2)):.0f}s")
            continue
        m = re.match(r"\s*\[pegasus\]\s*(\d+)/(\d+)", line)
        if m:
            frac = int(m.group(1)) / max(int(m.group(2)), 1)
            jobqueue.set_progress(job_id, percent=interpolate(lo, hi, frac),
                                  msg=f"Pegasus {m.group(1)}/{m.group(2)}")
            continue
        m = re.match(r"\s*\[clip\]\s*(\d+)/(\d+)", line)
        if m:
            frac = int(m.group(1)) / max(int(m.group(2)), 1)
            jobqueue.set_progress(job_id, percent=interpolate(lo, hi, frac),
                                  msg=f"CLIP 关键帧 {m.group(1)}/{m.group(2)}")
            continue
        if "[OK]" in line and "笔记" in line:
            mm = re.search(r"data[\\/]outputs[\\/]([^\\/]+)\.large-v3", line)
            if mm:
                stem = mm.group(1)
    proc.wait()
    return stem, proc.returncode


def _scan_output_fallback(job_id: str, started: float) -> Optional[str]:
    """subprocess 没吐 stem 时，扫 data/outputs 找 job 时段内新写的 md（Windows
    cleanup crash 但产物完整的情形）。返回 stem 或 None。
    （测试 monkeypatch 此函数。）"""
    candidates = [p for p in SC.DATA_OUTPUTS.glob("*.large-v3.neural.texttile*.md")
                  if p.stat().st_mtime >= started - 30]
    if not candidates:
        return None
    candidates.sort(key=lambda p: -p.stat().st_mtime)
    return re.sub(r"\.large-v3\.neural\.texttile(\.mm)?$", "", candidates[0].stem)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe scripts/test_worker_integration.py`
Expected: `=== ALL CHECKS PASSED ===`（(a)-(f) 全绿）。

- [ ] **Step 5: 回归 jobqueue 测试（确保 worker_tasks 真实现没破幂等链路）**

Run: `.venv/Scripts/python.exe scripts/test_jobqueue.py`
Expected: `=== ALL CHECKS PASSED ===`。

- [ ] **Step 6: Commit**

```bash
git add src/worker_tasks.py scripts/test_worker_integration.py
git commit -m "feat(worker): run_generate RQ 任务——subprocess pipeline + Redis 进度 + fallback/failed 状态机"
```

---

## Task 6: server.py 改 enqueue + 读 Redis（删线程/信号量/内存状态）

**Files:**
- Modify: `server.py`（端点改写 + 删 `_jobs`/`_jobs_lock`/`_PIPELINE_GATE`/`_run_pipeline`/`_run_pipeline_impl`/`_emit`）

api 进程不再起线程跑 GPU，只 enqueue 到 RQ、读 Redis。`/api/generate`、`/api/upload` 改 `enqueue_generate`；`/api/jobs/{id}` 读 `job_state` + `queue_position`；`/api/jobs/{id}/events` SSE 读 Redis 事件 list；`/api/health` 加 Redis 连通 + 队列深度；其余端点（`/api/probe`、`/api/notes`、`DELETE /api/notes/{id}`）不变。

- [ ] **Step 1: 删旧 runner 与内存状态，import jobqueue**

Modify `server.py`：

1. 顶部 import 区加（在 Task 3 的 `from service_common import ...` 之后）：

```python
import jobqueue  # noqa: E402
import redis as _redis_pkg  # noqa: E402
```

2. 删除以下整段定义：
   - `_jobs`/`_jobs_lock`（82-84）
   - `_PIPELINE_GATE` 注释块 + 定义（86-89）
   - `_emit`（92-99）
   - `_run_pipeline`（126-140）
   - `_run_pipeline_impl`（143-312，整段，含 subprocess 循环 + fallback + publish 调用——这些逻辑已搬到 `worker_tasks.py`）
   - `threading`、`asyncio`、`uuid` 的使用随端点改写后再清理（见下）。`asyncio` 仍被 SSE 用，保留。

- [ ] **Step 2: 改写 /api/generate**

把 `generate`（393-411）整段替换为：

```python
@app.post("/api/generate")
def generate(req: GenerateReq):
    url = (req.url or "").strip()
    if not url:
        raise HTTPException(400, "url is required")
    quality = normalize_quality(req.quality)
    try:
        job_id, _is_new = jobqueue.enqueue_generate(url, {"quality": quality})
    except _redis_pkg.exceptions.ConnectionError:
        raise HTTPException(503, "队列服务暂不可用，请稍后再试")
    return {"job_id": job_id}
```

- [ ] **Step 3: 改写 /api/upload 的入队部分**

`upload`（417-476）保留落盘 + 写 meta（426-462）不变，把结尾起线程部分（463-476）替换为：

```python
    opts = {"is_local": True, "quality": "best", "local_meta": meta}
    try:
        job_id, _is_new = jobqueue.enqueue_generate(str(dest), opts)
    except _redis_pkg.exceptions.ConnectionError:
        raise HTTPException(503, "队列服务暂不可用，请稍后再试")
    return {"job_id": job_id, "filename": file.filename,
            "duration": dur, "stored_as": dest.name}
```

- [ ] **Step 4: 改写 /api/jobs/{id} 读 Redis**

把 `job_status`（479-485）替换为：

```python
@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    st = jobqueue.job_state(job_id)
    if st is None:
        raise HTTPException(404, "job not found")
    pos = jobqueue.queue_position(job_id)
    if pos is not None:
        st["queue_ahead"] = pos
    return st
```

- [ ] **Step 5: 改写 /api/jobs/{id}/events SSE 读 Redis**

把 `job_events`（488-510）替换为：

```python
@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    if jobqueue.job_state(job_id) is None:
        raise HTTPException(404, "job not found")

    async def gen():
        last = 0
        while True:
            events, last = jobqueue.read_events(job_id, last)
            for e in events:          # e 已是 json 串
                yield f"data: {e}\n\n"
            st = jobqueue.job_state(job_id)
            if st is None or st.get("stage") in ("done", "failed", "interrupted"):
                break
            await asyncio.sleep(0.4)

    return StreamingResponse(gen(), media_type="text/event-stream")
```

- [ ] **Step 6: 改写 /api/health 加 Redis/队列深度**

把 `health`（583-585）替换为：

```python
@app.get("/api/health")
def health():
    try:
        jobqueue.get_kv().ping()
        depth = len(jobqueue.get_queue())
        return {"ok": True, "redis": True, "queue_depth": depth}
    except Exception as e:
        return {"ok": False, "redis": False, "error": str(e)}
```

- [ ] **Step 7: 清理 unused import**

删 `import threading`（19）、`import uuid`（21）若已无引用（generate/upload 不再用）。`import asyncio`、`import json`、`import re`、`import os` 视剩余引用保留（SSE 用 asyncio；`_guess_domain`/`list_notes` 用 json）。

- [ ] **Step 8: 验证 import + 端点签名 + Redis health**

确保 Redis 在跑（Task 1 Step 5）。Run:

```bash
.venv/Scripts/python.exe -c "import server; from fastapi.testclient import TestClient; c=TestClient(server.app); r=c.get('/api/health'); print(r.status_code, r.json()); j=c.get('/api/jobs/doesnotexist'); print('missing job ->', j.status_code)"
```

Expected: `200 {'ok': True, 'redis': True, 'queue_depth': 0}` 且 `missing job -> 404`。无 ImportError / 未删干净的 `_jobs` NameError。
（若 `fastapi.testclient` 需要 `httpx`：改用 `.venv/Scripts/python.exe -c "import server; print('import ok', bool(server.app))"` 至少确认可导入，health 留到 Task 8 e2e 验。）

- [ ] **Step 9: Commit**

```bash
git add server.py
git commit -m "refactor(server): /generate/upload 改 RQ enqueue，jobs/events/health 读 Redis，删线程+信号量+内存状态"
```

---

## Task 7: worker 启动脚本 + README 启动顺序

**Files:**
- Create: `scripts/run_worker.py`
- Modify: `README.md`（加「在线服务启动顺序」小节）

- [ ] **Step 1: 写 scripts/run_worker.py**

Create `scripts/run_worker.py`:

```python
"""起单个 RQ SimpleWorker 消费 default 队列。
- SimpleWorker：同进程消费、不 os.fork（Windows 无 fork）。
- 单 worker = 并发=1：天然串行，契合「大模型串行加载」铁律。
- pipeline 仍以 subprocess 跑（worker_tasks 内），崩溃不带垮 worker。
Run: .venv/Scripts/python.exe scripts/run_worker.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rq import SimpleWorker  # noqa: E402
import jobqueue  # noqa: E402


def main():
    conn = jobqueue.get_rq()
    queue = jobqueue.get_queue()
    print(f"[worker] SimpleWorker 启动，监听 default 队列 @ {jobqueue.REDIS_URL}")
    SimpleWorker([queue], connection=conn).work()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 验证 worker 脚本可导入且能空跑 burst**

确保 Redis 在跑。Run:

```bash
.venv/Scripts/python.exe -c "import sys,os; sys.path.insert(0,'src'); from rq import SimpleWorker; import jobqueue; SimpleWorker([jobqueue.get_queue()], connection=jobqueue.get_rq()).work(burst=True); print('worker burst ok (空队列即退)')"
```

Expected: 打印 `worker burst ok (空队列即退)`，无异常（空队列 burst 立即返回）。

- [ ] **Step 3: README 加启动顺序小节**

在 `README.md` 末尾追加：

```markdown
## 在线服务（Redis + RQ 队列模式）

提交 URL/文件 → 异步处理 → 拿笔记。需按顺序起 4 个组件：

1. **Redis**（队列后端，Docker 一条命令）：
   ```bash
   docker compose up -d redis
   ```
2. **API**（FastAPI）：
   ```bash
   .venv/Scripts/python.exe server.py        # http://127.0.0.1:8000
   ```
3. **Worker**（消费队列，跑在 GPU 机器上，单进程 = 并发 1）：
   ```bash
   .venv/Scripts/python.exe scripts/run_worker.py
   ```
4. **Web**（Next.js 前端）：
   ```bash
   cd web && npm run dev                      # http://localhost:3000
   ```

- 健康检查：`GET /api/health` 返回 `{ok, redis, queue_depth}`。
- Redis 没起时 `/api/generate` 返回 503；起好后重试即可。
- 自定义 Redis 地址：设 `NOTEGEN_REDIS_URL`（默认 `redis://127.0.0.1:6379/0`）。
```

- [ ] **Step 4: Commit**

```bash
git add scripts/run_worker.py README.md
git commit -m "feat(worker): run_worker.py 起 SimpleWorker + README 记 redis→api→worker→web 启动顺序"
```

---

## Task 8: 手动端到端验收（真 Redis + worker + 短视频）

**Files:** 无（纯验收，不改代码）

不进 CI、需 GPU，照 spec「手动 e2e」。把整链路跑通一次，确认替换信号量后行为正确。

- [ ] **Step 1: 起全栈**

四个终端依次：
```bash
docker compose up -d redis
.venv/Scripts/python.exe server.py
.venv/Scripts/python.exe scripts/run_worker.py
cd web && npm run dev
```
确认 `GET http://127.0.0.1:8000/api/health` → `{"ok": true, "redis": true, "queue_depth": 0}`。

- [ ] **Step 2: 提交一个短视频（省时用 360p）**

前端提交一个短视频 URL（或用 curl）：
```bash
curl -s -X POST http://127.0.0.1:8000/api/generate -H "Content-Type: application/json" -d "{\"url\":\"<短视频URL>\",\"quality\":\"360p\"}"
```
Expected: 返回 `{"job_id":"..."}`；worker 终端开始打印 pipeline 日志；`GET /api/jobs/{id}/events` SSE 进度从探测→语音识别→…→done 平滑推进（百分比由 `[PROGRESS]` 带 + 细行插值驱动）；完成后前端跳 `/notes/{note_id}` 能看到笔记。

- [ ] **Step 3: 验证并发=1 串行 + 队列位置**

连续提交两个 job。Expected: 第二个 `GET /api/jobs/{id2}` 返回里带 `queue_ahead: 1`（前面还有 1 个）；worker 串行执行（第一个 done 后第二个才开始），GPU 不会同时载两份模型（无黑屏/花屏）。

- [ ] **Step 4: 验证幂等**

第一个 job done 后，用相同 URL+quality 再提一次。Expected: 立刻返回同一个已完成 job 的 id，worker 不重新跑（幂等命中）。

- [ ] **Step 5: 验证持久化**

job 跑完后重启 api + worker 进程（Redis 不停），`GET /api/jobs/{已完成id}`。Expected: 仍返回 done 状态 + note_id（状态在 Redis，进程重启不丢）。

- [ ] **Step 6: 收尾说明**

确认无回归后，向用户报告：子项目 #1 服务骨架完成，`feature/service-hardening` 分支就绪，合 main 由用户决定（遵循三分支并存、合并是用户动作的约定）。

---

## Self-Review（计划编写后自检，已执行）

- **Spec coverage**：组件 1-5（jobqueue / worker_tasks / server 改造 / pipeline marker / worker 脚本+compose）分别对应 Task 4 / 5 / 6 / 2 / 1+7；数据流（提交/消费/进度/完成/队列位置）见 Task 5+6；错误处理（transient Retry / 致命 failed / crash-but-output fallback / Redis 不可用 503 / 幂等）见 Task 4-6 与测试 (b)(c)(d)(f)；测试三类（单元 marker/idem、集成 mock subprocess、手动 e2e）= Task 2/3/4/5 的 assert 脚本 + Task 8。✅
- **Placeholder scan**：无 TBD/TODO；每个 code step 给完整代码与确切命令/期望输出。Task 4 Step 5 的 worker_tasks 占位是**有意的临时桩**（解 import 环），Task 5 Step 3 覆盖之——已在原地说明。✅
- **Type/名称一致**：`set_progress`/`job_state`/`read_events`/`enqueue_generate`/`queue_position`/`create_job`/`append_log` 在 jobqueue 定义，worker_tasks 与 server 的调用签名逐一对齐；`_run_pipeline_subprocess`/`_scan_output_fallback`/`publish_to_web` 的 monkeypatch 名与实现名一致；progress 的 `emit_progress`/`parse_progress_marker`/`stage_band`/`interpolate` 在 pipeline 与 worker 两端用法一致。✅
- **环境事实对齐**：已知 rq/redis/fakeredis/pytest 均未装 → Task 1 装前三个（不引 pytest，沿用 `scripts/test_*.py` assert 风格）；测试用 fakeredis 不依赖真 Redis（除 Task 8 手动 e2e）。✅

