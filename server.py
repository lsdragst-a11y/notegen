"""NoteGen FastAPI backend.

POST  /api/generate  { url } -> { job_id }
GET   /api/jobs/{job_id}/events  (SSE) -> 流式进度
GET   /api/jobs/{job_id}  -> job 状态快照
GET   /api/notes  -> 列出所有可用笔记（含 demo + 新生成）

后台用 subprocess 跑 pipeline.py，解析 stdout 的 [N/4] markers 推进度。完成后
copy outputs 到 web/public/{notes,videos}/，前端 fetch /api/notes 看新笔记。
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent

import sys
SRC_DIR = str(ROOT / "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from service_common import (  # noqa: E402
    PY, WEB_PUBLIC, NOTES_DIR, VIDEOS_DIR, DATA_OUTPUTS, DATA_RAW,
    normalize_quality, adaptive_chunk_chars, estimate_pipeline_seconds,
    probe_duration, publish_to_web,
)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:3001", "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ Job state（in-memory，重启丢失，dev 用够了）============
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

# 串行闸：GPU 只有一块，pipeline 同一时刻只能跑一个。否则同时来两个请求会并行
# spawn 两个 pipeline → 两份 7B 模型抢同一张卡 → 黑屏/花屏崩溃。抢不到闸的任务停在
# 「排队中」阻塞等待。这是「并发=1 的最小队列」，后续会被 Redis+RQ 替换。
_PIPELINE_GATE = threading.Semaphore(1)


def _emit(job_id: str, **kwargs):
    """更新 job 状态 + 追加事件到列表（SSE 会消费）。"""
    with _jobs_lock:
        if job_id not in _jobs:
            return
        j = _jobs[job_id]
        j.update(kwargs)
        j["events"].append({**kwargs, "t": time.time()})


# ============ Pipeline runner (subprocess + stdout 解析) ============
def _run_pipeline(job_id: str, source: str, *,
                  is_local: bool = False,
                  local_meta: Optional[dict] = None,
                  quality: str = "best"):
    """并发=1 闸门：序列化 GPU pipeline 执行。抢不到闸的任务停在「排队中」直到前一个
    跑完，根治并发上 GPU 的崩溃。真正的工作在 _run_pipeline_impl。"""
    if not _PIPELINE_GATE.acquire(blocking=False):
        _emit(job_id, stage="queued", percent=4,
              msg="前面有任务在跑，排队等待 GPU 空闲…")
        _PIPELINE_GATE.acquire()
    try:
        _run_pipeline_impl(job_id, source, is_local=is_local,
                           local_meta=local_meta, quality=quality)
    finally:
        _PIPELINE_GATE.release()


def _run_pipeline_impl(job_id: str, source: str, *,
                  is_local: bool = False,
                  local_meta: Optional[dict] = None,
                  quality: str = "best"):
    """后台线程：subprocess 跑 pipeline.py，解析 stdout 推进度。
    URL 模式：source 是视频链接，先 fetch_metadata 拿 duration。
    Local 模式：source 是 data/raw 下的视频文件绝对路径，duration 已经在
                upload 阶段 ffprobe 出来写进 local_meta，直接复用。"""
    chunk_chars = 800  # 默认；探测到 duration 后会按 adaptive_chunk_chars 调整

    # Step 0: 拿 duration 估时间 + 选 chunk_chars
    try:
        if is_local:
            dur = float((local_meta or {}).get("duration") or 0)
            title = (local_meta or {}).get("title") or ""
            _emit(job_id, stage="探测", percent=1,
                  msg=f"本地视频：{title or Path(source).name}")
            if dur > 0:
                chunk_chars = adaptive_chunk_chars(dur)
                est = estimate_pipeline_seconds(dur)
                _emit(job_id, stage="探测", percent=3,
                      msg=f"视频 {dur/60:.1f} min · 预计 {est/60:.1f} min · 切分粒度 cc={chunk_chars}",
                      video_duration=dur, est_total_sec=est, video_title=title)
        else:
            from download import fetch_metadata  # noqa
            _emit(job_id, stage="探测", percent=1, msg="读取视频元信息（标题/时长）")
            meta = fetch_metadata(source)
            dur = float(meta.get("duration") or 0)
            if dur > 0:
                chunk_chars = adaptive_chunk_chars(dur)
                est = estimate_pipeline_seconds(dur)
                _emit(job_id, stage="探测", percent=3,
                      msg=f"视频 {dur/60:.1f} min · 预计 {est/60:.1f} min · 切分粒度 cc={chunk_chars}",
                      video_duration=dur, est_total_sec=est,
                      video_title=meta.get("title") or "")
    except Exception as e:
        _emit(job_id, stage="探测", percent=2, msg=f"元信息读取失败（不影响）：{e}")

    cmd = [
        str(PY), "src/pipeline.py", source,
        *(["--local"] if is_local else []),
        "--chunker", "texttile",
        "--chunk-chars", str(chunk_chars),
        "--chapters",
        "--summarizer", "neural",
        "--keyframes",
        "--llm-chapters",  # Qwen2.5-7B-AWQ 层级章节，~5GB VRAM；失败自动 fallback TextTiling
        "--vlm-captions",  # Qwen2.5-VL-7B-AWQ 视觉描述给 LLM 切分提供 cue；n_chunks>15 内部自动降级
    ]
    if not is_local and quality and quality != "best":
        cmd += ["--quality", quality]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    _emit(job_id, stage="启动", percent=4, msg="启动 pipeline 子进程")
    try:
        proc = subprocess.Popen(
            cmd, cwd=str(ROOT),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", env=env, bufsize=1,
        )
    except Exception as e:
        _emit(job_id, stage="error", percent=0, msg=f"启动失败：{e}")
        return

    pegasus_total = clip_total = 0
    md_path: Optional[str] = None
    try:
        for line in proc.stdout or []:
            line = line.rstrip()
            if not line:
                continue
            with _jobs_lock:
                _jobs[job_id].setdefault("log", []).append(line)
                if len(_jobs[job_id]["log"]) > 500:
                    _jobs[job_id]["log"] = _jobs[job_id]["log"][-500:]

            # 阶段进度（fuzzy 匹配 pipeline.py 自身的 print）
            if "[1/4]" in line:
                _emit(job_id, stage="下载", percent=6, msg="下载视频")
            elif "[2/4]" in line:
                _emit(job_id, stage="音频", percent=10, msg="抽取音频")
            elif "[3/4]" in line:
                if "缓存" in line:
                    _emit(job_id, stage="ASR", percent=55, msg="命中 ASR 缓存")
                else:
                    _emit(job_id, stage="ASR", percent=18, msg="语音识别中（最久的一步，5-10 分钟）")
            elif "[asr]" in line and "s /" in line:
                # `[asr] 123.4s / 2102.0s` — 流式 ASR 进度，把 percent 在 18-58 区间线性插值
                m = re.search(r"\[asr\]\s*([\d.]+)\s*s\s*/\s*([\d.]+)\s*s", line)
                if m:
                    proc_sec, tot = float(m.group(1)), float(m.group(2))
                    pct = 18 + int(min(1.0, proc_sec / max(tot, 0.1)) * 40)
                    _emit(job_id, stage="ASR", percent=min(58, pct),
                          msg=f"语音识别 {proc_sec:.0f}s / {tot:.0f}s")
            elif "duration=" in line and "segments=" in line:
                _emit(job_id, stage="ASR", percent=58, msg=line.replace("      ", "").strip())
            elif "[4/4]" in line:
                m = re.search(r"(\d+)\s*chunks", line)
                n = m.group(1) if m else "?"
                _emit(job_id, stage="摘要", percent=62, msg=f"切出 {n} 段，生成 headlines")
            elif "[pegasus]" in line and "->" in line:
                m = re.match(r"\s*\[pegasus\]\s*(\d+)/(\d+)", line)
                if m:
                    i, t = int(m.group(1)), int(m.group(2))
                    pegasus_total = t
                    _emit(job_id, stage="摘要", percent=62 + int(i / t * 14),
                          msg=f"Pegasus {i}/{t}")
            elif "[clip]" in line and "keyframe_" in line:
                m = re.match(r"\s*\[clip\]\s*(\d+)/(\d+)", line)
                if m:
                    i, t = int(m.group(1)), int(m.group(2))
                    clip_total = t
                    _emit(job_id, stage="关键帧", percent=78 + int(i / t * 14),
                          msg=f"CLIP 关键帧 {i}/{t}")
            elif "LLM 层级章节切分" in line:
                _emit(job_id, stage="章节", percent=92, msg="Qwen2.5-7B 层级章节切分（首次载入 30s）")
            elif "[llm-chapters]" in line:
                _emit(job_id, stage="章节", percent=94,
                      msg=line.replace("      ", "").strip())
            elif "[chapter abstract]" in line:
                # 抽 i/total 推 percent，章节越多铺得越细
                m = re.search(r"\[chapter abstract\]\s*(\d+)/(\d+)", line)
                if m:
                    i, t = int(m.group(1)), int(m.group(2))
                    _emit(job_id, stage="章节", percent=94 + int(i / t * 4),
                          msg=f"章节概述 {i}/{t}")
                else:
                    _emit(job_id, stage="章节", percent=94, msg="生成章节概述")
            elif "章节切分" in line:
                _emit(job_id, stage="章节", percent=98, msg="章节切分完成")
            elif "[OK]" in line and "笔记" in line:
                m = re.search(r"data[\\/]outputs[\\/]([^\\/]+)\.large-v3", line)
                if m:
                    md_path = m.group(1)
        proc.wait()
    except Exception as e:
        _emit(job_id, stage="error", percent=0, msg=f"运行错误：{e}")
        return

    # 兜底：subprocess 退出后如果没拿到 stem，扫 data/outputs/ 找 job 时段内
    # 新写的 *.large-v3.neural.texttile.md。这处理 PyTorch / ctranslate2 在 Windows 上
    # 退出时偶发的 access violation（exit code 3221226505）—— pipeline 实际写完所有
    # 输出文件，只是退出过程 crash，[OK] 行可能 print 在 buffer 没 flush。
    if not md_path:
        with _jobs_lock:
            job_started = _jobs[job_id].get("created", time.time() - 3600)
        candidates = [p for p in DATA_OUTPUTS.glob("*.large-v3.neural.texttile*.md")
                      if p.stat().st_mtime >= job_started - 30]
        if candidates:
            candidates.sort(key=lambda p: -p.stat().st_mtime)
            md_path = re.sub(r"\.large-v3\.neural\.texttile(\.mm)?$", "", candidates[0].stem)
            _emit(job_id, stage="收尾", percent=98,
                  msg=f"pipeline 进程异常退出但输出文件完整（{md_path}），尝试 publish")

    if not md_path:
        _emit(job_id, stage="error", percent=0,
              msg=f"pipeline 退出码 {proc.returncode}，未找到输出文件")
        return

    # 后处理：copy 产出到 web/public（即便 returncode != 0，文件存在就 publish）
    try:
        note_id = publish_to_web(md_path)
    except Exception as e:
        _emit(job_id, stage="error", percent=0, msg=f"产出复制失败：{e}")
        return
    if proc.returncode != 0:
        _emit(job_id, stage="done", percent=100,
              msg=f"完成（pipeline 进程退出码 {proc.returncode}，已知的 PyTorch Windows cleanup 问题，不影响输出）",
              note_id=note_id)
    else:
        _emit(job_id, stage="done", percent=100, msg="完成", note_id=note_id)


# ============ HTTP endpoints ============
class GenerateReq(BaseModel):
    url: str
    quality: Optional[str] = "best"


class ProbeReq(BaseModel):
    url: str


@app.post("/api/probe")
def probe(req: ProbeReq):
    """探测 URL 可下的画质 list + 元信息。前端 URL 提交前先调一次让用户选。"""
    url = (req.url or "").strip()
    if not url:
        raise HTTPException(400, "url is required")
    from download import probe_qualities  # lazy 避免循环 import
    return probe_qualities(url)


@app.post("/api/generate")
def generate(req: GenerateReq):
    url = (req.url or "").strip()
    if not url:
        raise HTTPException(400, "url is required")
    quality = normalize_quality(req.quality)
    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id, "url": url, "stage": "queued", "percent": 0,
            "msg": "排队中", "events": [], "log": [], "created": time.time(),
        }
    threading.Thread(
        target=_run_pipeline,
        args=(job_id, url),
        kwargs={"is_local": False, "quality": quality},
        daemon=True,
    ).start()
    return {"job_id": job_id}


_ALLOWED_VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".m4v", ".ts"}


@app.post("/api/upload")
async def upload(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    uploader: Optional[str] = Form(None),
):
    """接收本地视频文件，存到 data/raw/local_<id>.mp4 + 写 meta.json，
    然后启 pipeline (--local) 后台 job。返回 { job_id }，前端继续用
    /api/jobs/{job_id}/events 跟进度，跟 URL 模式完全一致。"""
    if not file.filename:
        raise HTTPException(400, "no filename")
    ext = Path(file.filename).suffix.lower()
    if ext and ext not in _ALLOWED_VIDEO_EXTS:
        raise HTTPException(400, f"unsupported video format: {ext}")
    # 落盘 — pipeline 期望 mp4 后缀，非 mp4 时 ffmpeg 可以读但 publish 链路
    # 会按 .mp4 名复制；这里强制写为 .mp4 后缀让下游一致（ffmpeg 会按容器实际解码）
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    safe_id = f"local_{uuid.uuid4().hex[:10]}"
    dest = DATA_RAW / f"{safe_id}.mp4"
    try:
        with dest.open("wb") as f:
            while True:
                chunk = await file.read(4 * 1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
    except Exception as e:
        # 落盘失败把残文件清掉
        try: dest.unlink(missing_ok=True)
        except Exception: pass
        raise HTTPException(500, f"upload write failed: {e}")
    # ffprobe 拿时长（失败也无所谓，pipeline 会自己跑出 ASR duration）
    dur = probe_duration(dest)
    display_title = (title or "").strip() or Path(file.filename).stem
    display_uploader = (uploader or "").strip() or "本地上传"
    meta = {
        "id": safe_id,
        "title": display_title,
        "uploader": display_uploader,
        "duration": dur,
        "webpage_url": "",
        "description": f"本地上传文件：{file.filename}",
    }
    (DATA_RAW / f"{safe_id}.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id, "url": str(dest), "stage": "queued", "percent": 0,
            "msg": "排队中（本地上传）", "events": [], "log": [], "created": time.time(),
        }
    threading.Thread(
        target=_run_pipeline,
        args=(job_id, str(dest)),
        kwargs={"is_local": True, "local_meta": meta},
        daemon=True,
    ).start()
    return {"job_id": job_id, "filename": file.filename,
            "duration": dur, "stored_as": dest.name}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    with _jobs_lock:
        j = _jobs.get(job_id)
        if not j:
            raise HTTPException(404, "job not found")
        return {k: v for k, v in j.items() if k != "events"}


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    with _jobs_lock:
        if job_id not in _jobs:
            raise HTTPException(404, "job not found")

    async def gen():
        last_idx = 0
        while True:
            with _jobs_lock:
                if job_id not in _jobs:
                    break
                events = _jobs[job_id]["events"]
                new = events[last_idx:]
                last_idx = len(events)
                stage = _jobs[job_id].get("stage")
            for e in new:
                yield f"data: {json.dumps(e, ensure_ascii=False)}\n\n"
            if stage in ("done", "error"):
                break
            await asyncio.sleep(0.4)

    return StreamingResponse(gen(), media_type="text/event-stream")


def _guess_domain(title: str) -> str:
    t = (title or "").lower()
    if "python" in t or "代码" in t or "编程" in t:
        return "编程教学"
    if "考研" in t or "操作系统" in t or "计算机网络" in t or "线代" in t or "线性代数" in t:
        return "考研专业课"
    if "vlog" in t or "日常" in t or "外卖" in t or "小镇" in t:
        return "Vlog"
    if "评测" in t or "iphone" in t or "ios" in t:
        return "数码评测"
    return "学习"


@app.get("/api/notes")
def list_notes():
    """枚举 web/public/notes/ 下所有 note 目录。"""
    if not NOTES_DIR.exists():
        return []
    items = []
    for d in sorted(NOTES_DIR.iterdir(), key=lambda p: -p.stat().st_mtime):
        if not d.is_dir():
            continue
        summary_p = d / "summary.json"
        chapters_p = d / "chapters.json"
        if not summary_p.exists() or not chapters_p.exists():
            continue
        try:
            summary = json.loads(summary_p.read_text(encoding="utf-8"))
            chapters = json.loads(chapters_p.read_text(encoding="utf-8"))
        except Exception:
            continue
        meta = {}
        if (d / "meta.json").exists():
            try:
                meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
            except Exception:
                meta = {}
        items.append({
            "id": d.name,
            "title": meta.get("title") or d.name,
            "domain": _guess_domain(meta.get("title", "")),
            "duration_sec": int(summary[-1]["end"]) if summary else 0,
            "chunks": len(summary),
            "chapters": len(chapters.get("chapters", [])),
            "uploader": meta.get("uploader", ""),
            "webpage_url": meta.get("webpage_url", ""),
        })
    return items


@app.delete("/api/notes/{note_id}")
def delete_note(note_id: str):
    """删除笔记 + 关联视频。id 必须是合法的目录名（无路径分隔符），避免越级。"""
    safe = (note_id or "").strip()
    if not safe or "/" in safe or "\\" in safe or ".." in safe:
        raise HTTPException(400, "invalid note id")
    note_dir = NOTES_DIR / safe
    video = VIDEOS_DIR / f"{safe}.mp4"
    if not note_dir.exists() and not video.exists():
        raise HTTPException(404, "note not found")
    removed = []
    if note_dir.exists():
        shutil.rmtree(note_dir)
        removed.append(str(note_dir))
    if video.exists():
        video.unlink()
        removed.append(str(video))
    return {"deleted": safe, "removed": removed}


@app.get("/api/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)
