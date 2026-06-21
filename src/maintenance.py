"""磁盘治理（ROADMAP 阶段 B #4）。纯 stdlib，便于无依赖单测。

三类清理（全部支持 dry_run，先收集后删除）：
  1. clean_old_files     — data/raw 与 data/audio 中超过保留期的文件
                           （raw 可重下载、audio 是 ASR 中间产物，笔记本体早已
                           publish 到 user_notes / web/public，删了不影响浏览）
  2. clean_orphan_uploads — data/raw/local_*.mp4(+meta) 中没有任何「活跃」job
                           引用的本地上传（含 failed/interrupted 残留），留 24h 宽限
  3. data/outputs 刻意不碰 — 那是论文 benchmark 产物

磁盘水位：disk_status() 给 /api/health 暴露 + 低水位时 /api/generate、/api/upload 拒单。

入口：
  - server.py 启动后每天跑一次（asyncio 后台任务）
  - scripts/run_maintenance.py 手动/任务计划程序跑，支持 --dry-run
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = ROOT / "data" / "raw"
DATA_AUDIO = ROOT / "data" / "audio"

# 环境变量旋钮
RETENTION_DAYS = float(os.environ.get("NOTEGEN_RAW_RETENTION_DAYS", "7"))
MIN_FREE_RATIO = float(os.environ.get("NOTEGEN_MIN_FREE_RATIO", "0.15"))
ORPHAN_GRACE_HOURS = float(os.environ.get("NOTEGEN_ORPHAN_GRACE_HOURS", "24"))

# jobs.status 里算「活跃」的状态：引用着的上传不能删
_ACTIVE_STATUSES = ("queued", "running")


def _remove(path: Path, dry_run: bool, removed: list[str]) -> None:
    removed.append(str(path))
    if dry_run:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def clean_old_files(dirs: Optional[list[Path]] = None,
                    days: float = RETENTION_DAYS,
                    *, now: Optional[float] = None,
                    dry_run: bool = False) -> list[str]:
    """删除 dirs 下 mtime 超过 days 天的普通文件（不递归子目录、不删目录）。"""
    cutoff = (now if now is not None else time.time()) - days * 86400
    removed: list[str] = []
    for d in (dirs if dirs is not None else [DATA_RAW, DATA_AUDIO]):
        if not d.is_dir():
            continue
        for f in d.iterdir():
            try:
                if f.is_file() and f.stat().st_mtime < cutoff:
                    _remove(f, dry_run, removed)
            except OSError:
                continue
    return removed


def _active_upload_sources() -> set[str]:
    """活跃 job 引用的本地上传路径集合（resolve 后字符串）。DB 不可用时返回
    None 语义由调用方处理——这里抛出让 clean_orphan_uploads 整体跳过，宁可不删。"""
    import db
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT source FROM jobs WHERE is_local=1 AND status IN (?,?)",
            _ACTIVE_STATUSES,
        ).fetchall()
    finally:
        conn.close()
    out = set()
    for r in rows:
        try:
            out.add(str(Path(r["source"]).resolve()))
        except OSError:
            continue
    return out


def clean_orphan_uploads(raw_dir: Optional[Path] = None,
                         grace_hours: float = ORPHAN_GRACE_HOURS,
                         *, now: Optional[float] = None,
                         dry_run: bool = False) -> list[str]:
    """删除没有活跃 job 引用、且超过宽限期的 local_*.mp4 及其 .meta.json。
    覆盖 failed/interrupted job 的上传残留；done job 的上传也可删（产物已 publish）。
    DB 读取失败时整体跳过（宁可漏删不可误删）。"""
    d = raw_dir if raw_dir is not None else DATA_RAW
    if not d.is_dir():
        return []
    try:
        active = _active_upload_sources()
    except Exception:
        return []
    cutoff = (now if now is not None else time.time()) - grace_hours * 3600
    removed: list[str] = []
    for f in d.glob("local_*.mp4"):
        try:
            if f.stat().st_mtime >= cutoff:
                continue
        except OSError:
            continue
        if str(f.resolve()) in active:
            continue
        _remove(f, dry_run, removed)
        meta = f.with_name(f.stem + ".meta.json")
        if meta.is_file():
            _remove(meta, dry_run, removed)
    return removed


def disk_status(path: Optional[Path] = None,
                min_free_ratio: float = MIN_FREE_RATIO,
                usage_fn: Callable = shutil.disk_usage) -> dict:
    """磁盘水位。low=True 时新任务应被拒绝；/api/health 原样暴露。"""
    p = path if path is not None else ROOT
    u = usage_fn(str(p))
    ratio = (u.free / u.total) if u.total else 0.0
    return {
        "total_gb": round(u.total / 1e9, 1),
        "free_gb": round(u.free / 1e9, 1),
        "free_ratio": round(ratio, 4),
        "low": ratio < min_free_ratio,
    }


def run_once(*, dry_run: bool = False) -> dict:
    """跑一轮全部清理，返回摘要（供日志/CLI 打印）。"""
    old = clean_old_files(dry_run=dry_run)
    orphans = clean_orphan_uploads(dry_run=dry_run)
    return {
        "old_files_removed": old,
        "orphan_uploads_removed": orphans,
        "disk": disk_status(),
        "dry_run": dry_run,
    }
