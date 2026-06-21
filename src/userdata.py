"""笔记归属(notes) 与提交历史(jobs) 的 SQLite 仓储。短连接，经 db.connect()。
notes 的展示字段是列表冗余（发布时写入），避免列表页逐目录读文件。
jobs 只在 enqueue(record) 与终态(update_status) 镜像，实时进度仍在 Redis。"""
from __future__ import annotations

import json
import time
from typing import Optional

import db

_TERMINAL = ("done", "failed", "interrupted")

_NOTE_COLS = ("id", "owner_id", "visibility", "storage_path", "title", "domain",
              "duration_sec", "chunks", "chapters", "uploader", "webpage_url",
              "created_at")
_JOB_COLS = ("id", "user_id", "source", "is_local", "quality", "status",
             "note_id", "error", "created_at", "updated_at", "finished_at")
_BOOKMARK_COLS = ("key", "note_id", "note_title", "kind", "idx", "title",
                  "title_en", "time_sec", "keyframe_rel", "category_ids_json",
                  "added_at")
_BOOKMARK_CATEGORY_COLS = ("id", "name", "color", "created_at")


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


def _bookmark_row(r) -> dict:
    cats_raw = r["category_ids_json"] if "category_ids_json" in r.keys() else "[]"
    try:
        category_ids = json.loads(cats_raw or "[]")
    except (TypeError, ValueError):
        category_ids = []
    if not isinstance(category_ids, list):
        category_ids = []
    return {
        "key": r["key"],
        "noteId": r["note_id"],
        "noteTitle": r["note_title"],
        "kind": r["kind"],
        "idx": r["idx"],
        "title": r["title"],
        "title_en": r["title_en"],
        "time": r["time_sec"],
        "keyframeRel": r["keyframe_rel"],
        "categoryIds": [str(x) for x in category_ids],
        "addedAt": r["added_at"],
    }


def _category_row(r) -> dict:
    return {
        "id": r["id"],
        "name": r["name"],
        "color": r["color"],
        "createdAt": r["created_at"],
    }


