"""jobqueue 断言：idempotency_key 稳定性、job hash 读写、状态机、事件 list、
幂等 enqueue 去重。用 fakeredis，无需真 Redis / GPU。
Run: .venv/Scripts/python.exe scripts/test_jobqueue.py"""
import sys
import os
import json
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

# (c2) stage metrics: marker boundaries are persisted and emitted on terminal events
JQ.record_stage_start("job1", {"stage": "asr", "label": "ASR", "i": 4, "n": 18}, now=100.0)
JQ.record_stage_start("job1", {"stage": "chunk", "label": "Chunk", "i": 5, "n": 18}, now=103.25)
metrics = JQ.finish_stage_metrics("job1", status="done", now=105.0)
check(len(metrics) == 2 and metrics[0]["duration_sec"] == 3.25 and metrics[1]["status"] == "done",
      f"(c2) metrics close previous/current stages -> {metrics}")
st = JQ.job_state("job1")
check(st["metrics"][0]["stage"] == "asr" and st["metrics"][1]["duration_sec"] == 1.75,
      f"(c2) job_state exposes parsed metrics -> {st['metrics']}")
old_n = n2
JQ.set_progress("job1", stage="done", percent=100, msg="done again")
evs3, n3 = JQ.read_events("job1", old_n)
last_event = json.loads(evs3[-1])
check(n3 == old_n + 1 and last_event["metrics"][1]["stage"] == "chunk",
      f"(c2) terminal event includes metrics -> {last_event}")

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

# (g) done job：note 还在 -> 复用；note 被删 -> 强制新建（防前端跳到已失踪 note）
gopts = {"quality": "best", "user_id": "ug"}
gj, _ = JQ.enqueue_generate("https://g.com/v", gopts)
JQ.set_progress(gj, stage="done", percent=100, msg="完成", note_id="ug_BVg")
_orig_ne = JQ._note_exists
JQ._note_exists = lambda nid: True
gj2, gnew2 = JQ.enqueue_generate("https://g.com/v", dict(gopts))
check(gj2 == gj and gnew2 is False, "(g) done 且 note 在 -> 复用同 job")
JQ._note_exists = lambda nid: False
gj3, gnew3 = JQ.enqueue_generate("https://g.com/v", dict(gopts))
check(gnew3 is True and gj3 != gj, "(g) done 但 note 已删 -> 新 job")
JQ._note_exists = _orig_ne

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ===")
    sys.exit(1)
print("=== ALL CHECKS PASSED ===")
