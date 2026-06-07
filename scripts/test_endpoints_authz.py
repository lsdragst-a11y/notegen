"""端点门禁烟测：匿名访问受保护端点应 401；公开端点开放。临时库。
完整多用户队列链路在 test_multiuser_integration.py。
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_endpoints_authz.py"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))  # repo root: 找到 server.py
os.environ["NOTEGEN_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
import db  # noqa: E402
db.set_db_path(os.environ["NOTEGEN_DB_PATH"])
from fastapi.testclient import TestClient  # noqa: E402
import server  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

c = TestClient(server.app)

# 匿名受保护端点 → 401
for method, path in [("post", "/api/generate"), ("get", "/api/notes/mine"),
                     ("get", "/api/history")]:
    r = getattr(c, method)(path, **{"json": {}} if method == "post" else {})
    check(r.status_code == 401, f"匿名 {method.upper()} {path} -> 401 (got {r.status_code})")

# 公开端点开放（空库返空 list）
r = c.get("/api/notes/public")
check(r.status_code == 200 and r.json() == [], f"匿名 /api/notes/public 200 [] -> {r.status_code}")

# 私有文件端点：未知 note 匿名 → 404（不泄露）
r = c.get("/api/notes/ghost/file/summary.json")
check(r.status_code == 404, f"匿名取未知私有文件 404 -> {r.status_code}")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ==="); sys.exit(1)
print("=== ALL CHECKS PASSED ===")
