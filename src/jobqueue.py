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
    """稳定 key：归一化 source + quality + is_local + user_id。
    含 user_id 使两用户提交同一 URL 各得各自私有笔记，互不复用。"""
    norm = (source or "").strip().lower()
    payload = json.dumps(
        {"s": norm, "q": opts.get("quality") or "best",
         "l": bool(opts.get("is_local")), "u": opts.get("user_id") or ""},
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
