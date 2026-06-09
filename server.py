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

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
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
from object_store import default_store  # noqa: E402

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
import db  # noqa: E402
import accounts  # noqa: E402
import authdeps  # noqa: E402
from authdeps import current_user, require_user  # noqa: E402
from userdata import notes_repo, jobs_repo, bookmarks_repo  # noqa: E402

db.init_db()  # 启动即建表（幂等）

import os as _os  # noqa: E402
_COOKIE_SECURE = _os.environ.get("NOTEGEN_COOKIE_SECURE", "0") == "1"
_VERIFY_BASE = _os.environ.get("NOTEGEN_VERIFY_BASE", "http://localhost:3000")


# ============ HTTP endpoints ============
class RegisterReq(BaseModel):
    email: str
    password: str
    display_name: str


class LoginReq(BaseModel):
    email: str
    password: str


@app.post("/api/auth/register", status_code=201)
def auth_register(req: RegisterReq):
    email = (req.email or "").strip()
    if not email or "@" not in email:
        raise HTTPException(400, "邮箱格式不正确")
    if len(req.password or "") < 8:
        raise HTTPException(400, "密码至少 8 位")
    try:
        uid = accounts.create_user(email, req.password, req.display_name or email)
    except ValueError:
        raise HTTPException(409, "该邮箱已注册")
    token = accounts.create_verification_token(uid)
    # dev：不发真邮件，把验证链接打到控制台
    print(f"[VERIFY] {_VERIFY_BASE}/verify?token={token}", flush=True)
    return {"ok": True, "message": "注册成功，请查看控制台验证链接完成邮箱验证"}


@app.get("/api/auth/verify")
def auth_verify(token: str):
    uid = accounts.consume_verification_token(token)
    if uid is None:
        raise HTTPException(400, "验证链接无效或已过期")
    return {"ok": True, "message": "邮箱验证成功，请登录"}


@app.post("/api/auth/login")
def auth_login(req: LoginReq):
    user = accounts.verify_login(req.email, req.password)
    if user is None:
        raise HTTPException(401, "邮箱或密码错误")
    if not user["email_verified"]:
        raise HTTPException(403, "请先验证邮箱（查看控制台验证链接）")
    token = accounts.create_session(user["id"])
    resp = JSONResponse(user)
    resp.set_cookie(authdeps.SESSION_COOKIE, token, httponly=True, samesite="lax",
                    max_age=accounts.SESSION_TTL, secure=_COOKIE_SECURE, path="/")
    return resp


@app.post("/api/auth/logout")
def auth_logout(request: Request):
    token = request.cookies.get(authdeps.SESSION_COOKIE)
    if token:
        accounts.delete_session(token)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(authdeps.SESSION_COOKIE, path="/")
    return resp


@app.get("/api/auth/me")
def auth_me(user: dict = Depends(require_user)):
    return user


class GenerateReq(BaseModel):
    url: str
    quality: Optional[str] = "best"


class ProbeReq(BaseModel):
    url: str


class BookmarkReq(BaseModel):
    key: str
    noteId: str
    noteTitle: str
    kind: str
    idx: int
    title: str
    title_en: Optional[str] = None
    time: float
    keyframeRel: Optional[str] = None
    categoryIds: list[str] = []
    addedAt: Optional[float] = None


class BookmarkCategoryReq(BaseModel):
    id: str
    name: str
    color: str
    createdAt: Optional[float] = None


class BookmarkCategoryRenameReq(BaseModel):
    name: str


@app.post("/api/probe")
def probe(req: ProbeReq):
    """探测 URL 可下的画质 list + 元信息。前端 URL 提交前先调一次让用户选。"""
    url = (req.url or "").strip()
    if not url:
        raise HTTPException(400, "url is required")
    from download import probe_qualities  # lazy 避免循环 import
    return probe_qualities(url)


