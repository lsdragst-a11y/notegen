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
import shutil
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


# ============ 队列后端：job 状态/进度/事件全在 Redis（经 jobqueue）============
# api 进程只 enqueue + 读 Redis，不再起线程跑 GPU。并发=1 由单个 RQ SimpleWorker
# 进程天然保证（取代旧的 threading.Semaphore 闸门），契合「大模型串行加载」铁律。
import jobqueue  # noqa: E402
import redis as _redis_pkg  # noqa: E402


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
    try:
        job_id, _is_new = jobqueue.enqueue_generate(url, {"quality": quality})
    except _redis_pkg.exceptions.ConnectionError:
        raise HTTPException(503, "队列服务暂不可用，请稍后再试")
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
    opts = {"is_local": True, "quality": "best", "local_meta": meta}
    try:
        job_id, _is_new = jobqueue.enqueue_generate(str(dest), opts)
    except _redis_pkg.exceptions.ConnectionError:
        raise HTTPException(503, "队列服务暂不可用，请稍后再试")
    return {"job_id": job_id, "filename": file.filename,
            "duration": dur, "stored_as": dest.name}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    st = jobqueue.job_state(job_id)
    if st is None:
        raise HTTPException(404, "job not found")
    pos = jobqueue.queue_position(job_id)
    if pos is not None:
        st["queue_ahead"] = pos
    return st


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
    try:
        jobqueue.get_kv().ping()
        depth = len(jobqueue.get_queue())
        return {"ok": True, "redis": True, "queue_depth": depth}
    except Exception as e:
        return {"ok": False, "redis": False, "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)
