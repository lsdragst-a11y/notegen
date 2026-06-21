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
QA_TIMEOUT = 600    # 单条 QA：模型冷加载 ~1min + 生成，10min 封顶
QA_TTL = 24 * 3600  # qa:{id} 结果保留一天，过期自动清
REDIS_CONNECT_TIMEOUT = float(os.environ.get("NOTEGEN_REDIS_CONNECT_TIMEOUT", "1.0"))
REDIS_KV_TIMEOUT = float(os.environ.get("NOTEGEN_REDIS_KV_TIMEOUT", "2.0"))

_kv = None   # decode_responses=True：job hash / list
_rq = None   # bytes：RQ Queue 专用


def set_connections(kv=None, rq=None) -> None:
    """测试钩子：注入 fakeredis 连接。"""
    global _kv, _rq
    _kv, _rq = kv, rq


def get_kv():
    global _kv
    if _kv is None:
        _kv = redis.Redis.from_url(
            REDIS_URL, decode_responses=True,
            socket_connect_timeout=REDIS_CONNECT_TIMEOUT,
            socket_timeout=REDIS_KV_TIMEOUT,
        )
    return _kv


def get_rq():
    global _rq
    if _rq is None:
        _rq = redis.Redis.from_url(
            REDIS_URL,
            socket_connect_timeout=REDIS_CONNECT_TIMEOUT,
        )
    return _rq


def get_queue() -> Queue:
    return Queue("default", connection=get_rq())


def get_qa_queue() -> Queue:
    """QA 专用高优队列。worker 监听 ["qa", "default"]（列表序即优先级），
    问答插队在排队 pipeline 任务之前，但仍与运行中的任务串行——单 worker
    并发=1 的铁律不破。"""
    return Queue("qa", connection=get_rq())


def _job_key(jid: str) -> str: return f"job:{jid}"
def _events_key(jid: str) -> str: return f"job:{jid}:events"
def _log_key(jid: str) -> str: return f"job:{jid}:log"
def _idem_key(k: str) -> str: return f"idem:{k}"


def _decode_metrics(raw) -> list[dict]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return data if isinstance(data, list) else []


def _store_metrics(jid: str, metrics: list[dict]) -> None:
    get_kv().hset(_job_key(jid), mapping={
        "metrics_json": json.dumps(metrics, ensure_ascii=False),
    })


def stage_metrics(jid: str) -> list[dict]:
    return _decode_metrics(get_kv().hget(_job_key(jid), "metrics_json"))


def record_stage_start(jid: str, marker: dict, now: Optional[float] = None) -> list[dict]:
    """Record a pipeline stage boundary from a [PROGRESS] marker."""
    ts = time.time() if now is None else float(now)
    metrics = stage_metrics(jid)
    stage = str(marker.get("stage") or "")
    label = str(marker.get("label") or stage)

    if metrics and metrics[-1].get("status") == "running":
        if metrics[-1].get("stage") == stage:
            return metrics
        start_t = float(metrics[-1].get("start_t") or ts)
        metrics[-1]["end_t"] = ts
        metrics[-1]["duration_sec"] = round(max(0.0, ts - start_t), 3)
        metrics[-1]["status"] = "done"

    try:
        i = int(marker.get("i") or len(metrics) + 1)
    except (ValueError, TypeError):
        i = len(metrics) + 1
    try:
        n = int(marker.get("n") or 0)
    except (ValueError, TypeError):
        n = 0

    metrics.append({
        "stage": stage,
        "label": label,
        "i": i,
        "n": n,
        "start_t": ts,
        "end_t": None,
        "duration_sec": None,
        "status": "running",
    })
    _store_metrics(jid, metrics)
    return metrics


def finish_stage_metrics(jid: str, status: str = "done",
                         now: Optional[float] = None) -> list[dict]:
    ts = time.time() if now is None else float(now)
    metrics = stage_metrics(jid)
    if metrics and metrics[-1].get("status") == "running":
        start_t = float(metrics[-1].get("start_t") or ts)
        metrics[-1]["end_t"] = ts
        metrics[-1]["duration_sec"] = round(max(0.0, ts - start_t), 3)
        metrics[-1]["status"] = status
        _store_metrics(jid, metrics)
    return metrics


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
        "user_id": opts.get("user_id") or "",
        "stage": "queued", "percent": "0", "msg": "排队中",
        "metrics_json": "[]",
        "created": str(time.time()),
    })


def set_progress(jid: str, *, stage=None, percent=None, msg=None,
                 note_id=None, returncode=None, metrics=None) -> None:
    """更新 job hash + 追加一条事件（仅含变化字段 + 时间戳）供 SSE 消费。"""
    kv = get_kv()
    if metrics is None and stage in ("done", "failed", "interrupted"):
        metrics = finish_stage_metrics(jid, str(stage))
    fields = {}
    for k, v in (("stage", stage), ("percent", percent), ("msg", msg),
                 ("note_id", note_id), ("returncode", returncode)):
        if v is not None:
            fields[k] = str(v)
    if metrics is not None:
        fields["metrics_json"] = json.dumps(metrics, ensure_ascii=False)
    if fields:
        kv.hset(_job_key(jid), mapping=fields)
    ev = {k: v for k, v in fields.items() if k != "metrics_json"}
    if metrics is not None:
        ev["metrics"] = metrics
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
    h["metrics"] = _decode_metrics(h.pop("metrics_json", "[]"))
    h["log"] = kv.lrange(_log_key(jid), 0, -1)
    return h


