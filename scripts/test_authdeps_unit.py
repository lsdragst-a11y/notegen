"""authdeps：current_user / require_user / require_admin。用真临时库 + 假 Request
（只需 .cookies）。require_* 抛 HTTPException(401/403)。
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_authdeps_unit.py"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import db  # noqa: E402
db.set_db_path(os.path.join(tempfile.mkdtemp(), "t.db"))
db.init_db()
import accounts as A  # noqa: E402
import authdeps as AD  # noqa: E402
from fastapi import HTTPException  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

class FakeReq:
    def __init__(self, cookies):
        self.cookies = cookies

uid = A.create_user("a@x.com", "pw12345", "A", email_verified=True)
aid = A.create_user("admin@x.com", "pw12345", "Adm", role="admin", email_verified=True)
stok = A.create_session(uid)
atok = A.create_session(aid)

check(AD.current_user(FakeReq({})) is None, "无 cookie -> current_user None")
check(AD.current_user(FakeReq({AD.SESSION_COOKIE: "bad"})) is None, "坏 token None")
cu = AD.current_user(FakeReq({AD.SESSION_COOKIE: stok}))
check(cu is not None and cu["id"] == uid, "有效会话 -> current_user 命中")

# require_user：以 current_user 的返回值作为依赖入参
check(AD.require_user(cu)["id"] == uid, "require_user 放行登录用户")
got = None
try:
    AD.require_user(None)
except HTTPException as e:
    got = e.status_code
check(got == 401, "require_user 匿名 -> 401")

# require_admin
au = AD.current_user(FakeReq({AD.SESSION_COOKIE: atok}))
check(AD.require_admin(au)["id"] == aid, "require_admin 放行 admin")
got = None
try:
    AD.require_admin(cu)  # 普通用户
except HTTPException as e:
    got = e.status_code
check(got == 403, "require_admin 普通用户 -> 403")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ==="); sys.exit(1)
print("=== ALL CHECKS PASSED ===")
