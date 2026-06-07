"""笔记归属(notes) 与提交历史(jobs) 的 SQLite 仓储。短连接，经 db.connect()。
notes 的展示字段是列表冗余（发布时写入），避免列表页逐目录读文件。
jobs 只在 enqueue(record) 与终态(update_status) 镜像，实时进度仍在 Redis。"""
from __future__ import annotations

import time
from typing import Optional

import db

_TERMINAL = ("done", "failed", "interrupted")

_NOTE_COLS = ("id", "owner_id", "visibility", "storage_path", "title", "domain",
              "duration_sec", "chunks", "chapters", "uploader", "webpage_url",
              "created_at")
_JOB_COLS = ("id", "user_id", "source", "is_local", "quality", "status",
             "note_id", "error", "created_at", "updated_at", "finished_at")


def _row(r, cols) -> Optional[dict]:
    return None if r is None else {k: r[k] for k in cols}


class _NotesRepo:
    def upsert(self, *, id, owner_id, visibility, storage_path, title, domain,
               duration_sec, chunks, chapters, uploader, webpage_url) -> None:
        conn = db.connect()
        try:
            exists = conn.execute("SELECT created_at FROM notes WHERE id=?",
                                  (id,)).fetchone()
            created = exists["created_at"] if exists else time.time()
            conn.execute(
                "INSERT INTO notes(id,owner_id,visibility,storage_path,title,domain,"
                "duration_sec,chunks,chapters,uploader,webpage_url,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET owner_id=excluded.owner_id,"
                "visibility=excluded.visibility,storage_path=excluded.storage_path,"
                "title=excluded.title,domain=excluded.domain,"
                "duration_sec=excluded.duration_sec,chunks=excluded.chunks,"
                "chapters=excluded.chapters,uploader=excluded.uploader,"
                "webpage_url=excluded.webpage_url",
                (id, owner_id, visibility, storage_path, title, domain, duration_sec,
                 chunks, chapters, uploader, webpage_url, created),
            )
            conn.commit()
        finally:
            conn.close()

    def get(self, note_id: str) -> Optional[dict]:
        conn = db.connect()
        try:
            return _row(conn.execute("SELECT * FROM notes WHERE id=?",
                                     (note_id,)).fetchone(), _NOTE_COLS)
        finally:
            conn.close()

    def list_public(self) -> list[dict]:
        conn = db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM notes WHERE visibility='public' "
                "ORDER BY created_at DESC").fetchall()
            return [_row(r, _NOTE_COLS) for r in rows]
        finally:
            conn.close()

    def list_mine(self, owner_id: str) -> list[dict]:
        conn = db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM notes WHERE owner_id=? AND visibility='private' "
                "ORDER BY created_at DESC", (owner_id,)).fetchall()
            return [_row(r, _NOTE_COLS) for r in rows]
        finally:
            conn.close()

    def delete(self, note_id: str) -> None:
        conn = db.connect()
        try:
            conn.execute("DELETE FROM notes WHERE id=?", (note_id,))
            conn.commit()
        finally:
            conn.close()


class _JobsRepo:
    def record(self, job_id, user_id, source, *, is_local, quality, status) -> None:
        now = time.time()
        conn = db.connect()
        try:
            conn.execute(
                "INSERT INTO jobs(id,user_id,source,is_local,quality,status,"
                "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET status=excluded.status,"
                "updated_at=excluded.updated_at",
                (job_id, user_id, source, 1 if is_local else 0, quality, status,
                 now, now),
            )
            conn.commit()
        finally:
            conn.close()

    def update_status(self, job_id, status, *, note_id=None, error=None) -> None:
        now = time.time()
        finished = now if status in _TERMINAL else None
        conn = db.connect()
        try:
            conn.execute(
                "UPDATE jobs SET status=?, updated_at=?, "
                "note_id=COALESCE(?, note_id), error=COALESCE(?, error), "
                "finished_at=COALESCE(?, finished_at) WHERE id=?",
                (status, now, note_id, error, finished, job_id),
            )
            conn.commit()
        finally:
            conn.close()

    def reconcile_orphans(self) -> int:
        """worker 启动时调用：并发=1 下启动期必无真正在跑的任务，故把卡在 'running' 的孤儿
        标 'interrupted'（上个 worker 崩溃/被杀残留），释放该用户在飞名额。返回处理条数。"""
        now = time.time()
        conn = db.connect()
        try:
            cur = conn.execute(
                "UPDATE jobs SET status='interrupted', updated_at=?, "
                "finished_at=COALESCE(finished_at, ?) WHERE status='running'",
                (now, now))
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    def get(self, job_id: str) -> Optional[dict]:
        conn = db.connect()
        try:
            return _row(conn.execute("SELECT * FROM jobs WHERE id=?",
                                     (job_id,)).fetchone(), _JOB_COLS)
        finally:
            conn.close()

    def count_active(self, user_id: str) -> int:
        conn = db.connect()
        try:
            r = conn.execute(
                "SELECT COUNT(*) AS c FROM jobs WHERE user_id=? "
                "AND status IN ('queued','running')", (user_id,)).fetchone()
            return int(r["c"])
        finally:
            conn.close()

    def list_history(self, user_id: str) -> list[dict]:
        conn = db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE user_id=? ORDER BY created_at DESC",
                (user_id,)).fetchall()
            return [_row(r, _JOB_COLS) for r in rows]
        finally:
            conn.close()


notes_repo = _NotesRepo()
jobs_repo = _JobsRepo()