@app.post("/api/generate")
def generate(req: GenerateReq, user: dict = Depends(require_user)):
    url = (req.url or "").strip()
    if not url:
        raise HTTPException(400, "url is required")
    quality = normalize_quality(req.quality)
    if jobs_repo.count_active(user["id"]) >= 1:
        raise HTTPException(409, "你已有任务在处理中，请等它完成后再提交")
    opts = {"quality": quality, "user_id": user["id"]}
    try:
        job_id, is_new = jobqueue.enqueue_generate(url, opts)
    except _redis_pkg.exceptions.ConnectionError:
        raise HTTPException(503, "队列服务暂不可用，请稍后再试")
    if is_new:
        jobs_repo.record(job_id, user["id"], url, is_local=False,
                         quality=quality, status="queued")
    return {"job_id": job_id}


_ALLOWED_VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".m4v", ".ts"}


@app.post("/api/upload")
async def upload(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    uploader: Optional[str] = Form(None),
    user: dict = Depends(require_user),
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
    if jobs_repo.count_active(user["id"]) >= 1:
        try: dest.unlink(missing_ok=True)
        except Exception: pass
        raise HTTPException(409, "你已有任务在处理中，请等它完成后再提交")
    opts = {"is_local": True, "quality": "best", "local_meta": meta,
            "user_id": user["id"]}
    try:
        job_id, is_new = jobqueue.enqueue_generate(str(dest), opts)
    except _redis_pkg.exceptions.ConnectionError:
        raise HTTPException(503, "队列服务暂不可用，请稍后再试")
    if is_new:
        jobs_repo.record(job_id, user["id"], str(dest), is_local=True,
                         quality="best", status="queued")
    return {"job_id": job_id, "filename": file.filename,
            "duration": dur, "stored_as": dest.name}


def _owned_job_or_404(job_id: str, user: dict) -> dict:
    row = jobs_repo.get(job_id)
    if row is None or row["user_id"] != user["id"]:
        raise HTTPException(404, "job not found")
    return row


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str, user: dict = Depends(require_user)):
    _owned_job_or_404(job_id, user)
    st = jobqueue.job_state(job_id)
    if st is None:
        raise HTTPException(404, "job not found")
    pos = jobqueue.queue_position(job_id)
    if pos is not None:
        st["queue_ahead"] = pos
    return st


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str, user: dict = Depends(require_user)):
    _owned_job_or_404(job_id, user)
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


def _note_view(n: dict) -> dict:
    return {"id": n["id"], "title": n["title"], "domain": n["domain"],
            "duration_sec": n["duration_sec"], "chunks": n["chunks"],
            "chapters": n["chapters"], "uploader": n["uploader"],
            "webpage_url": n["webpage_url"], "visibility": n["visibility"]}


@app.get("/api/notes/public")
def list_public_notes():
    return [_note_view(n) for n in notes_repo.list_public()]


@app.get("/api/notes/mine")
def list_my_notes(user: dict = Depends(require_user)):
    return [_note_view(n) for n in notes_repo.list_mine(user["id"])]


@app.get("/api/bookmarks")
def bookmark_state(user: dict = Depends(require_user)):
    return bookmarks_repo.state(user["id"])


@app.put("/api/bookmarks")
def upsert_bookmark(req: BookmarkReq, user: dict = Depends(require_user)):
    data = req.model_dump()
    if data["kind"] not in ("chunk", "chapter"):
        raise HTTPException(400, "invalid bookmark kind")
    if not data["key"].strip() or not data["noteId"].strip():
        raise HTTPException(400, "invalid bookmark")
    bookmarks_repo.upsert_bookmark(user["id"], data)
    return bookmarks_repo.state(user["id"])


@app.delete("/api/bookmarks/{key:path}")
def delete_bookmark(key: str, user: dict = Depends(require_user)):
    bookmarks_repo.delete_bookmark(user["id"], key)
    return bookmarks_repo.state(user["id"])


