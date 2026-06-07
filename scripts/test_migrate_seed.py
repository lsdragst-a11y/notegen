"""migrate_seed_public_notes：建 admin + 登记公开笔记，幂等可重跑。临时库 + 临时 notes 目录。
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_migrate_seed.py"""
import sys, os, json, tempfile
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
db_dir = tempfile.mkdtemp()
os.environ["NOTEGEN_DB_PATH"] = os.path.join(db_dir, "t.db")
import db  # noqa: E402
db.set_db_path(os.environ["NOTEGEN_DB_PATH"]); db.init_db()
import service_common as SC  # noqa: E402
import accounts as A  # noqa: E402
from userdata import notes_repo  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

# 造两个公开 note 目录
SC.NOTES_DIR = Path(tempfile.mkdtemp()) / "notes"
SC.NOTES_DIR.mkdir(parents=True)
for nid, title in [("BVa_p0", "操作系统"), ("BVb_p0", "Python 教程")]:
    d = SC.NOTES_DIR / nid; d.mkdir()
    (d / "summary.json").write_text('[{"start":0,"end":120}]', encoding="utf-8")
    (d / "chapters.json").write_text('{"chapters":[{"title":"c1"}]}', encoding="utf-8")
    (d / "meta.json").write_text(json.dumps({"title": title}), encoding="utf-8")

import migrate_seed_public_notes as M  # noqa: E402
M.run()
M.run()  # 二次幂等

admin = A.get_user_by_email(M.ADMIN_EMAIL)
check(admin is not None and admin["role"] == "admin", "seed admin 已建")
pub = {n["id"]: n for n in notes_repo.list_public()}
check(set(pub) == {"BVa_p0", "BVb_p0"}, f"两公开笔记登记 -> {set(pub)}")
check(pub["BVa_p0"]["domain"] == "考研专业课", "域猜测写入(操作系统)")
check(pub["BVb_p0"]["owner_id"] == admin["id"], "公开笔记归属 seed admin")
check(len(notes_repo.list_public()) == 2, "重跑不产生重复行")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ==="); sys.exit(1)
print("=== ALL CHECKS PASSED ===")
