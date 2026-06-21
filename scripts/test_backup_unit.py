"""backup.py 断言：SQLite 在线快照可恢复、目录打包（视频默认排除/可带上）、
滚动保留、run_backup 摘要。纯 stdlib + 临时目录。
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_backup_unit.py"""
import os
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import backup as B  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)


# ============ 造源数据：临时库 + 两个源目录 ============
tmp = Path(tempfile.mkdtemp())
db_file = tmp / "src.db"
conn = sqlite3.connect(str(db_file))
conn.execute("CREATE TABLE t(x TEXT)")
conn.execute("INSERT INTO t VALUES ('hello-backup')")
conn.commit(); conn.close()

notes_dir = tmp / "user_notes"
(notes_dir / "note1").mkdir(parents=True)
(notes_dir / "note1" / "chapters.json").write_text('{"a":1}', encoding="utf-8")
(notes_dir / "note1" / "video.mp4").write_bytes(b"\x00" * 1024)
(notes_dir / "note1" / "kf.jpg").write_bytes(b"\xff" * 64)
web_notes = tmp / "web_notes_src"
web_notes.mkdir()
(web_notes / "summary.json").write_text("[]", encoding="utf-8")

SOURCES = [(notes_dir, "user_notes"), (web_notes, "web_notes"),
           (tmp / "nonexistent", "ghost")]
dest = tmp / "backups"

# ============ (a) create_backup：默认排除视频 ============
s = B.create_backup(dest, include_videos=False, sources=SOURCES,
                    db_file=db_file)
check(s["db_included"] is True, "SQLite 进包")
check(s["skipped_videos"] == 1, f"视频默认排除（skipped={s['skipped_videos']}）")
zp = Path(s["path"])
check(zp.is_file() and s["size_mb"] >= 0, "zip 落盘")
names = set(zipfile.ZipFile(zp).namelist())
check("notegen.db" in names, "包含 notegen.db")
check("user_notes/note1/chapters.json" in names, "user_notes 保持相对路径")
check("user_notes/note1/kf.jpg" in names, "关键帧进包")
check("web_notes/summary.json" in names, "web notes 进包")
check("user_notes/note1/video.mp4" not in names, "mp4 不在包里")
check(not any(n.startswith("ghost") for n in names), "不存在的源目录跳过")
check(not list(dest.glob(".db_snapshot_*")), "临时 db 快照已清理")

# ============ (b) db 快照可恢复 ============
with zipfile.ZipFile(zp) as zf:
    zf.extract("notegen.db", tmp / "restore")
rconn = sqlite3.connect(str(tmp / "restore" / "notegen.db"))
row = rconn.execute("SELECT x FROM t").fetchone()
rconn.close()
check(row and row[0] == "hello-backup", "解包后 SQLite 可查询（在线 backup 一致）")

# ============ (c) include_videos=True ============
s2 = B.create_backup(dest, include_videos=True, sources=SOURCES,
                     db_file=db_file, now=B.time.time() + 1)
names2 = set(zipfile.ZipFile(s2["path"]).namelist())
check("user_notes/note1/video.mp4" in names2, "--include-videos 时视频进包")
check(s2["skipped_videos"] == 0, "include 时 skipped=0")

# ============ (d) db 不存在 → 跳过但仍出包 ============
s3 = B.create_backup(dest, include_videos=False, sources=SOURCES,
                     db_file=tmp / "missing.db", now=B.time.time() + 2)
check(s3["db_included"] is False, "库不存在 → db_included False")
check("notegen.db" not in set(zipfile.ZipFile(s3["path"]).namelist()),
      "包里没有 notegen.db 但其余照常")

# ============ (e) prune：留最新 keep 份 ============
for i in range(5):
    (dest / f"notegen_backup_2020010{i}_000000.zip").write_bytes(b"PK\x05\x06" + b"\x00" * 18)
all_zips = sorted(p.name for p in dest.glob("notegen_backup_*.zip"))
removed = B.prune_backups(dest, keep=4)
left = sorted(p.name for p in dest.glob("notegen_backup_*.zip"))
check(len(left) == 4, f"prune 后剩 4 份（{len(left)}）")
check(left == sorted(all_zips)[-4:], "留的是最新 4 份（字典序=时间序）")
check(all(Path(r).name.startswith("notegen_backup_2020") for r in removed),
      "删的全是旧假包")

# ============ (f) run_backup 摘要 ============
s4 = B.run_backup(dest_dir=dest, include_videos=False, sources=SOURCES,
                  db_file=db_file, keep=3, now=B.time.time() + 3)
check({"path", "size_mb", "files", "skipped_videos", "db_included", "pruned"}
      <= set(s4.keys()), "run_backup 摘要字段齐全")
check(len(list(dest.glob("notegen_backup_*.zip"))) == 3, "run_backup 顺带滚动清理")

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("ALL PASS")