@app.put("/api/bookmark-categories")
def upsert_bookmark_category(req: BookmarkCategoryReq,
                             user: dict = Depends(require_user)):
    if not req.id.strip() or not req.name.strip():
        raise HTTPException(400, "invalid category")
    bookmarks_repo.upsert_category(
        user["id"], id=req.id, name=req.name.strip(),
        color=req.color or "#0a84ff", created_at=req.createdAt,
    )
    return bookmarks_repo.state(user["id"])


@app.patch("/api/bookmark-categories/{category_id}")
def rename_bookmark_category(category_id: str, req: BookmarkCategoryRenameReq,
                             user: dict = Depends(require_user)):
    name = req.name.strip()
    if not name:
        raise HTTPException(400, "invalid category name")
    if not bookmarks_repo.rename_category(user["id"], category_id, name):
        raise HTTPException(404, "category not found")
    return bookmarks_repo.state(user["id"])


@app.delete("/api/bookmark-categories/{category_id}")
def delete_bookmark_category(category_id: str, user: dict = Depends(require_user)):
    bookmarks_repo.delete_category(user["id"], category_id)
    return bookmarks_repo.state(user["id"])


@app.get("/api/history")
def list_history(user: dict = Depends(require_user)):
    return jobs_repo.list_history(user["id"])


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: str, user: dict = Depends(require_user)):
    row = _owned_job_or_404(job_id, user)
    if row["status"] not in ("failed", "interrupted"):
        raise HTTPException(409, "只有失败/中断的任务可以重试")
    if jobs_repo.count_active(user["id"]) >= 1:
        raise HTTPException(409, "你已有任务在处理中，请等它完成后再提交")
    opts = {"quality": row["quality"], "user_id": user["id"],
            "is_local": bool(row["is_local"])}
    try:
        new_id, is_new = jobqueue.enqueue_generate(row["source"], opts)
    except _redis_pkg.exceptions.ConnectionError:
        raise HTTPException(503, "队列服务暂不可用，请稍后再试")
    if is_new:
        jobs_repo.record(new_id, user["id"], row["source"],
                         is_local=bool(row["is_local"]), quality=row["quality"],
                         status="queued")
    return {"job_id": new_id}


@app.get("/api/notes/{note_id}/file/{path:path}")
def note_file(note_id: str, path: str, user: Optional[dict] = Depends(current_user)):
    """私有笔记鉴权托管（公开笔记走 Next.js 静态，不绕此端点）。
    非 owner / 未登录 / 不存在 → 一律 404，不泄露存在性。Starlette FileResponse 自带 Range。"""
    row = notes_repo.get(note_id)
    if row is None:
        raise HTTPException(404, "not found")
    if row["visibility"] == "private" and (user is None or row["owner_id"] != user["id"]):
        raise HTTPException(404, "not found")
    try:
        target = default_store.file_path(row["storage_path"], path)
    except ValueError:
        raise HTTPException(404, "not found")
    if not target.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(str(target))


@app.delete("/api/notes/{note_id}")
def delete_note(note_id: str, user: dict = Depends(require_user)):
    safe = (note_id or "").strip()
    if not safe or "/" in safe or "\\" in safe or ".." in safe:
        raise HTTPException(400, "invalid note id")
    row = notes_repo.get(safe)
    if row is None:
        raise HTTPException(404, "note not found")
    if row["visibility"] == "private":
        if row["owner_id"] != user["id"]:
            raise HTTPException(404, "note not found")
    else:  # public：仅 admin
        if user.get("role") != "admin":
            raise HTTPException(403, "仅管理员可删除公开笔记")
    removed = []
    if row["visibility"] == "private":
        removed.extend(default_store.delete_prefix(row["storage_path"]))
    else:
        note_dir = default_store.path_for_ref(row["storage_path"])
        video = VIDEOS_DIR / f"{safe}.mp4"
        if note_dir.exists():
            shutil.rmtree(note_dir, ignore_errors=True)
            removed.append(str(note_dir))
        if video.exists():
            video.unlink()
            removed.append(str(video))
    notes_repo.delete(safe)
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
