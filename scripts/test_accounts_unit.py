"""accounts.py 单元：密码 hash/verify、用户 CRUD/归一、登录校验。
（邮箱验证 token 与会话在 Task 3 追加到本文件。）临时库，不碰 GPU/真库。
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_accounts_unit.py"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import db  # noqa: E402
db.set_db_path(os.path.join(tempfile.mkdtemp(), "t.db"))
db.init_db()
import accounts as A  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

# --- 密码 ---
h = A.hash_password("s3cret!")
check(h != "s3cret!" and h.startswith("$2"), "bcrypt hash 非明文")
check(A.verify_password("s3cret!", h) is True, "正确密码验证通过")
check(A.verify_password("wrong", h) is False, "错误密码验证失败")
check(A.verify_password("x", "not-a-hash") is False, "坏 hash 不抛、返 False")

# --- 邮箱归一 ---
check(A.normalize_email("  Foo@Bar.COM ") == "foo@bar.com", "邮箱小写去空白")

# --- 用户 CRUD ---
uid = A.create_user("Alice@X.com", "pw12345", "Alice")
u = A.get_user_by_id(uid)
check(u is not None and u["email"] == "alice@x.com", "create+get_by_id 邮箱已归一")
check("password_hash" not in u, "返回的 user dict 不含 password_hash")
check(u["role"] == "user" and u["email_verified"] == 0, "默认 role=user/未验证")
check(A.get_user_by_email("ALICE@x.com")["id"] == uid, "get_by_email 大小写无关")
dup = None
try:
    A.create_user("alice@x.com", "other", "Dup")
except ValueError as e:
    dup = str(e)
check(dup is not None, "重复邮箱抛 ValueError")

# --- 登录校验：未验证邮箱仍能被 verify_login 校验密码（验证状态由调用层判定）---
check(A.verify_login("alice@x.com", "pw12345")["id"] == uid, "对密码登录命中")
check(A.verify_login("alice@x.com", "bad") is None, "错密码登录 None")
check(A.verify_login("nobody@x.com", "whatever") is None, "不存在用户登录 None")

# --- 邮箱验证 token ---
import time as _t
tok = A.create_verification_token(uid, ttl=60)
check(A.consume_verification_token(tok) == uid, "有效 token 消费返回 uid")
check(A.get_user_by_id(uid)["email_verified"] == 1, "消费后 email_verified=1")
check(A.consume_verification_token(tok) is None, "token 一次性（再消费 None）")
expired = A.create_verification_token(uid, ttl=-1)
check(A.consume_verification_token(expired) is None, "过期 token 不消费")
check(A.consume_verification_token("bogus") is None, "未知 token None")

# --- 会话 ---
stok = A.create_session(uid, ttl=3600)
su = A.get_session_user(stok)
check(su is not None and su["id"] == uid, "会话查回用户")
check("password_hash" not in su, "会话用户 dict 不含 hash")
check(A.get_session_user("nope") is None, "未知会话 None")
dead = A.create_session(uid, ttl=-1)
check(A.get_session_user(dead) is None, "过期会话 None")
A.delete_session(stok)
check(A.get_session_user(stok) is None, "登出后会话失效")
# 滑动续期：旧到期时间被刷新
stok2 = A.create_session(uid, ttl=2)
import sqlite3 as _s
_c = db.connect()
old_exp = _c.execute("SELECT expires_at FROM sessions WHERE token=?", (stok2,)).fetchone()[0]
_c.close()
_t.sleep(0.05)
A.get_session_user(stok2)
_c = db.connect()
new_exp = _c.execute("SELECT expires_at FROM sessions WHERE token=?", (stok2,)).fetchone()[0]
_c.close()
check(new_exp > old_exp, "访问会话滑动续期 expires_at")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ==="); sys.exit(1)
print("=== ALL CHECKS PASSED ===")
