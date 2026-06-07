"""鉴权 API（TestClient）：注册→未验证登录 403→验证→登录下发 cookie→me→登出→me 401。
临时库；不需 Redis（不碰队列端点）。验证 token 直接从 DB 取，跳过控制台解析。
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_auth_api.py"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))  # repo root: 找到 server.py
os.environ["NOTEGEN_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
import db  # noqa: E402
db.set_db_path(os.environ["NOTEGEN_DB_PATH"])
from fastapi.testclient import TestClient  # noqa: E402
import server  # noqa: E402
import authdeps as AD  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

c = TestClient(server.app)

r = c.post("/api/auth/register",
           json={"email": "Bob@X.com", "password": "pw123456", "display_name": "Bob"})
check(r.status_code == 201, f"注册 201 -> {r.status_code}")

# 未验证 → 登录 403
r = c.post("/api/auth/login", json={"email": "bob@x.com", "password": "pw123456"})
check(r.status_code == 403, f"未验证登录 403 -> {r.status_code}")

# 从 DB 取验证 token（替代解析控制台）
conn = db.connect()
tok = conn.execute("SELECT token FROM email_verifications").fetchone()["token"]
conn.close()
r = c.get(f"/api/auth/verify?token={tok}")
check(r.status_code == 200, f"验证 200 -> {r.status_code}")

# 登录成功 + 下发 httpOnly cookie
r = c.post("/api/auth/login", json={"email": "bob@x.com", "password": "pw123456"})
check(r.status_code == 200, f"验证后登录 200 -> {r.status_code}")
check(AD.SESSION_COOKIE in r.cookies, "登录下发会话 cookie")
check(r.json()["email"] == "bob@x.com", "登录返回 profile")

# 错密码统一文案
rb = c.post("/api/auth/login", json={"email": "bob@x.com", "password": "WRONG"})
check(rb.status_code == 401, f"错密码 401 -> {rb.status_code}")

# me（TestClient 自动带 cookie jar）
r = c.get("/api/auth/me")
check(r.status_code == 200 and r.json()["email"] == "bob@x.com", "me 返回当前用户")

# 重复邮箱注册 409
r = c.post("/api/auth/register",
           json={"email": "bob@x.com", "password": "x2345678", "display_name": "B2"})
check(r.status_code == 409, f"重复邮箱 409 -> {r.status_code}")

# 登出 → me 401
r = c.post("/api/auth/logout")
check(r.status_code == 200, "登出 200")
r = c.get("/api/auth/me")
check(r.status_code == 401, f"登出后 me 401 -> {r.status_code}")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ==="); sys.exit(1)
print("=== ALL CHECKS PASSED ===")
