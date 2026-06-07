"""终审两修：A) jobs_repo.reconcile_orphans() 把卡死 running 标 interrupted 解锁在飞名额；
B) /api/jobs/{id}/retry 只对 failed/interrupted 放行，done/queued/running → 409（不静默复用旧 job）。
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_review_fixes.py"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))  # repo root for `import server`
TMP = tempfile.mkdtemp()
os.environ["NOTEGEN_DB_PATH"] = os.path.join(TMP, "t.db")
import db  # noqa: E402
db.set_db_path(os.environ["NOTEGEN_DB_PATH"])
import fakeredis  # noqa: E402
import jobqueue as JQ  # noqa: E402
from userdata import jobs_repo  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import server  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

SRV = fakeredis.FakeServer()
KV = fakeredis.FakeStrictRedis(server=SRV, decode_responses=True)
RQc = fakeredis.FakeStrictRedis(server=SRV)
JQ.set_connections(kv=KV, rq=RQc)

# ---------- A) reconcile_orphans ----------
jobs_repo.record("J_run", "uX", "https://a/v", is_local=False, quality="360p", status="running")
jobs_repo.record("J_que", "uX", "https://b/v", is_local=False, quality="360p", status="queued")
check(jobs_repo.count_active("uX") == 2, "起始在飞 2(running+queued)")
n = jobs_repo.reconcile_orphans()
check(n == 1, f"reconcile 处理 1 条 running -> {n}")
check(jobs_repo.get("J_run")["status"] == "interrupted", "running -> interrupted")
check(jobs_repo.get("J_que")["status"] == "queued", "queued 不动")
check(jobs_repo.get("J_run")["finished_at"] is not None, "interrupted 写 finished_at")
check(jobs_repo.count_active("uX") == 1, "在飞名额释放(仅剩 queued)")

# ---------- B) retry 只放行 failed/interrupted ----------
def signup(client, email):
    client.post("/api/auth/register",
                json={"email": email, "password": "pw123456", "display_name": email})
    conn = db.connect()
    tok = conn.execute(
        "SELECT ev.token FROM email_verifications ev JOIN users u ON u.id=ev.user_id "
        "WHERE u.email=?", (email.lower(),)).fetchone()["token"]
    uid = conn.execute("SELECT id FROM users WHERE email=?", (email.lower(),)).fetchone()["id"]
    conn.close()
    client.get(f"/api/auth/verify?token={tok}")
    r = client.post("/api/auth/login", json={"email": email, "password": "pw123456"})
    assert r.status_code == 200, r.text
    return uid

c = TestClient(server.app)
uid = signup(c, "rf@x.com")

# done 任务：retry → 409（修前会静默复用旧 job 返 200）
jobs_repo.record("DONE1", uid, "https://done/v", is_local=False, quality="360p", status="queued")
jobs_repo.update_status("DONE1", "done", note_id="N1")
r = c.post("/api/jobs/DONE1/retry")
check(r.status_code == 409, f"done 任务 retry 409 -> {r.status_code} {r.text[:80]}")

# failed 任务：retry → 200 且给出新 job_id
jobs_repo.record("FAIL1", uid, "https://fail/v", is_local=False, quality="360p", status="queued")
jobs_repo.update_status("FAIL1", "failed", error="boom")
r = c.post("/api/jobs/FAIL1/retry")
check(r.status_code == 200 and r.json().get("job_id") and r.json()["job_id"] != "FAIL1",
      f"failed 任务 retry 200 + 新 job -> {r.status_code} {r.text[:80]}")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ==="); sys.exit(1)
print("=== ALL CHECKS PASSED ===")
