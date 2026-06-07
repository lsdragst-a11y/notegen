"""db.py：临时库建表幂等 + WAL + Row 工厂。无真实 data/notegen.db 写入。
Run: .venv/Scripts/python.exe scripts/test_db_schema.py"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import db  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

tmp = os.path.join(tempfile.mkdtemp(), "t.db")
db.set_db_path(tmp)
db.init_db()
db.init_db()  # 二次调用须幂等不抛

conn = db.connect()
try:
    names = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    for t in ("users", "email_verifications", "sessions", "notes", "jobs"):
        check(t in names, f"表 {t} 已建")
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    check(str(mode).lower() == "wal", f"journal_mode=WAL -> {mode}")
    r = conn.execute("PRAGMA table_info(users)").fetchall()
    check(r[0].keys()[0] == "cid", "Row 工厂可用（按列名取值）")
finally:
    conn.close()

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ==="); sys.exit(1)
print("=== ALL CHECKS PASSED ===")