def job_stage(jid: str) -> Optional[str]:
    """只读 stage 单字段（HGET）。SSE 轮询循环用：job_state 每次 HGETALL +
    拉整段 log（最多 500 行），0.4s 一次纯属浪费。job 不存在 → None。"""
    return get_kv().hget(_job_key(jid), "stage")


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


# ============ QA（视频问答）：qa:{id} hash + 每用户单飞限制 ============

class ActiveQAError(Exception):
    """该用户已有进行中的 QA。"""


def _qa_key(qid: str) -> str: return f"qa:{qid}"
def _qa_active_key(uid: str) -> str: return f"qa:active:{uid}"


def create_qa(qid: str, note_id: str, question: str, lang: str, user_id: str) -> None:
    kv = get_kv()
    kv.hset(_qa_key(qid), mapping={
        "id": qid, "note_id": note_id, "question": question,
        "lang": lang, "user_id": user_id,
        "status": "queued", "created": str(time.time()),
    })
    kv.expire(_qa_key(qid), QA_TTL)


def set_qa(qid: str, *, status=None, result=None, error=None) -> None:
    kv = get_kv()
    fields = {}
    if status is not None:
        fields["status"] = str(status)
    if result is not None:
        fields["result_json"] = json.dumps(result, ensure_ascii=False)
    if error is not None:
        fields["error"] = str(error)[:500]
    if fields:
        kv.hset(_qa_key(qid), mapping=fields)
        kv.expire(_qa_key(qid), QA_TTL)


def qa_state(qid: str) -> Optional[dict]:
    h = get_kv().hgetall(_qa_key(qid))
    if not h:
        return None
    raw = h.pop("result_json", None)
    if raw:
        try:
            h["result"] = json.loads(raw)
        except ValueError:
            h["result"] = None
    if h.get("status") == "queued":
        try:
            h["queue_ahead"] = get_qa_queue().get_job_position(qid)
        except Exception:
            pass
    return h


def enqueue_ask(note_id: str, question: str, lang: str, user_id: str,
                history: Optional[list[dict]] = None) -> str:
    """每用户同时只允许 1 个进行中 QA（GPU 串行，排队多了纯堵）。
    active 指针带 QA_TTL 过期，残留不会永久卡死。
    history: [{question, answer}] 追问上下文，直接随任务参数传给 worker。"""
    kv = get_kv()
    existing = kv.get(_qa_active_key(user_id))
    if existing:
        st = qa_state(existing)
        if st and st.get("status") in ("queued", "running"):
            raise ActiveQAError(existing)
    qid = uuid.uuid4().hex[:12]
    create_qa(qid, note_id, question, lang, user_id)
    import worker_tasks  # lazy 避免 import 环
    get_qa_queue().enqueue(
        worker_tasks.run_ask, qid, note_id, question, lang, history,
        job_id=qid, job_timeout=QA_TIMEOUT,
    )
    kv.set(_qa_active_key(user_id), qid, ex=QA_TIMEOUT)
    return qid


def _note_exists(note_id: Optional[str]) -> bool:
    """done job 的产出 note 是否还在库里。用户删笔记后 idem 仍指向那个 done job，
    不校验就会把前端导到一个已失踪的 note。DB 不可用时保守返回 True 不阻塞入队。"""
    if not note_id:
        return False
    try:
        import userdata  # lazy 避免 import 环
        return userdata.notes_repo.get(note_id) is not None
    except Exception:
        return True


def _reusable(st: Optional[dict]) -> bool:
    """命中的 job 能否复用：失败/中断 → 否（放行重提）；私有 done 但 note 已删 → 否（强制
    新建，否则前端跳到失踪 note）；其余 in-flight（queued/running）及无 user 的公开 done → 是。"""
    if not st:
        return False
    stage = st.get("stage")
    if stage in ("failed", "interrupted"):
        return False
    if stage == "done" and st.get("user_id"):
        return _note_exists(st.get("note_id"))
    return True


def enqueue_generate(source: str, opts: dict) -> tuple[str, bool]:
    """幂等入队。返回 (job_id, is_new)。命中已有 in-flight/done 任务则复用。"""
    kv = get_kv()
    key = idempotency_key(source, opts)
    existing = kv.get(_idem_key(key))
    if existing and _reusable(job_state(existing)):
        return existing, False
    jid = uuid.uuid4().hex[:12]
    create_job(jid, source, opts)
    import worker_tasks  # lazy 避免 import 环
    get_queue().enqueue(
        worker_tasks.run_generate, jid, source, opts,
        job_id=jid, retry=Retry(max=2, interval=[10, 30]),
        job_timeout=JOB_TIMEOUT,
    )
    # idem 映射必须在 enqueue 成功之后写：否则 enqueue 抛异常时 idem 指向一个
    # 永远 stage=queued 却没入队的死 job，_reusable 会一直复用它把用户卡死
    kv.set(_idem_key(key), jid)
    return jid, True