class _BookmarksRepo:
    def state(self, user_id: str) -> dict:
        conn = db.connect()
        try:
            cats = conn.execute(
                "SELECT * FROM bookmark_categories WHERE user_id=? "
                "ORDER BY created_at ASC", (user_id,),
            ).fetchall()
            bookmarks = conn.execute(
                "SELECT * FROM bookmarks WHERE user_id=? ORDER BY added_at DESC",
                (user_id,),
            ).fetchall()
            return {
                "categories": [_category_row(r) for r in cats],
                "bookmarks": [_bookmark_row(r) for r in bookmarks],
            }
        finally:
            conn.close()

    def upsert_category(self, user_id: str, *, id: str, name: str,
                        color: str, created_at: Optional[float] = None) -> None:
        conn = db.connect()
        try:
            created = created_at if created_at is not None else time.time()
            exists = conn.execute(
                "SELECT created_at FROM bookmark_categories WHERE user_id=? AND id=?",
                (user_id, id),
            ).fetchone()
            if exists:
                created = exists["created_at"]
            conn.execute(
                "INSERT INTO bookmark_categories(id,user_id,name,color,created_at) "
                "VALUES(?,?,?,?,?) "
                "ON CONFLICT(user_id,id) DO UPDATE SET "
                "name=excluded.name,color=excluded.color",
                (id, user_id, name, color, created),
            )
            conn.commit()
        finally:
            conn.close()

    def rename_category(self, user_id: str, id: str, name: str) -> bool:
        conn = db.connect()
        try:
            cur = conn.execute(
                "UPDATE bookmark_categories SET name=? WHERE user_id=? AND id=?",
                (name, user_id, id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def delete_category(self, user_id: str, id: str) -> bool:
        conn = db.connect()
        try:
            cur = conn.execute(
                "DELETE FROM bookmark_categories WHERE user_id=? AND id=?",
                (user_id, id),
            )
            rows = conn.execute(
                "SELECT key, category_ids_json FROM bookmarks WHERE user_id=?",
                (user_id,),
            ).fetchall()
            for row in rows:
                try:
                    ids = json.loads(row["category_ids_json"] or "[]")
                except (TypeError, ValueError):
                    ids = []
                if id not in ids:
                    continue
                next_ids = [x for x in ids if x != id]
                conn.execute(
                    "UPDATE bookmarks SET category_ids_json=? "
                    "WHERE user_id=? AND key=?",
                    (json.dumps(next_ids, ensure_ascii=False), user_id, row["key"]),
                )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def upsert_bookmark(self, user_id: str, b: dict) -> None:
        conn = db.connect()
        try:
            exists = conn.execute(
                "SELECT added_at FROM bookmarks WHERE user_id=? AND key=?",
                (user_id, b["key"]),
            ).fetchone()
            added = float(b.get("addedAt") or time.time())
            if exists:
                added = exists["added_at"]
            category_ids = b.get("categoryIds") or []
            if not isinstance(category_ids, list):
                category_ids = []
            conn.execute(
                "INSERT INTO bookmarks(user_id,key,note_id,note_title,kind,idx,title,"
                "title_en,time_sec,keyframe_rel,category_ids_json,added_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(user_id,key) DO UPDATE SET "
                "note_id=excluded.note_id,note_title=excluded.note_title,"
                "kind=excluded.kind,idx=excluded.idx,title=excluded.title,"
                "title_en=excluded.title_en,time_sec=excluded.time_sec,"
                "keyframe_rel=excluded.keyframe_rel,"
                "category_ids_json=excluded.category_ids_json",
                (user_id, b["key"], b["noteId"], b["noteTitle"], b["kind"],
                 int(b["idx"]), b["title"], b.get("title_en"), float(b["time"]),
                 b.get("keyframeRel"),
                 json.dumps([str(x) for x in category_ids], ensure_ascii=False),
                 added),
            )
            conn.commit()
        finally:
            conn.close()

    def delete_bookmark(self, user_id: str, key: str) -> bool:
        conn = db.connect()
        try:
            cur = conn.execute(
                "DELETE FROM bookmarks WHERE user_id=? AND key=?",
                (user_id, key),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


class _SharesRepo:
    """笔记分享 token：一笔记一 token（UNIQUE note_id），revoke 即删行。"""

    def ensure(self, note_id: str) -> str:
        """返回该笔记的分享 token，没有则创建（幂等）。"""
        import secrets
        conn = db.connect()
        try:
            row = conn.execute("SELECT token FROM note_shares WHERE note_id=?",
                               (note_id,)).fetchone()
            if row is not None:
                return row["token"]
            token = secrets.token_urlsafe(16)
            conn.execute(
                "INSERT INTO note_shares(token, note_id, created_at) VALUES(?,?,?)",
                (token, note_id, time.time()))
            conn.commit()
            return token
        finally:
            conn.close()

    def get_token(self, note_id: str) -> Optional[str]:
        conn = db.connect()
        try:
            row = conn.execute("SELECT token FROM note_shares WHERE note_id=?",
                               (note_id,)).fetchone()
            return row["token"] if row else None
        finally:
            conn.close()

    def resolve(self, token: str) -> Optional[str]:
        """token → note_id；无效 token → None。"""
        conn = db.connect()
        try:
            row = conn.execute("SELECT note_id FROM note_shares WHERE token=?",
                               (token,)).fetchone()
            return row["note_id"] if row else None
        finally:
            conn.close()

    def revoke(self, note_id: str) -> bool:
        conn = db.connect()
        try:
            cur = conn.execute("DELETE FROM note_shares WHERE note_id=?", (note_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


notes_repo = _NotesRepo()
jobs_repo = _JobsRepo()
bookmarks_repo = _BookmarksRepo()
shares_repo = _SharesRepo()
