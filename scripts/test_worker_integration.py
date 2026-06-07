"""worker_tasks 集成断言：enqueue→SimpleWorker→Redis 状态→done 全链路、
output-fallback、失败入 failed registry、幂等命中、并发=1 串行、Retry 配置。
mock 掉 subprocess 与 publish，不碰 GPU/文件系统。用 fakeredis。
Run: .venv/Scripts/python.exe scripts/test_worker_integration.py"""
import sys
import os
import socket
import time
import threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import fakeredis  # noqa: E402
from rq import SimpleWorker  # noqa: E402
from rq.timeouts import TimerDeathPenalty  # noqa: E402
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
    """SimpleWorker 同进程串行消费完队列即退（burst）。
    fakeredis 的 client_list() 不含 'addr' 字段，会让 RQ worker 初始化 KeyError，
    故用 prepare_for_work=False 跳过该探测，手动补 hostname/pid（register_birth 需要）。
    Windows 无 signal.SIGALRM，death penalty 必须用 TimerDeathPenalty（生产 worker 同样需要）。"""
    w = SimpleWorker([JQ.get_queue()], connection=conn, prepare_for_work=False)
    w.hostname = socket.gethostname()
    w.pid = os.getpid()
    w.death_penalty_class = TimerDeathPenalty
    w.work(burst=True, logging_level="ERROR")

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
