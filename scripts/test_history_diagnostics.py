"""History endpoint diagnostics: SQLite history enriched with Redis runtime data.
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_history_diagnostics.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

TMP = tempfile.mkdtemp()
os.environ["NOTEGEN_DB_PATH"] = os.path.join(TMP, "t.db")

import db  # noqa: E402
db.set_db_path(os.environ["NOTEGEN_DB_PATH"])

import fakeredis  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import jobqueue as JQ  # noqa: E402
import server  # noqa: E402
from userdata import jobs_repo  # noqa: E402

FAILS = []


def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)


SRV = fakeredis.FakeServer()
KV = fakeredis.FakeStrictRedis(server=SRV, decode_responses=True)
RQc = fakeredis.FakeStrictRedis(server=SRV)
JQ.set_connections(kv=KV, rq=RQc)


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


c1 = TestClient(server.app)
c2 = TestClient(server.app)
uid1 = signup(c1, "diag1@x.com")
uid2 = signup(c2, "diag2@x.com")

jobs_repo.record("FAIL_DIAG", uid1, "https://fail/v", is_local=False, quality="360p", status="queued")
jobs_repo.update_status("FAIL_DIAG", "failed")
jobs_repo.record("OTHER_DIAG", uid2, "https://other/v", is_local=False, quality="360p", status="queued")
jobs_repo.update_status("OTHER_DIAG", "failed", error="other boom")

JQ.create_job("FAIL_DIAG", "https://fail/v", {"quality": "360p", "user_id": uid1})
JQ.append_log("FAIL_DIAG", "[asr] started")
JQ.append_log("FAIL_DIAG", "[error] no output")
JQ.record_stage_start("FAIL_DIAG", {"stage": "asr", "label": "语音识别", "i": 4, "n": 18}, now=100.0)
metrics = JQ.finish_stage_metrics("FAIL_DIAG", status="failed", now=105.5)
JQ.set_progress("FAIL_DIAG", stage="failed", percent=0, msg="pipeline 无输出",
                returncode=1, metrics=metrics)

r = c1.get("/api/history")
hist = r.json()
check(r.status_code == 200 and len(hist) == 1, f"u1 history one row -> {r.status_code} {hist}")
row = hist[0]
check(row["id"] == "FAIL_DIAG" and row["error"] == "pipeline 无输出",
      f"Redis failed msg fills missing SQLite error -> {row}")
check(row["runtime"]["metrics"][0]["duration_sec"] == 5.5,
      f"runtime metrics exposed -> {row.get('runtime')}")
check(row["runtime"]["log_tail"][-1] == "[error] no output",
      f"runtime log tail exposed -> {row.get('runtime')}")
check(row["runtime"]["returncode"] == "1", f"returncode exposed as Redis string -> {row.get('runtime')}")

r = c2.get("/api/history")
hist2 = r.json()
check(r.status_code == 200 and len(hist2) == 1 and hist2[0]["id"] == "OTHER_DIAG",
      f"u2 only sees own history -> {r.status_code} {hist2}")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ===")
    sys.exit(1)
print("=== ALL CHECKS PASSED ===")
