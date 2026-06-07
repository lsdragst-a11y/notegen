"""多用户端到端：注册/验证/登录→提交→worker→私有笔记+历史→跨用户隔离/404→
在飞 1 上限→按用户幂等。TestClient + fakeredis + SimpleWorker(burst)，mock pipeline。
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_multiuser_integration.py"""
import sys, os, socket, tempfile
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))  # repo root for `import server`
TMP = tempfile.mkdtemp()
os.environ["NOTEGEN_DB_PATH"] = os.path.join(TMP, "t.db")
import db  # noqa: E402
db.set_db_path(os.environ["NOTEGEN_DB_PATH"])
import fakeredis  # noqa: E402
from rq import SimpleWorker  # noqa: E402
from rq.timeouts import TimerDeathPenalty  # noqa: E402
import jobqueue as JQ  # noqa: E402
import worker_tasks as WT  # noqa: E402
import service_common as SC  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import server  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

# 单一 fakeredis server，api 与 worker 共享
SRV = fakeredis.FakeServer()
KV = fakeredis.FakeStrictRedis(server=SRV, decode_responses=True)
RQc = fakeredis.FakeStrictRedis(server=SRV)
JQ.set_connections(kv=KV, rq=RQc)

# mock pipeline + 私有发布（真写一个 summary.json 让文件端点可服务）
_counter = {"n": 0}
def fake_sub(job_id, source, opts):
    _counter["n"] += 1
    return f"BV{_counter['n']}_p0", 0
WT._run_pipeline_subprocess = fake_sub

def fake_publish_private(stem, uid):
    d = Path(TMP) / "user_notes" / uid / stem
    d.mkdir(parents=True, exist_ok=True)
    (d / "summary.json").write_text('[{"start":0,"end":30}]', encoding="utf-8")
    return stem, str(d), {"title": "我的笔记", "domain": "学习", "duration_sec": 30,
                          "chunks": 1, "chapters": 1, "uploader": "", "webpage_url": ""}
SC.publish_private = fake_publish_private

def run_burst():
    w = SimpleWorker([JQ.get_queue()], connection=RQc, prepare_for_work=False)
    w.hostname = socket.gethostname(); w.pid = os.getpid()
    w.death_penalty_class = TimerDeathPenalty
    w.work(burst=True, logging_level="ERROR")

def signup(client, email):
    client.post("/api/auth/register",
                json={"email": email, "password": "pw123456", "display_name": email})
    conn = db.connect()
    tok = conn.execute(
        "SELECT ev.token FROM email_verifications ev JOIN users u ON u.id=ev.user_id "
        "WHERE u.email=?", (email.lower(),)).fetchone()["token"]
    conn.close()
    client.get(f"/api/auth/verify?token={tok}")
    r = client.post("/api/auth/login", json={"email": email, "password": "pw123456"})
    assert r.status_code == 200, r.text

c1 = TestClient(server.app)
c2 = TestClient(server.app)
signup(c1, "u1@x.com")
signup(c2, "u2@x.com")

# --- 每用户在飞 1：u1 提交 A(queued) 后提交 B → 409 ---
r = c1.post("/api/generate", json={"url": "https://a/v", "quality": "360p"})
check(r.status_code == 200, f"u1 提交 A 200 -> {r.status_code}")
jidA = r.json()["job_id"]
r = c1.post("/api/generate", json={"url": "https://b/v", "quality": "360p"})
check(r.status_code == 409, f"u1 在飞时第二单 409 -> {r.status_code}")

run_burst()  # 处理 A

# --- u1 历史/私有库 ---
hist = c1.get("/api/history").json()
check(len(hist) == 1 and hist[0]["status"] == "done", f"u1 历史 1 条 done -> {hist}")
noteid = hist[0]["note_id"]
mine = c1.get("/api/notes/mine").json()
check(len(mine) == 1 and mine[0]["id"] == noteid, "u1 私有库 1 条")

# --- u2 看不到 u1 的私有 ---
check(c2.get("/api/notes/mine").json() == [], "u2 私有库为空")
check(c2.get("/api/history").json() == [], "u2 历史为空")

# --- 私有文件：owner 200 / 非 owner 404 / 匿名 404 ---
r = c1.get(f"/api/notes/{noteid}/file/summary.json")
check(r.status_code == 200, f"owner 取私有文件 200 -> {r.status_code}")
r = c2.get(f"/api/notes/{noteid}/file/summary.json")
check(r.status_code == 404, f"非 owner 取私有文件 404 -> {r.status_code}")
anon = TestClient(server.app)
r = anon.get(f"/api/notes/{noteid}/file/summary.json")
check(r.status_code == 404, f"匿名取私有文件 404 -> {r.status_code}")
# 路径越级拦截
r = c1.get(f"/api/notes/{noteid}/file/../../../etc/passwd")
check(r.status_code == 404, f"路径越级 404 -> {r.status_code}")

# --- u2 跨用户取 u1 的 job → 404 ---
r = c2.get(f"/api/jobs/{jidA}")
check(r.status_code == 404, f"u2 取 u1 job 404 -> {r.status_code}")
check(c1.get(f"/api/jobs/{jidA}").status_code == 200, "u1 取自己 job 200")

# --- 按用户幂等：u1 同 URL 再提（A 已 done）→ 复用同 job，历史不增 ---
r = c1.post("/api/generate", json={"url": "https://a/v", "quality": "360p"})
check(r.status_code == 200 and r.json()["job_id"] == jidA, "u1 同 URL 命中幂等(同 job)")
check(len(c1.get("/api/history").json()) == 1, "幂等不新增历史行")

# --- 不同用户同 URL → 各自独立 job ---
r = c2.post("/api/generate", json={"url": "https://a/v", "quality": "360p"})
check(r.status_code == 200 and r.json()["job_id"] != jidA, "u2 同 URL 不复用 u1 的 job")
run_burst()
m2 = c2.get("/api/notes/mine").json()
check(len(m2) == 1 and m2[0]["id"] != noteid, "u2 得到独立私有笔记")

# --- 公开展示区匿名可读（此处空，断结构）---
check(anon.get("/api/notes/public").status_code == 200, "匿名可读公开展示区")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ==="); sys.exit(1)
print("=== ALL CHECKS PASSED ===")
