"""备份（ROADMAP 阶段 B #6）。纯 stdlib，便于无依赖单测。

每轮产出一个 zip：notegen_backup_YYYYMMDD_HHMMSS.zip，内容：
  - notegen.db        SQLite 在线 backup（sqlite3.backup API，WAL 下也一致）
  - user_notes/...    data/user_notes 私有笔记对象目录
  - web_notes/...     web/public/notes 公开笔记产物
默认排除视频（*.mp4 等，体积大且可由 pipeline 重建/重下载），
NOTEGEN_BACKUP_INCLUDE_VIDEOS=1 或 --include-videos 可带上。

滚动保留最近 N 份（默认 7），老的自动删。
目的地默认 backups/（建议用 NOTEGEN_BACKUP_DIR 指到第二块盘/网盘同步目录）。

入口：server.py 每日一轮（NOTEGEN_AUTO_BACKUP=0 关）；scripts/run_backup.py 手动。
恢复：解压 zip，notegen.db 放回 data/，user_notes/ → data/user_notes/，
web_notes/ → web/public/notes/。
"""
from __future__ import annotations

import os
import sqlite3
import time
import zipfile
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent

BACKUP_DIR = Path(os.environ.get("NOTEGEN_BACKUP_DIR", str(ROOT / "backups")))
BACKUP_KEEP = int(os.environ.get("NOTEGEN_BACKUP_KEEP", "7"))
INCLUDE_VIDEOS = os.environ.get("NOTEGEN_BACKUP_INCLUDE_VIDEOS", "0") == "1"

_VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".m4v", ".ts"}
_PREFIX = "notegen_backup_"

# (源目录, zip 内前缀)；目录不存在则跳过
_DEFAULT_SOURCES = [
    (ROOT / "data" / "user_notes", "user_notes"),
    (ROOT / "web" / "public" / "notes", "web_notes"),
]


def _backup_sqlite(db_file: Path, out_file: Path) -> bool:
    """sqlite3 在线 backup：server 开着也能拿到一致快照。库不存在返回 False。"""
    if not db_file.is_file():
        return False
    src = sqlite3.connect(str(db_file))
    try:
        dst = sqlite3.connect(str(out_file))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return True


def create_backup(dest_dir: Optional[Path] = None, *,
                  include_videos: Optional[bool] = None,
                  sources: Optional[list] = None,
                  db_file: Optional[Path] = None,
                  now: Optional[float] = None) -> dict:
    """打一个备份 zip。返回 {path, size_mb, files, skipped_videos, db_included}。"""
    dest = Path(dest_dir) if dest_dir is not None else BACKUP_DIR
    dest.mkdir(parents=True, exist_ok=True)
    inc_video = INCLUDE_VIDEOS if include_videos is None else include_videos
    srcs = sources if sources is not None else _DEFAULT_SOURCES
    if db_file is None:
        import db
        db_file = db.db_path()

    stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(now))
    zip_path = dest / f"{_PREFIX}{stamp}.zip"
    n_files = 0
    skipped_videos = 0

    db_snap = dest / f".db_snapshot_{stamp}.tmp"
    db_included = _backup_sqlite(Path(db_file), db_snap)
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if db_included:
                zf.write(db_snap, "notegen.db")
                n_files += 1
            for src_dir, prefix in srcs:
                src_dir = Path(src_dir)
                if not src_dir.is_dir():
                    continue
                for f in sorted(src_dir.rglob("*")):
                    if not f.is_file():
                        continue
                    if not inc_video and f.suffix.lower() in _VIDEO_EXTS:
                        skipped_videos += 1
                        continue
                    zf.write(f, f"{prefix}/{f.relative_to(src_dir).as_posix()}")
                    n_files += 1
    finally:
        db_snap.unlink(missing_ok=True)

    return {
        "path": str(zip_path),
        "size_mb": round(zip_path.stat().st_size / 1e6, 2),
        "files": n_files,
        "skipped_videos": skipped_videos,
        "db_included": db_included,
    }


def prune_backups(dest_dir: Optional[Path] = None,
                  keep: Optional[int] = None) -> list[str]:
    """按文件名（含时间戳，字典序=时间序）保留最新 keep 份，删掉更老的。"""
    dest = Path(dest_dir) if dest_dir is not None else BACKUP_DIR
    k = BACKUP_KEEP if keep is None else keep
    if not dest.is_dir() or k < 1:
        return []
    zips = sorted(dest.glob(f"{_PREFIX}*.zip"), key=lambda p: p.name, reverse=True)
    removed = []
    for p in zips[k:]:
        try:
            p.unlink()
            removed.append(str(p))
        except OSError:
            pass
    return removed


def run_backup(**kwargs) -> dict:
    """打包 + 滚动清理，一步到位（server 每日任务 / CLI 共用）。"""
    summary = create_backup(**{k: v for k, v in kwargs.items()
                               if k in ("dest_dir", "include_videos", "sources",
                                        "db_file", "now")})
    summary["pruned"] = prune_backups(
        kwargs.get("dest_dir"), kwargs.get("keep"))
    return summary
