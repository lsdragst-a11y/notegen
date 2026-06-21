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
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent

import sys
SRC_DIR = str(ROOT / "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
SCRIPTS_DIR = str(ROOT / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from service_common import (  # noqa: E402
    PY, WEB_PUBLIC, NOTES_DIR, VIDEOS_DIR, DATA_OUTPUTS, DATA_RAW,
    normalize_quality, adaptive_chunk_chars, estimate_pipeline_seconds,
    probe_duration, publish_to_web,
)
from object_store import default_store  # noqa: E402

app = FastAPI()
# 额外放行来源（compose / 局域网他机访问）：
#   NOTEGEN_CORS_ORIGINS="http://192.168.1.5:3000,http://mynas:3000"
import os  # noqa: E402
_EXTRA_ORIGINS = [o.strip() for o in
                  os.environ.get("NOTEGEN_CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:3001", "http://127.0.0.1:3001",
    ] + _EXTRA_ORIGINS,
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
from userdata import notes_repo, jobs_repo, bookmarks_repo, shares_repo  # noqa: E402
import backup as backup_mod  # noqa: E402
import maintenance  # noqa: E402
import mailer  # noqa: E402
from logging_setup import setup_logging  # noqa: E402
from ratelimit import SlidingWindowLimiter  # noqa: E402

db.init_db()  # 启动即建表（幂等）
log = setup_logging("server")

import os as _os  # noqa: E402
_COOKIE_SECURE = _os.environ.get("NOTEGEN_COOKIE_SECURE", "0") == "1"
_VERIFY_BASE = _os.environ.get("NOTEGEN_VERIFY_BASE", "http://localhost:3000")

# ============ 阶段 B 硬化：限速 / 上传上限 / 磁盘水位 ============
_LOGIN_LIMITER = SlidingWindowLimiter.from_env("NOTEGEN_LOGIN_LIMIT", "10/60")
_REGISTER_LIMITER = SlidingWindowLimiter.from_env("NOTEGEN_REGISTER_LIMIT", "10/600")
_MAX_UPLOAD_MB = int(_os.environ.get("NOTEGEN_MAX_UPLOAD_MB", "4096"))


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _enforce_limit(limiter: SlidingWindowLimiter, request: Request, what: str) -> None:
    ip = _client_ip(request)
    if not limiter.allow(ip):
        ra = limiter.retry_after(ip)
        log.warning(f"rate-limited: {what} from {ip}, retry after {ra}s")
        raise HTTPException(429, f"{what}过于频繁，请 {ra} 秒后再试",
                            headers={"Retry-After": str(ra)})


def _reject_if_low_disk() -> None:
    st = maintenance.disk_status()
    if st["low"]:
        log.warning(f"low disk: free {st['free_gb']}GB ({st['free_ratio']:.0%}), 拒绝新任务")
        raise HTTPException(
            507, f"服务器磁盘空间不足（剩余 {st['free_gb']}GB），暂不接收新任务")


@app.on_event("startup")
async def _start_maintenance_loop():
    """每日例行：磁盘治理 + 备份。启动 60s 后首跑，之后每 24h 一轮（阻塞 IO 丢线程池）。
    NOTEGEN_AUTO_MAINTENANCE=0 关清理（raw 里有要长留的素材时，改手动 run_maintenance.py）；
    NOTEGEN_AUTO_BACKUP=0 关备份（改手动 run_backup.py）。磁盘水位检查不受影响。"""
    do_clean = _os.environ.get("NOTEGEN_AUTO_MAINTENANCE", "1") != "0"
    do_backup = _os.environ.get("NOTEGEN_AUTO_BACKUP", "1") != "0"
    if not do_clean:
        log.info("自动磁盘清理已关闭（NOTEGEN_AUTO_MAINTENANCE=0）")
    if not do_backup:
        log.info("自动备份已关闭（NOTEGEN_AUTO_BACKUP=0）")
    if not (do_clean or do_backup):
        return

    async def _loop():
        await asyncio.sleep(60)
        while True:
            if do_clean:
                try:
                    s = await asyncio.to_thread(maintenance.run_once)
                    log.info(
                        "maintenance: 清理过期文件 {} 个、孤儿上传 {} 个，磁盘剩余 {}GB ({:.0%})".format(
                            len(s["old_files_removed"]), len(s["orphan_uploads_removed"]),
                            s["disk"]["free_gb"], s["disk"]["free_ratio"]))
                except Exception as e:
                    log.error(f"maintenance 失败: {e}")
            if do_backup:
                try:
                    b = await asyncio.to_thread(backup_mod.run_backup)
                    log.info(
                        "backup: {}（{}MB，{} 个文件，跳过视频 {}，滚动清理 {} 份）".format(
                            b["path"], b["size_mb"], b["files"],
                            b["skipped_videos"], len(b["pruned"])))
                except Exception as e:
                    log.error(f"backup 失败: {e}")
            await asyncio.sleep(86400)
    asyncio.create_task(_loop())


# ============ HTTP endpoints ============
class RegisterReq(BaseModel):
    email: str
    password: str
    display_name: str


class LoginReq(BaseModel):
    email: str
    password: str


@app.post("/api/auth/register", status_code=201)
def auth_register(req: RegisterReq, request: Request):
    _enforce_limit(_REGISTER_LIMITER, request, "注册")
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
    # 配了 NOTEGEN_SMTP_* 走真邮件；否则维持 dev 行为：链接打到控制台
    link = f"{_VERIFY_BASE}/verify?token={token}"
    if mailer.send_verification_email(email, link):
        log.info(f"register: 验证邮件已发送 -> {email}")
        return {"ok": True, "message": "注册成功，验证邮件已发送，请查收（注意垃圾箱）"}
    return {"ok": True, "message": "注册成功，请查看控制台验证链接完成邮箱验证"}


@app.get("/api/auth/verify")
def auth_verify(token: str):
    uid = accounts.consume_verification_token(token)
    if uid is None:
        raise HTTPException(400, "验证链接无效或已过期")
    return {"ok": True, "message": "邮箱验证成功，请登录"}


@app.post("/api/auth/login")
def auth_login(req: LoginReq, request: Request):
    _enforce_limit(_LOGIN_LIMITER, request, "登录尝试")
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
    _reject_if_low_disk()
    quality = normalize_quality(req.quality)
    if jobs_repo.count_active(user["id"]) >= 1:
        raise HTTPException(409, "你已有任务在处理中，请等它完成后再提交")
    opts = {"quality": quality, "user_id": user["id"]}
    try:
        job_id, is_new = jobqueue.enqueue_generate(url, opts)
    except _redis_pkg.exceptions.RedisError:
        raise HTTPException(503, "队列服务暂不可用，请稍后再试")
    if is_new:
        jobs_repo.record(job_id, user["id"], url, is_local=False,
                         quality=quality, status="queued")
    return {"job_id": job_id}


_ALLOWED_VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".m4v", ".ts"}


class _UploadTooLarge(Exception):
    pass


@app.post("/api/upload")
async def upload(
    request: Request,
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
    _reject_if_low_disk()
    # 上传上限：Content-Length 先快速拒（留 1MB multipart 开销余量），
    # 落盘时再按实际字节数兜底——头可以伪造，写入计数不行
    max_bytes = _MAX_UPLOAD_MB * 1024 * 1024
    clen = request.headers.get("content-length")
    if clen and clen.isdigit() and int(clen) > max_bytes + 1024 * 1024:
        raise HTTPException(413, f"文件过大（上限 {_MAX_UPLOAD_MB}MB）")
    # 配额检查放在落盘之前：已有任务在跑时直接 409，不浪费几百 MB 的写入再删除
    if jobs_repo.count_active(user["id"]) >= 1:
        raise HTTPException(409, "你已有任务在处理中，请等它完成后再提交")
    # 落盘 — pipeline 期望 mp4 后缀，非 mp4 时 ffmpeg 可以读但 publish 链路
    # 会按 .mp4 名复制；这里强制写为 .mp4 后缀让下游一致（ffmpeg 会按容器实际解码）
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    safe_id = f"local_{uuid.uuid4().hex[:10]}"
    dest = DATA_RAW / f"{safe_id}.mp4"
    written = 0
    try:
        with dest.open("wb") as f:
            while True:
                chunk = await file.read(4 * 1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise _UploadTooLarge()
                f.write(chunk)
    except _UploadTooLarge:
        try: dest.unlink(missing_ok=True)
        except Exception: pass
        raise HTTPException(413, f"文件过大（上限 {_MAX_UPLOAD_MB}MB）")
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
    opts = {"is_local": True, "quality": "best", "local_meta": meta,
            "user_id": user["id"]}
    try:
        job_id, is_new = jobqueue.enqueue_generate(str(dest), opts)
    except _redis_pkg.exceptions.RedisError:
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
            # 轻量终态检查：HGET 单字段，别用 job_state（HGETALL + 整段 log）
            stage = jobqueue.job_stage(job_id)
            if stage is None or stage in ("done", "failed", "interrupted"):
                # 终态事件可能在上面 read_events 之后才写入，break 前再清一次增量
                events, last = jobqueue.read_events(job_id, last)
                for e in events:
                    yield f"data: {e}\n\n"
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


def _job_runtime_snapshot(job_id: str) -> tuple[Optional[dict], bool]:
    try:
        st = jobqueue.job_state(job_id)
    except _redis_pkg.exceptions.RedisError:
        return None, False
    except Exception:
        return None, False
    if not st:
        return None, True
    log = st.get("log") or []
    return {
        "stage": st.get("stage") or "",
        "percent": st.get("percent") or 0,
        "msg": st.get("msg") or "",
        "returncode": st.get("returncode"),
        "metrics": st.get("metrics") or [],
        "log_tail": log[-20:],
    }, True


@app.get("/api/history")
def list_history(user: dict = Depends(require_user)):
    rows = jobs_repo.list_history(user["id"])
    out = []
    can_read_runtime = True
    for row in rows:
        item = dict(row)
        runtime = None
        if can_read_runtime:
            runtime, can_read_runtime = _job_runtime_snapshot(item["id"])
        if runtime:
            item["runtime"] = runtime
            if not item.get("error") and runtime.get("stage") in ("failed", "interrupted", "error"):
                item["error"] = runtime.get("msg")
        out.append(item)
    return out


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
    except _redis_pkg.exceptions.RedisError:
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
    if (not target.is_file()
            and row["visibility"] == "public"
            and path == "video.mp4"):
        target = VIDEOS_DIR / f"{note_id}.mp4"
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
    shares_repo.revoke(safe)   # 分享 token 随笔记一起失效，避免悬挂链接
    return {"deleted": safe, "removed": removed}


# ============ 分享链接：owner 生成 token，持链接者免登录只读 ============
def _owned_note_or_404(note_id: str, user: dict) -> dict:
    safe = (note_id or "").strip()
    if not safe or "/" in safe or "\\" in safe or ".." in safe:
        raise HTTPException(404, "not found")
    row = notes_repo.get(safe)
    if row is None or row["owner_id"] != user["id"]:
        raise HTTPException(404, "not found")
    return row


@app.post("/api/notes/{note_id}/share")
def create_share(note_id: str, user: dict = Depends(require_user)):
    """生成（或返回已有）分享 token。幂等：同笔记多次调用同一 token。"""
    _owned_note_or_404(note_id, user)
    return {"token": shares_repo.ensure(note_id)}


@app.get("/api/notes/{note_id}/share")
def get_share(note_id: str, user: dict = Depends(require_user)):
    _owned_note_or_404(note_id, user)
    token = shares_repo.get_token(note_id)
    if token is None:
        raise HTTPException(404, "not shared")
    return {"token": token}


@app.delete("/api/notes/{note_id}/share")
def revoke_share(note_id: str, user: dict = Depends(require_user)):
    _owned_note_or_404(note_id, user)
    shares_repo.revoke(note_id)
    return {"ok": True}


@app.get("/api/shared/{token}")
def shared_meta(token: str):
    """token → 笔记基本信息（免登录）。前端 /s/{token} 页用来拿 note_id 和标题。"""
    note_id = shares_repo.resolve((token or "").strip())
    if note_id is None:
        raise HTTPException(404, "not found")
    row = notes_repo.get(note_id)
    if row is None:
        shares_repo.revoke(note_id)   # 笔记已删，顺手清掉悬挂 token
        raise HTTPException(404, "not found")
    return {"id": row["id"], "title": row["title"]}


@app.get("/api/shared/{token}/file/{path:path}")
def shared_file(token: str, path: str):
    """免登录按 token 托管笔记文件（summary/chapters/meta/keyframes/video）。
    与 note_file 同一路径解析；token 即授权，无效一律 404。"""
    note_id = shares_repo.resolve((token or "").strip())
    if note_id is None:
        raise HTTPException(404, "not found")
    row = notes_repo.get(note_id)
    if row is None:
        raise HTTPException(404, "not found")
    try:
        target = default_store.file_path(row["storage_path"], path)
    except ValueError:
        raise HTTPException(404, "not found")
    if not target.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(str(target))


# ============ 导出 docx：前端把 buildMarkdown 的产物 POST 过来，服务端转 Word ============
class ExportDocxReq(BaseModel):
    markdown: str
    filename: Optional[str] = None   # 不含扩展名也行，服务端兜底加 .docx


_EXPORT_MD_MAX = 2_000_000   # 2MB 文本上限，防滥用


def _safe_export_filename(raw: Optional[str]) -> str:
    """去掉路径分隔/控制字符，保留中文。空→ notes.docx。"""
    name = (raw or "").strip()
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", name).strip(". ")
    if not name:
        name = "notes"
    if not name.lower().endswith(".docx"):
        name += ".docx"
    return name[:120]


@app.post("/api/export/docx")
def export_docx(req: ExportDocxReq):
    """markdown → .docx（复用 scripts/md_to_docx.py，无 pandoc 依赖）。
    内容由客户端提供（与「导出 Markdown」同源、同语言），故无需鉴权——
    服务端只做格式转换，不读笔记数据。分享只读页（/s/{token}）同样可用。"""
    md = (req.markdown or "").strip()
    if not md:
        raise HTTPException(400, "markdown is required")
    if len(md) > _EXPORT_MD_MAX:
        raise HTTPException(413, "内容过大")
    try:
        import md_to_docx  # 惰性导入：python-docx 未装时其余接口不受影响
    except ImportError:
        raise HTTPException(501, "服务端未安装 python-docx，无法导出 Word")
    tmp = Path(tempfile.mkdtemp(prefix="notegen_export_"))
    try:
        md_path = tmp / "note.md"
        docx_path = tmp / "note.docx"
        md_path.write_text(md, encoding="utf-8")
        try:
            md_to_docx.convert(md_path, docx_path)
        except Exception:
            raise HTTPException(500, "转换失败，请重试")
        data = docx_path.read_bytes()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    filename = _safe_export_filename(req.filename)
    # RFC 5987：ASCII fallback + UTF-8 filename*（中文标题）
    disposition = (
        f'attachment; filename="export.docx"; '
        f"filename*=UTF-8''{quote(filename)}"
    )
    return Response(
        content=data,
        media_type=("application/vnd.openxmlformats-officedocument"
                    ".wordprocessingml.document"),
        headers={"Content-Disposition": disposition},
    )


# ============ 视频问答（接口契约见 docs/frontend-redesign.md §5） ============
class AskHistoryItem(BaseModel):
    question: str
    answer: str


class AskReq(BaseModel):
    question: str
    lang: Optional[str] = "zh"
    history: Optional[list[AskHistoryItem]] = None   # 追问上下文，最近 2 轮


def _note_accessible_or_404(note_id: str, user: dict) -> None:
    """QA 的访问控制与 note_file 一致：公开（DB 或旧静态 demo）所有登录用户可问，
    私有仅 owner；不存在/无权一律 404 不泄露存在性。"""
    safe = (note_id or "").strip()
    if not safe or "/" in safe or "\\" in safe or ".." in safe:
        raise HTTPException(404, "not found")
    row = notes_repo.get(safe)
    if row is not None:
        if row["visibility"] == "private" and row["owner_id"] != user["id"]:
            raise HTTPException(404, "not found")
        return
    if not (NOTES_DIR / safe / "summary.json").is_file():
        raise HTTPException(404, "not found")


@app.post("/api/notes/{note_id}/ask")
def ask_note(note_id: str, req: AskReq, user: dict = Depends(require_user)):
    _note_accessible_or_404(note_id, user)
    q = (req.question or "").strip()
    if not q:
        raise HTTPException(400, "question is required")
    if len(q) > 500:
        raise HTTPException(400, "问题太长（≤500 字）")
    lang = "en" if req.lang == "en" else "zh"
    history = [
        {"question": h.question.strip()[:500], "answer": h.answer.strip()[:1000]}
        for h in (req.history or [])[-2:]
        if h.question.strip() and h.answer.strip()
    ]
    try:
        qa_id = jobqueue.enqueue_ask(note_id, q, lang, user["id"],
                                     history=history or None)
    except jobqueue.ActiveQAError:
        raise HTTPException(409, "你已有一个问题在处理中，请等它回答完再问")
    except _redis_pkg.exceptions.RedisError:
        raise HTTPException(503, "队列服务暂不可用，请稍后再试")
    return {"qa_id": qa_id}


@app.get("/api/qa/{qa_id}")
def qa_status(qa_id: str, user: dict = Depends(require_user)):
    try:
        st = jobqueue.qa_state(qa_id)
    except _redis_pkg.exceptions.RedisError:
        raise HTTPException(503, "队列服务暂不可用，请稍后再试")
    if st is None or st.get("user_id") != user["id"]:
        raise HTTPException(404, "not found")
    return st


@app.get("/api/health")
def health():
    disk = maintenance.disk_status()
    try:
        jobqueue.get_kv().ping()
        depth = len(jobqueue.get_queue())
        return {"ok": not disk["low"], "redis": True, "queue_depth": depth,
                "disk": disk}
    except Exception as e:
        return {"ok": False, "redis": False, "error": str(e), "disk": disk}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)
