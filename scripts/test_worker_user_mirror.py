"""worker 带 user_id：enqueue→SimpleWorker→私有 publish→notes 行写入→jobs 终态 done。
fakeredis + 临时 SQLite + mock subprocess/publish_private。不碰 GPU。
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_worker_user_mirror.py"""
import sys, os, socket, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import db  # noqa: E402
db.set_db_path(os.path.join(tempfile.mkdtemp(), "t.db"))
db.init_db()
import fakeredis  # noqa: E402
from rq import SimpleWorker  # noqa: E402
from rq.timeouts import TimerDeathPenalty  # noqa: E402
import jobqueue as JQ  # noqa: E402
import worker_tasks as WT  # noqa: E402
import service_common as SC  # noqa: E402
from userdata import notes_repo, jobs_repo  # noqa: E402

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
    w = SimpleWorker([JQ.get_queue()], connection=conn, prepare_for_work=False)
    w.hostname = socket.gethostname(); w.pid = os.getpid()
    w.death_penalty_class = TimerDeathPenalty
    w.work(burst=True, logging_level="ERROR")

conn = fresh()
WT._run_pipeline_subprocess = lambda j, s, o: ("BVuser_p0", 0)
# 假私有发布：不真 copy，返回字段
SC.publish_private = lambda stem, uid: (
    stem, f"data/user_notes/{uid}/{stem}",
    {"title": "私有笔记", "domain": "学习", "duration_sec": 60,
     "chunks": 4, "chapters": 2, "uploader": "u", "webpage_url": ""})

opts = {"quality": "360p", "user_id": "u1"}
jid, _ = JQ.enqueue_generate("https://x/v", opts)
# enqueue 镜像由 server 端做；这里手动补一行 queued 模拟 api 已记录
jobs_repo.record(jid, "u1", "https://x/v", is_local=False, quality="360p", status="queued")
run_burst(conn)

st = JQ.job_state(jid)
check(st["stage"] == "done" and st["note_id"] == "BVuser_p0", "Redis 仍 done(热路径不变)")
note = notes_repo.get("BVuser_p0")
check(note is not None and note["owner_id"] == "u1" and note["visibility"] == "private",
      "私有 notes 行写入(owner/visibility)")
check(note["title"] == "私有笔记" and note["chapters"] == 2, "notes 展示字段镜像")
job = jobs_repo.get(jid)
check(job["status"] == "done" and job["note_id"] == "BVuser_p0", "jobs 终态镜像 done")
check(job["finished_at"] is not None, "jobs.finished_at 已写")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ==="); sys.exit(1)
print("=== ALL CHECKS PASSED ===")
