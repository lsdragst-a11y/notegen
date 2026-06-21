"""maintenance.py 断言：过期文件清理（dry_run/真删）、孤儿上传清理
（活跃 job 引用保护 / 宽限期 / DB 异常跳过）、磁盘水位。纯 stdlib + 临时库。
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_maintenance_unit.py"""
import os
import sys
import tempfile
import time
from collections import namedtuple
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import db  # noqa: E402
db.set_db_path(os.path.join(tempfile.mkdtemp(), "t.db"))
db.init_db()
from userdata import jobs_repo  # noqa: E402
import maintenance as M  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)


NOW = time.time()

def _make(d: Path, name: str, age_days: float) -> Path:
    p = d / name
    p.write_bytes(b"x")
    ts = NOW - age_days * 86400
    os.utime(p, (ts, ts))
    return p


# ============ (a) clean_old_files ============
d1 = Path(tempfile.mkdtemp())
old_f = _make(d1, "old.mp4", 8)
new_f = _make(d1, "new.mp4", 1)
sub = d1 / "subdir"; sub.mkdir()

removed = M.clean_old_files([d1], days=7, now=NOW, dry_run=True)
check(str(old_f) in removed and len(removed) == 1, "dry_run 只列出过期文件")
check(old_f.exists(), "dry_run 不真删")

removed = M.clean_old_files([d1], days=7, now=NOW)
check(not old_f.exists(), "过期文件被删")
check(new_f.exists(), "保留期内文件不动")
check(sub.exists(), "子目录不动")
check(M.clean_old_files([d1 / "nope"], days=7, now=NOW) == [], "目录不存在 → 空列表")


# ============ (b) clean_orphan_uploads ============
raw = Path(tempfile.mkdtemp())
active_up = _make(raw, "local_active1234.mp4", 3)
orphan_up = _make(raw, "local_orphan5678.mp4", 3)
orphan_meta = raw / "local_orphan5678.meta.json"
orphan_meta.write_text("{}", encoding="utf-8")
ts = NOW - 3 * 86400; os.utime(orphan_meta, (ts, ts))
fresh_up = _make(raw, "local_fresh9999.mp4", 0.5)   # 12h < 24h 宽限
url_raw = _make(raw, "BV1xxx.mp4", 3)               # 非 local_ 前缀不归这条管

jobs_repo.record("job-a", "u1", str(active_up), is_local=True,
                 quality="best", status="running")
jobs_repo.record("job-f", "u1", str(orphan_up), is_local=True,
                 quality="best", status="failed")

removed = M.clean_orphan_uploads(raw, grace_hours=24, now=NOW)
check(str(orphan_up) in removed, "failed job 的上传被清")
check(str(orphan_meta) in removed, "伴随 meta.json 一起清")
check(active_up.exists(), "running job 引用的上传受保护")
check(fresh_up.exists(), "宽限期内的上传不动")
check(url_raw.exists(), "非 local_ 文件不归孤儿清理管（由 clean_old_files 管）")

# DB 不可用 → 整体跳过（宁可漏删）
real_connect = db.connect
db.connect = lambda: (_ for _ in ()).throw(RuntimeError("db down"))
check(M.clean_orphan_uploads(raw, grace_hours=0, now=NOW + 9e6) == [],
      "DB 异常 → 跳过不删")
db.connect = real_connect


# ============ (c) disk_status ============
U = namedtuple("usage", "total used free")
st = M.disk_status(usage_fn=lambda p: U(100e9, 90e9, 10e9))
check(st["low"] is True and abs(st["free_ratio"] - 0.1) < 1e-6,
      f"free 10% < 15% → low（{st}）")
st = M.disk_status(usage_fn=lambda p: U(100e9, 50e9, 50e9))
check(st["low"] is False and st["free_gb"] == 50.0, "free 50% → 不 low")
st = M.disk_status(min_free_ratio=0.6, usage_fn=lambda p: U(100e9, 50e9, 50e9))
check(st["low"] is True, "自定义水位线生效")


# ============ (d) run_once（重定向模块目录后冒烟） ============
M.DATA_RAW = raw
M.DATA_AUDIO = Path(tempfile.mkdtemp())
s = M.run_once(dry_run=True)
check(set(s.keys()) == {"old_files_removed", "orphan_uploads_removed", "disk", "dry_run"},
      "run_once 摘要字段齐全")
check(s["dry_run"] is True and isinstance(s["disk"]["low"], bool), "run_once dry_run 冒烟")

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("ALL PASS")
