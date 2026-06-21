"""note_shares 仓储断言：幂等 ensure、resolve、revoke。临时库，无需服务。
Run: .venv/Scripts/python.exe scripts/test_shares_unit.py"""
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import db  # noqa: E402

db.set_db_path(os.path.join(tempfile.mkdtemp(), "test_shares.db"))
db.init_db()

import userdata  # noqa: E402
SR = userdata.shares_repo

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

t1 = SR.ensure("note-a")
check(isinstance(t1, str) and len(t1) >= 16, "ensure 生成 token")
check(SR.ensure("note-a") == t1, "ensure 幂等：同笔记同 token")
check(SR.get_token("note-a") == t1, "get_token 命中")
check(SR.get_token("note-x") is None, "get_token 未分享 → None")
check(SR.resolve(t1) == "note-a", "resolve token → note_id")
check(SR.resolve("bogus") is None, "resolve 无效 token → None")

t2 = SR.ensure("note-b")
check(t2 != t1, "不同笔记不同 token")

check(SR.revoke("note-a") is True, "revoke 返回 True")
check(SR.resolve(t1) is None, "revoke 后 token 立即失效")
check(SR.revoke("note-a") is False, "重复 revoke 返回 False")
check(SR.resolve(t2) == "note-b", "revoke 不影响其它笔记")

t3 = SR.ensure("note-a")
check(t3 != t1, "重新分享生成新 token（旧链接不复活）")

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("ALL PASS")
