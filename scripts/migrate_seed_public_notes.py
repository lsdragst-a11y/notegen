"""幂等迁移：建 seed admin（dev 凭据，可用 env 覆盖）+ 把 web/public/notes/ 既有目录
登记为公开笔记(visibility='public', owner_id=admin)。可重跑（按 note id upsert）。
Run: .venv/Scripts/python.exe scripts/migrate_seed_public_notes.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import db  # noqa: E402
import accounts  # noqa: E402
import service_common as SC  # noqa: E402
from userdata import notes_repo  # noqa: E402

ADMIN_EMAIL = os.environ.get("NOTEGEN_ADMIN_EMAIL", "admin@notegen.local")
ADMIN_PASSWORD = os.environ.get("NOTEGEN_ADMIN_PASSWORD", "admin12345")


def ensure_admin() -> str:
    existing = accounts.get_user_by_email(ADMIN_EMAIL)
    if existing:
        return existing["id"]
    return accounts.create_user(ADMIN_EMAIL, ADMIN_PASSWORD, "NoteGen Admin",
                                role="admin", email_verified=True)


def run() -> None:
    db.init_db()
    admin_id = ensure_admin()
    if not SC.NOTES_DIR.exists():
        print(f"[migrate] {SC.NOTES_DIR} 不存在，仅建 admin")
        return
    n = 0
    for d in sorted(SC.NOTES_DIR.iterdir()):
        if not d.is_dir():
            continue
        if not (d / "summary.json").exists() or not (d / "chapters.json").exists():
            continue
        fields = SC.extract_note_fields(d)
        notes_repo.upsert(id=d.name, owner_id=admin_id, visibility="public",
                          storage_path=str(d), **fields)
        n += 1
    print(f"[migrate] admin={ADMIN_EMAIL} 公开笔记登记 {n} 条")


if __name__ == "__main__":
    run()
