"""userdata.py：notes_repo / jobs_repo 读写。临时库，不碰真库/GPU。
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_userdata_unit.py"""
import sys, os, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import db  # noqa: E402
db.set_db_path(os.path.join(tempfile.mkdtemp(), "t.db"))
db.init_db()
from userdata import notes_repo, jobs_repo  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

# ---------- notes ----------
notes_repo.upsert(id="n1", owner_id="u1", visibility="private",
                  storage_path="data/user_notes/u1/n1", title="T1", domain="编程教学",
                  duration_sec=100, chunks=5, chapters=2, uploader="up", webpage_url="")
notes_repo.upsert(id="pub1", owner_id="admin", visibility="public",
                  storage_path="web/public/notes/pub1", title="P1", domain="学习",
                  duration_sec=50, chunks=3, chapters=1, uploader="", webpage_url="")
notes_repo.upsert(id="n2", owner_id="u2", visibility="private",
                  storage_path="data/user_notes/u2/n2", title="T2", domain="学习",
                  duration_sec=10, chunks=1, chapters=1, uploader="", webpage_url="")

g = notes_repo.get("n1")
check(g is not None and g["owner_id"] == "u1" and g["visibility"] == "private",
      "notes.get 取回归属/可见性")
check(notes_repo.get("nope") is None, "notes.get 未知 None")
check([n["id"] for n in notes_repo.list_public()] == ["pub1"], "list_public 仅公开")
mine = [n["id"] for n in notes_repo.list_mine("u1")]
check(mine == ["n1"], f"list_mine 仅本人私有 -> {mine}")
# upsert 幂等更新标题
notes_repo.upsert(id="n1", owner_id="u1", visibility="private",
                  storage_path="data/user_notes/u1/n1", title="T1b", domain="编程教学",
                  duration_sec=100, chunks=5, chapters=2, uploader="up", webpage_url="")
check(notes_repo.get("n1")["title"] == "T1b", "upsert 幂等覆盖标题")
notes_repo.delete("n1")
check(notes_repo.get("n1") is None, "notes.delete 生效")

# ---------- jobs ----------
jobs_repo.record("j1", "u1", "https://a/v", is_local=False, quality="360p", status="queued")
check(jobs_repo.get("j1")["status"] == "queued", "jobs.record 入库 queued")
check(jobs_repo.count_active("u1") == 1, "count_active 计 queued")
jobs_repo.update_status("j1", "running")
check(jobs_repo.count_active("u1") == 1, "running 仍算在飞")
jobs_repo.update_status("j1", "done", note_id="n1")
g = jobs_repo.get("j1")
check(g["status"] == "done" and g["note_id"] == "n1" and g["finished_at"] is not None,
      "终态 done 写 note_id + finished_at")
check(jobs_repo.count_active("u1") == 0, "done 不再算在飞")
jobs_repo.record("j2", "u1", "https://b/v", is_local=False, quality="best", status="queued")
jobs_repo.update_status("j2", "failed", error="boom")
check(jobs_repo.get("j2")["error"] == "boom", "failed 记 error")
hist = [j["id"] for j in jobs_repo.list_history("u1")]
check(set(hist) == {"j1", "j2"} and len(hist) == 2, f"list_history 全量 -> {hist}")
check(jobs_repo.list_history("u2") == [], "他人历史不串")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ==="); sys.exit(1)
print("=== ALL CHECKS PASSED ===")
