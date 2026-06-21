"""阶段 B 硬化 API 断言（TestClient）：登录/注册限速 429、上传上限 413、
低磁盘 507 拒单、/api/health 暴露磁盘信息。临时库；不需 Redis（上传走到
enqueue 一步拿 503 即证明前面的闸门都没拦错）。
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_hardening_api.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))  # repo root: 找到 server.py

# 限速/上限旋钮必须在 import server 之前定好（模块级读取）
os.environ["NOTEGEN_LOGIN_LIMIT"] = "5/60"
os.environ["NOTEGEN_REGISTER_LIMIT"] = "4/60"
os.environ["NOTEGEN_MAX_UPLOAD_MB"] = "1"
os.environ["NOTEGEN_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
for k in ("NOTEGEN_SMTP_HOST", "NOTEGEN_SMTP_USER", "NOTEGEN_SMTP_PASS"):
    os.environ.pop(k, None)

import db  # noqa: E402
db.set_db_path(os.environ["NOTEGEN_DB_PATH"])
from fastapi.testclient import TestClient  # noqa: E402
import server  # noqa: E402
import maintenance  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

c = TestClient(server.app)


def _register(i):
    return c.post("/api/auth/register", json={
        "email": f"user{i}@x.com", "password": "pw123456",
        "display_name": f"u{i}"})


# ============ (a) 注册 + 验证 + 登录（消耗 register 1 hit / login 1 hit） ============
r = _register(0)
check(r.status_code == 201, f"注册 201（{r.status_code}）")
check("控制台" in r.json().get("message", ""), "无 SMTP 配置 → 控制台链接提示")
conn = db.connect()
tok = conn.execute("SELECT token FROM email_verifications").fetchone()["token"]
conn.close()
check(c.get(f"/api/auth/verify?token={tok}").status_code == 200, "邮箱验证 200")
r = c.post("/api/auth/login", json={"email": "user0@x.com", "password": "pw123456"})
check(r.status_code == 200, f"登录 200（{r.status_code}）")

# ============ (b) 上传上限（MAX=1MB） ============
big = b"0" * (3 * 1024 * 1024)   # 3MB > 1MB 上限 + 1MB multipart 余量
r = c.post("/api/upload", files={"file": ("v.mp4", big, "video/mp4")})
check(r.status_code == 413, f"3MB 上传 → 413（{r.status_code}）")
small = b"0" * (200 * 1024)      # 200KB 过闸门，走到 enqueue 因无 Redis 拿 503
r = c.post("/api/upload", files={"file": ("v.mp4", small, "video/mp4")})
check(r.status_code == 503, f"小文件过闸门到 enqueue → 503 无 Redis（{r.status_code}）")

# ============ (c) 低磁盘 507 拒单 ============
real_disk = maintenance.disk_status
maintenance.disk_status = lambda *a, **k: {
    "total_gb": 100.0, "free_gb": 5.0, "free_ratio": 0.05, "low": True}
r = c.post("/api/generate", json={"url": "https://example.com/v"})
check(r.status_code == 507, f"低磁盘 generate → 507（{r.status_code}）")
r = c.post("/api/upload", files={"file": ("v.mp4", small, "video/mp4")})
check(r.status_code == 507, f"低磁盘 upload → 507（{r.status_code}）")
maintenance.disk_status = real_disk

# ============ (d) /api/health 暴露磁盘 ============
r = c.get("/api/health")
d = r.json().get("disk", {})
check({"total_gb", "free_gb", "free_ratio", "low"} <= set(d.keys()),
      f"health 带 disk 字段（{sorted(d.keys())}）")

# ============ (e) 登录限速 5/60：已用 1，再来 4 次错密码到顶，第 6 次 429 ============
for i in range(4):
    r = c.post("/api/auth/login", json={"email": "user0@x.com", "password": "wrong!!!!"})
    check(r.status_code == 401, f"错密码 #{i+1} → 401（{r.status_code}）")
r = c.post("/api/auth/login", json={"email": "user0@x.com", "password": "pw123456"})
check(r.status_code == 429, f"第 6 次登录 → 429（{r.status_code}）")
check(r.headers.get("retry-after", "").isdigit(), "429 带 Retry-After 头")

# ============ (f) 注册限速 4/60：已用 1，再 3 次到顶，第 5 次 429 ============
for i in range(1, 4):
    r = _register(i)
    check(r.status_code == 201, f"注册 #{i+1} → 201（{r.status_code}）")
r = _register(9)
check(r.status_code == 429, f"第 5 次注册 → 429（{r.status_code}）")

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("ALL PASS")
