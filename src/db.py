"""SQLite 连接 + schema（子项目 #2 关系数据：users/sessions/笔记归属/job 历史）。
唯一持有 DB 路径与连接策略：WAL + busy_timeout + Row 工厂 + 短连接（每操作开关）。
测试用 set_db_path() 指向临时库，绝不碰真实 data/notegen.db。"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_DEFAULT = ROOT / "data" / "notegen.db"
_OVERRIDE: Path | None = None


def set_db_path(p) -> None:
    """测试钩子：把库切到临时文件。"""
    global _OVERRIDE
    _OVERRIDE = Path(p)


def db_path() -> Path:
    if _OVERRIDE is not None:
        return _OVERRIDE
    return Path(os.environ.get("NOTEGEN_DB_PATH", str(_DEFAULT)))


def connect() -> sqlite3.Connection:
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  display_name TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'user',
  email_verified INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS email_verifications (
  token TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  created_at REAL NOT NULL,
  expires_at REAL NOT NULL,
  last_seen REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL,
  visibility TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  title TEXT, domain TEXT, duration_sec INTEGER,
  chunks INTEGER, chapters INTEGER, uploader TEXT, webpage_url TEXT,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  source TEXT NOT NULL, is_local INTEGER NOT NULL, quality TEXT NOT NULL,
  status TEXT NOT NULL,
  note_id TEXT, error TEXT,
  created_at REAL NOT NULL, updated_at REAL NOT NULL, finished_at REAL
);
CREATE INDEX IF NOT EXISTS idx_notes_owner ON notes(owner_id, visibility);
CREATE INDEX IF NOT EXISTS idx_notes_vis ON notes(visibility, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id, created_at);
"""


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
