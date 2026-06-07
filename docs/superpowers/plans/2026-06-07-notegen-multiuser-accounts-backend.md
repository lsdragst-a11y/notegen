# NoteGen 多用户 + 账号 + 历史（后端）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 notegen 在线队列服务（子项目 #1）加上邮箱+密码鉴权、SQLite 持久化的用户/会话/笔记归属/提交历史，以及私有笔记的鉴权托管——纯后端，可无头测试。

**Architecture:** 沿用「FastAPI api + Redis/RQ 队列 + RQ SimpleWorker(并发=1) + subprocess pipeline」骨架，新增一层 SQLite(WAL) 存关系数据。job 实时进度仍只在 Redis（热路径不变）；SQLite `jobs` 只在 enqueue 与终态镜像。新生成笔记默认私有，发布到 `data/user_notes/{uid}/{id}/`，经鉴权端点带 HTTP Range 托管；既有公开笔记继续走静态。服务端会话 cookie（非 JWT），bcrypt 存密码。

**Tech Stack:** Python 3.10 / FastAPI / 标准库 `sqlite3`(3.40.1, WAL) / `bcrypt` / Redis + RQ / `fakeredis` + `fastapi.testclient.TestClient` 做无头测试（沿用 `scripts/test_*.py` assert 脚本风格，不碰 GPU）。

**Spec:** `docs/superpowers/specs/2026-06-07-notegen-multiuser-accounts-design.md`

**前置说明（执行者必读）：**
- 当前分支 `feature/service-hardening`（子项目 #1，未合 main）。**实现分支由用户决定**——建议基于本分支新建 `feature/multiuser-accounts`。开工前与用户确认分支，不要擅自 checkout。
- 测试运行器：`E:/claudeproject/notegen/.venv/Scripts/python.exe`。无 pytest，用 `check(cond, msg)` assert 脚本，末尾 `sys.exit(1)` 表失败。终端中文乱码时加环境变量 `PYTHONIOENCODING=utf-8`。
- 所有 `src/*` 模块靠 `sys.path.insert(0, .../src)` 互相直接 import（`import db` 而非 `from src import db`），沿用现有约定。
- 测试隔离 SQLite：用 `db.set_db_path(<临时文件>)` + `db.init_db()`，**不要**碰真实 `data/notegen.db`。
- 串行 GPU 铁律不变（并发=1 由单 worker 保证）；本计划只加「每用户在飞 1」公平限制。

---

## File Structure

**新建：**
- `src/db.py` — SQLite 连接（WAL/busy_timeout/Row）+ schema 建表（幂等）。唯一持有 DB 路径与连接策略。
- `src/accounts.py` — 密码哈希、用户 CRUD、登录校验、邮箱验证 token、会话。依赖 `db`。
- `src/userdata.py` — `notes_repo` / `jobs_repo`：笔记归属与提交历史的读写。依赖 `db`。
- `src/authdeps.py` — FastAPI 依赖：`current_user` / `require_user` / `require_admin` + cookie 名常量。依赖 `accounts`。
- `scripts/migrate_seed_public_notes.py` — 幂等迁移：建 seed admin + 把 `web/public/notes/` 既有目录登记为公开笔记。
- 测试：`scripts/test_accounts_unit.py`、`scripts/test_userdata_unit.py`、`scripts/test_idempotency_user.py`、`scripts/test_auth_api.py`、`scripts/test_multiuser_integration.py`。

**修改：**
- `requirements.txt` — 加 `bcrypt`。
- `src/service_common.py` — 抽出 publish 共用核心 + 新增 `publish_private` + `extract_note_fields` + `USER_NOTES_DIR`；`_guess_domain` 从 server 迁入。
- `src/jobqueue.py` — `idempotency_key` 纳入 `user_id`。
- `src/worker_tasks.py` — 按 `user_id` 分流私有发布 + 镜像 SQLite `jobs`/`notes` 终态。
- `src/server.py` — 鉴权端点；generate/upload 加 `require_user` + 每用户在飞 1 上限 + 入队镜像；jobs 归属校验；`/api/notes` 拆 public/mine；新增 `/api/history`、`/api/jobs/{id}/retry`、私有文件托管；DELETE 加归属；启动初始化 DB。
- `scripts/run_worker.py` — 启动时 `db.init_db()`（worker 先于 api 起也能写库）。

---

### Task 1: 依赖 + SQLite 基座（`src/db.py`）

**Files:**
- Modify: `requirements.txt`
- Create: `src/db.py`
- Test: `scripts/test_db_schema.py`

- [ ] **Step 1: 加 bcrypt 到 requirements 并安装**

在 `requirements.txt` 末尾（`fakeredis>=2.20` 行之后）追加一行：

```
bcrypt>=4.1,<5.0
```

Run: `E:/claudeproject/notegen/.venv/Scripts/python.exe -m pip install "bcrypt>=4.1,<5.0"`
Expected: `Successfully installed bcrypt-4.x.x`（或 already satisfied）

- [ ] **Step 2: 写失败测试 `scripts/test_db_schema.py`**

```python
"""db.py：临时库建表幂等 + WAL + Row 工厂。无真实 data/notegen.db 写入。
Run: .venv/Scripts/python.exe scripts/test_db_schema.py"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import db  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

tmp = os.path.join(tempfile.mkdtemp(), "t.db")
db.set_db_path(tmp)
db.init_db()
db.init_db()  # 二次调用须幂等不抛

conn = db.connect()
try:
    names = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    for t in ("users", "email_verifications", "sessions", "notes", "jobs"):
        check(t in names, f"表 {t} 已建")
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    check(str(mode).lower() == "wal", f"journal_mode=WAL -> {mode}")
    r = conn.execute("PRAGMA table_info(users)").fetchall()
    check(r[0].keys()[0] == "cid", "Row 工厂可用（按列名取值）")
finally:
    conn.close()

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ==="); sys.exit(1)
print("=== ALL CHECKS PASSED ===")
```

- [ ] **Step 3: 运行测试确认失败**

Run: `E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/test_db_schema.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'db'`

- [ ] **Step 4: 实现 `src/db.py`**

```python
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
```

- [ ] **Step 5: 运行测试确认通过**

Run: `E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/test_db_schema.py`
Expected: PASS（全部）+ `=== ALL CHECKS PASSED ===`

- [ ] **Step 6: 提交**

```bash
git add requirements.txt src/db.py scripts/test_db_schema.py
git commit -m "feat(db): SQLite 基座(WAL/schema)与依赖 bcrypt"
```

---

### Task 2: 密码 + 用户 + 登录（`src/accounts.py` 第一部分）

**Files:**
- Create: `src/accounts.py`
- Test: `scripts/test_accounts_unit.py`

- [ ] **Step 1: 写失败测试 `scripts/test_accounts_unit.py`（仅密码/用户/登录部分，后续 Task 3 追加）**

```python
"""accounts.py 单元：密码 hash/verify、用户 CRUD/归一、登录校验。
（邮箱验证 token 与会话在 Task 3 追加到本文件。）临时库，不碰 GPU/真库。
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_accounts_unit.py"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import db  # noqa: E402
db.set_db_path(os.path.join(tempfile.mkdtemp(), "t.db"))
db.init_db()
import accounts as A  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

# --- 密码 ---
h = A.hash_password("s3cret!")
check(h != "s3cret!" and h.startswith("$2"), "bcrypt hash 非明文")
check(A.verify_password("s3cret!", h) is True, "正确密码验证通过")
check(A.verify_password("wrong", h) is False, "错误密码验证失败")
check(A.verify_password("x", "not-a-hash") is False, "坏 hash 不抛、返 False")

# --- 邮箱归一 ---
check(A.normalize_email("  Foo@Bar.COM ") == "foo@bar.com", "邮箱小写去空白")

# --- 用户 CRUD ---
uid = A.create_user("Alice@X.com", "pw12345", "Alice")
u = A.get_user_by_id(uid)
check(u is not None and u["email"] == "alice@x.com", "create+get_by_id 邮箱已归一")
check("password_hash" not in u, "返回的 user dict 不含 password_hash")
check(u["role"] == "user" and u["email_verified"] == 0, "默认 role=user/未验证")
check(A.get_user_by_email("ALICE@x.com")["id"] == uid, "get_by_email 大小写无关")
dup = None
try:
    A.create_user("alice@x.com", "other", "Dup")
except ValueError as e:
    dup = str(e)
check(dup is not None, "重复邮箱抛 ValueError")

# --- 登录校验：未验证邮箱仍能被 verify_login 校验密码（验证状态由调用层判定）---
check(A.verify_login("alice@x.com", "pw12345")["id"] == uid, "对密码登录命中")
check(A.verify_login("alice@x.com", "bad") is None, "错密码登录 None")
check(A.verify_login("nobody@x.com", "whatever") is None, "不存在用户登录 None")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ==="); sys.exit(1)
print("=== ALL CHECKS PASSED ===")
```

- [ ] **Step 2: 运行确认失败**

Run: `E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/test_accounts_unit.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'accounts'`

- [ ] **Step 3: 实现 `src/accounts.py`（第一部分；Task 3 会在同文件追加 token/session 段）**

```python
"""账号域：密码哈希、用户 CRUD、登录校验、邮箱验证 token、会话。
全部经 db.connect() 短连接读写。返回的 user dict 一律剥掉 password_hash。
错误信息防枚举：登录失败统一 None，由调用层给「邮箱或密码错误」。"""
from __future__ import annotations

import secrets
import time
import uuid
from typing import Optional

import bcrypt

import db

# 不存在用户时也跑一次 checkpw，抹平时序侧信道（尽力，非强保证）。
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password", bcrypt.gensalt()).decode("utf-8")

_PUBLIC_USER_COLS = ("id", "email", "display_name", "role", "email_verified", "created_at")


def _to_user(row) -> Optional[dict]:
    if row is None:
        return None
    return {k: row[k] for k in _PUBLIC_USER_COLS}


# ---------------- 密码 ----------------
def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), (hashed or "").encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------- 用户 ----------------
def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def create_user(email: str, password: str, display_name: str,
                role: str = "user", email_verified: bool = False) -> str:
    em = normalize_email(email)
    uid = uuid.uuid4().hex
    conn = db.connect()
    try:
        exists = conn.execute("SELECT 1 FROM users WHERE email=?", (em,)).fetchone()
        if exists:
            raise ValueError("该邮箱已注册")
        conn.execute(
            "INSERT INTO users(id,email,password_hash,display_name,role,"
            "email_verified,created_at) VALUES(?,?,?,?,?,?,?)",
            (uid, em, hash_password(password), display_name.strip() or em,
             role, 1 if email_verified else 0, time.time()),
        )
        conn.commit()
        return uid
    finally:
        conn.close()


def get_user_by_id(uid: str) -> Optional[dict]:
    conn = db.connect()
    try:
        return _to_user(conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())
    finally:
        conn.close()


def get_user_by_email(email: str) -> Optional[dict]:
    conn = db.connect()
    try:
        row = conn.execute("SELECT * FROM users WHERE email=?",
                           (normalize_email(email),)).fetchone()
        return _to_user(row)
    finally:
        conn.close()


def verify_login(email: str, password: str) -> Optional[dict]:
    """校验邮箱+密码（不查 email_verified——是否放行未验证由调用层定）。
    命中返回 public user dict，否则 None（含不存在/错密码，均跑一次 hash 比较防枚举）。"""
    conn = db.connect()
    try:
        row = conn.execute("SELECT * FROM users WHERE email=?",
                           (normalize_email(email),)).fetchone()
        if row is None:
            verify_password(password, _DUMMY_HASH)  # 抹平时序
            return None
        if not verify_password(password, row["password_hash"]):
            return None
        return _to_user(row)
    finally:
        conn.close()


def set_email_verified(uid: str) -> None:
    conn = db.connect()
    try:
        conn.execute("UPDATE users SET email_verified=1 WHERE id=?", (uid,))
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 4: 运行确认通过**

Run: `PYTHONIOENCODING=utf-8 E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/test_accounts_unit.py`
Expected: PASS（全部）

- [ ] **Step 5: 提交**

```bash
git add src/accounts.py scripts/test_accounts_unit.py
git commit -m "feat(accounts): 密码哈希+用户CRUD+登录校验"
```

---

### Task 3: 邮箱验证 token + 会话（`src/accounts.py` 第二部分）

**Files:**
- Modify: `src/accounts.py`（追加 token/session 段）
- Modify: `scripts/test_accounts_unit.py`（追加断言）

- [ ] **Step 1: 在 `scripts/test_accounts_unit.py` 的 `print()` 之前插入新断言块**

把下面这段插到现有文件里 `print()`（汇总输出那行）**之前**：

```python
# --- 邮箱验证 token ---
import time as _t
tok = A.create_verification_token(uid, ttl=60)
check(A.consume_verification_token(tok) == uid, "有效 token 消费返回 uid")
check(A.get_user_by_id(uid)["email_verified"] == 1, "消费后 email_verified=1")
check(A.consume_verification_token(tok) is None, "token 一次性（再消费 None）")
expired = A.create_verification_token(uid, ttl=-1)
check(A.consume_verification_token(expired) is None, "过期 token 不消费")
check(A.consume_verification_token("bogus") is None, "未知 token None")

# --- 会话 ---
stok = A.create_session(uid, ttl=3600)
su = A.get_session_user(stok)
check(su is not None and su["id"] == uid, "会话查回用户")
check("password_hash" not in su, "会话用户 dict 不含 hash")
check(A.get_session_user("nope") is None, "未知会话 None")
dead = A.create_session(uid, ttl=-1)
check(A.get_session_user(dead) is None, "过期会话 None")
A.delete_session(stok)
check(A.get_session_user(stok) is None, "登出后会话失效")
# 滑动续期：旧到期时间被刷新
stok2 = A.create_session(uid, ttl=2)
import sqlite3 as _s
_c = db.connect()
old_exp = _c.execute("SELECT expires_at FROM sessions WHERE token=?", (stok2,)).fetchone()[0]
_c.close()
_t.sleep(0.05)
A.get_session_user(stok2)
_c = db.connect()
new_exp = _c.execute("SELECT expires_at FROM sessions WHERE token=?", (stok2,)).fetchone()[0]
_c.close()
check(new_exp > old_exp, "访问会话滑动续期 expires_at")
```

- [ ] **Step 2: 运行确认失败**

Run: `PYTHONIOENCODING=utf-8 E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/test_accounts_unit.py`
Expected: FAIL — `AttributeError: module 'accounts' has no attribute 'create_verification_token'`

- [ ] **Step 3: 在 `src/accounts.py` 末尾追加 token + session 段**

```python
# ---------------- 邮箱验证 token ----------------
def create_verification_token(user_id: str, ttl: int = 86400) -> str:
    token = secrets.token_urlsafe(32)
    conn = db.connect()
    try:
        conn.execute(
            "INSERT INTO email_verifications(token,user_id,expires_at) VALUES(?,?,?)",
            (token, user_id, time.time() + ttl),
        )
        conn.commit()
        return token
    finally:
        conn.close()


def consume_verification_token(token: str) -> Optional[str]:
    """有效且未过期 → 置该用户 email_verified=1，删 token，返回 user_id；否则 None。"""
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT user_id, expires_at FROM email_verifications WHERE token=?",
            (token,)).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM email_verifications WHERE token=?", (token,))
        if row["expires_at"] < time.time():
            conn.commit()
            return None
        conn.execute("UPDATE users SET email_verified=1 WHERE id=?", (row["user_id"],))
        conn.commit()
        return row["user_id"]
    finally:
        conn.close()


# ---------------- 会话 ----------------
SESSION_TTL = 7 * 86400  # 7 天滑动


def create_session(user_id: str, ttl: int = SESSION_TTL) -> str:
    token = secrets.token_urlsafe(32)
    now = time.time()
    conn = db.connect()
    try:
        conn.execute(
            "INSERT INTO sessions(token,user_id,created_at,expires_at,last_seen) "
            "VALUES(?,?,?,?,?)",
            (token, user_id, now, now + ttl, now),
        )
        conn.commit()
        return token
    finally:
        conn.close()


def get_session_user(token: str, ttl: int = SESSION_TTL) -> Optional[dict]:
    """查会话→未过期则滑动续期(last_seen/expires_at)并返回 public user dict；否则 None。"""
    if not token:
        return None
    now = time.time()
    conn = db.connect()
    try:
        s = conn.execute("SELECT user_id, expires_at FROM sessions WHERE token=?",
                         (token,)).fetchone()
        if s is None:
            return None
        if s["expires_at"] < now:
            conn.execute("DELETE FROM sessions WHERE token=?", (token,))
            conn.commit()
            return None
        conn.execute("UPDATE sessions SET last_seen=?, expires_at=? WHERE token=?",
                     (now, now + ttl, token))
        urow = conn.execute("SELECT * FROM users WHERE id=?", (s["user_id"],)).fetchone()
        conn.commit()
        return _to_user(urow)
    finally:
        conn.close()


def delete_session(token: str) -> None:
    conn = db.connect()
    try:
        conn.execute("DELETE FROM sessions WHERE token=?", (token,))
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 4: 运行确认通过**

Run: `PYTHONIOENCODING=utf-8 E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/test_accounts_unit.py`
Expected: PASS（全部）

- [ ] **Step 5: 提交**

```bash
git add src/accounts.py scripts/test_accounts_unit.py
git commit -m "feat(accounts): 邮箱验证 token + 服务端会话(滑动过期)"
```

---

### Task 4: 笔记归属与提交历史仓储（`src/userdata.py`）

**Files:**
- Create: `src/userdata.py`
- Test: `scripts/test_userdata_unit.py`

- [ ] **Step 1: 写失败测试 `scripts/test_userdata_unit.py`**

```python
"""userdata.py：notes_repo / jobs_repo 读写。临时库，不碰真库/GPU。
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_userdata_unit.py"""
import sys, os, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import db  # noqa: E402
db.set_db_path(os.path.join(tempfile.mkdtemp(), "t.db"))
db.init_db()
from userdata import notes_repo, jobs_repo  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

# ---------- notes ----------
notes_repo.upsert(id="n1", owner_id="u1", visibility="private",
                  storage_path="data/user_notes/u1/n1", title="T1", domain="编程教学",
                  duration_sec=100, chunks=5, chapters=2, uploader="up", webpage_url="")
notes_repo.upsert(id="pub1", owner_id="admin", visibility="public",
                  storage_path="web/public/notes/pub1", title="P1", domain="学习",
                  duration_sec=50, chunks=3, chapters=1, uploader="", webpage_url="")
notes_repo.upsert(id="n2", owner_id="u2", visibility="private",
                  storage_path="data/user_notes/u2/n2", title="T2", domain="学习",
                  duration_sec=10, chunks=1, chapters=1, uploader="", webpage_url="")

g = notes_repo.get("n1")
check(g is not None and g["owner_id"] == "u1" and g["visibility"] == "private",
      "notes.get 取回归属/可见性")
check(notes_repo.get("nope") is None, "notes.get 未知 None")
check([n["id"] for n in notes_repo.list_public()] == ["pub1"], "list_public 仅公开")
mine = [n["id"] for n in notes_repo.list_mine("u1")]
check(mine == ["n1"], f"list_mine 仅本人私有 -> {mine}")
# upsert 幂等更新标题
notes_repo.upsert(id="n1", owner_id="u1", visibility="private",
                  storage_path="data/user_notes/u1/n1", title="T1b", domain="编程教学",
                  duration_sec=100, chunks=5, chapters=2, uploader="up", webpage_url="")
check(notes_repo.get("n1")["title"] == "T1b", "upsert 幂等覆盖标题")
notes_repo.delete("n1")
check(notes_repo.get("n1") is None, "notes.delete 生效")

# ---------- jobs ----------
jobs_repo.record("j1", "u1", "https://a/v", is_local=False, quality="360p", status="queued")
check(jobs_repo.get("j1")["status"] == "queued", "jobs.record 入库 queued")
check(jobs_repo.count_active("u1") == 1, "count_active 计 queued")
jobs_repo.update_status("j1", "running")
check(jobs_repo.count_active("u1") == 1, "running 仍算在飞")
jobs_repo.update_status("j1", "done", note_id="n1")
g = jobs_repo.get("j1")
check(g["status"] == "done" and g["note_id"] == "n1" and g["finished_at"] is not None,
      "终态 done 写 note_id + finished_at")
check(jobs_repo.count_active("u1") == 0, "done 不再算在飞")
jobs_repo.record("j2", "u1", "https://b/v", is_local=False, quality="best", status="queued")
jobs_repo.update_status("j2", "failed", error="boom")
check(jobs_repo.get("j2")["error"] == "boom", "failed 记 error")
hist = [j["id"] for j in jobs_repo.list_history("u1")]
check(set(hist) == {"j1", "j2"} and len(hist) == 2, f"list_history 全量 -> {hist}")
check(jobs_repo.list_history("u2") == [], "他人历史不串")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ==="); sys.exit(1)
print("=== ALL CHECKS PASSED ===")
```

- [ ] **Step 2: 运行确认失败**

Run: `PYTHONIOENCODING=utf-8 E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/test_userdata_unit.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'userdata'`

- [ ] **Step 3: 实现 `src/userdata.py`**

```python
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
```

- [ ] **Step 4: 运行确认通过**

Run: `PYTHONIOENCODING=utf-8 E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/test_userdata_unit.py`
Expected: PASS（全部）

- [ ] **Step 5: 提交**

```bash
git add src/userdata.py scripts/test_userdata_unit.py
git commit -m "feat(userdata): notes/jobs 仓储(归属/历史/在飞计数)"
```

---

### Task 5: 幂等 key 纳入 user_id（修改 `src/jobqueue.py`）

**Files:**
- Modify: `src/jobqueue.py:56-62`（`idempotency_key`）
- Test: `scripts/test_idempotency_user.py`

- [ ] **Step 1: 写失败测试 `scripts/test_idempotency_user.py`**

```python
"""idempotency_key 现按 user_id 隔离：同用户同 URL 同 key；不同用户不同 key；
无 user_id 行为稳定（向后兼容公开/旧路径）。无 Redis/网络。
Run: .venv/Scripts/python.exe scripts/test_idempotency_user.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import jobqueue as JQ  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

base = {"quality": "360p", "user_id": "u1"}
k_u1 = JQ.idempotency_key("https://a/v", base)
k_u1b = JQ.idempotency_key("HTTPS://A/V  ", dict(base))  # 归一仍同
k_u2 = JQ.idempotency_key("https://a/v", {"quality": "360p", "user_id": "u2"})
k_none = JQ.idempotency_key("https://a/v", {"quality": "360p"})

check(k_u1 == k_u1b, "同用户同 URL（归一后）同 key")
check(k_u1 != k_u2, "不同用户同 URL 不同 key")
check(k_u1 != k_none and k_u2 != k_none, "带/不带 user_id 不同 key")
check(len(k_u1) == 16, "key 仍 16 hex")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ==="); sys.exit(1)
print("=== ALL CHECKS PASSED ===")
```

- [ ] **Step 2: 运行确认失败**

Run: `E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/test_idempotency_user.py`
Expected: FAIL — `k_u1 != k_u2`（当前不含 user_id，两者相等）

- [ ] **Step 3: 修改 `idempotency_key`**

把 `src/jobqueue.py` 的 `idempotency_key`（约 56-62 行）替换为：

```python
def idempotency_key(source: str, opts: dict) -> str:
    """稳定 key：归一化 source + quality + is_local + user_id。
    含 user_id 使两用户提交同一 URL 各得各自私有笔记，互不复用。"""
    norm = (source or "").strip().lower()
    payload = json.dumps(
        {"s": norm, "q": opts.get("quality") or "best",
         "l": bool(opts.get("is_local")), "u": opts.get("user_id") or ""},
        sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
```

- [ ] **Step 4: 运行确认通过 + 回归既有 worker 集成测试**

Run: `E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/test_idempotency_user.py`
Expected: PASS

Run: `E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/test_worker_integration.py`
Expected: PASS（既有 6 组仍过——无 user_id 时行为稳定，旧测试不受影响）

- [ ] **Step 5: 提交**

```bash
git add src/jobqueue.py scripts/test_idempotency_user.py
git commit -m "feat(jobqueue): 幂等 key 纳入 user_id 做按用户隔离"
```

---

### Task 6: FastAPI 鉴权依赖（`src/authdeps.py`）

**Files:**
- Create: `src/authdeps.py`
- Test: `scripts/test_authdeps_unit.py`

- [ ] **Step 1: 写失败测试 `scripts/test_authdeps_unit.py`**

```python
"""authdeps：current_user / require_user / require_admin。用真临时库 + 假 Request
（只需 .cookies）。require_* 抛 HTTPException(401/403)。
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_authdeps_unit.py"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import db  # noqa: E402
db.set_db_path(os.path.join(tempfile.mkdtemp(), "t.db"))
db.init_db()
import accounts as A  # noqa: E402
import authdeps as AD  # noqa: E402
from fastapi import HTTPException  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

class FakeReq:
    def __init__(self, cookies):
        self.cookies = cookies

uid = A.create_user("a@x.com", "pw12345", "A", email_verified=True)
aid = A.create_user("admin@x.com", "pw12345", "Adm", role="admin", email_verified=True)
stok = A.create_session(uid)
atok = A.create_session(aid)

check(AD.current_user(FakeReq({})) is None, "无 cookie -> current_user None")
check(AD.current_user(FakeReq({AD.SESSION_COOKIE: "bad"})) is None, "坏 token None")
cu = AD.current_user(FakeReq({AD.SESSION_COOKIE: stok}))
check(cu is not None and cu["id"] == uid, "有效会话 -> current_user 命中")

# require_user：以 current_user 的返回值作为依赖入参
check(AD.require_user(cu)["id"] == uid, "require_user 放行登录用户")
got = None
try:
    AD.require_user(None)
except HTTPException as e:
    got = e.status_code
check(got == 401, "require_user 匿名 -> 401")

# require_admin
au = AD.current_user(FakeReq({AD.SESSION_COOKIE: atok}))
check(AD.require_admin(au)["id"] == aid, "require_admin 放行 admin")
got = None
try:
    AD.require_admin(cu)  # 普通用户
except HTTPException as e:
    got = e.status_code
check(got == 403, "require_admin 普通用户 -> 403")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ==="); sys.exit(1)
print("=== ALL CHECKS PASSED ===")
```

- [ ] **Step 2: 运行确认失败**

Run: `PYTHONIOENCODING=utf-8 E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/test_authdeps_unit.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'authdeps'`

- [ ] **Step 3: 实现 `src/authdeps.py`**

```python
"""FastAPI 鉴权依赖：从 httpOnly cookie 取会话 → 用户。
current_user 不抛（匿名返 None，给 404-不泄露 的端点用）；require_user/admin 抛 401/403。"""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request

import accounts

SESSION_COOKIE = "ng_session"


def current_user(request: Request) -> Optional[dict]:
    token = request.cookies.get(SESSION_COOKIE)
    return accounts.get_session_user(token) if token else None


def require_user(user: Optional[dict] = Depends(current_user)) -> dict:
    if user is None:
        raise HTTPException(401, "需要登录")
    return user


def require_admin(user: dict = Depends(require_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(403, "需要管理员权限")
    return user
```

- [ ] **Step 4: 运行确认通过**

Run: `PYTHONIOENCODING=utf-8 E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/test_authdeps_unit.py`
Expected: PASS（全部）

- [ ] **Step 5: 提交**

```bash
git add src/authdeps.py scripts/test_authdeps_unit.py
git commit -m "feat(authdeps): current_user/require_user/require_admin 依赖"
```

---

### Task 7: 私有发布 + 笔记字段抽取（修改 `src/service_common.py`）

把 publish 拆出共用核心，新增私有发布到 `data/user_notes/{uid}/{id}/`（视频随目录放为 `video.mp4`），并把列表展示字段抽取（含 `_guess_domain`，从 server 迁入）集中到这里。

**Files:**
- Modify: `src/service_common.py`
- Test: `scripts/test_publish_private.py`

- [ ] **Step 1: 写失败测试 `scripts/test_publish_private.py`**

```python
"""service_common 私有发布 + 字段抽取。用临时 DATA_OUTPUTS/DATA_RAW/USER_NOTES_DIR
造假产物，验证私有目录落位 + video.mp4 + extract_note_fields。不碰 GPU/网络。
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_publish_private.py"""
import sys, os, json, tempfile
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import service_common as SC  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

# 把 SC 的目录常量重定向到临时区
base = Path(tempfile.mkdtemp())
SC.DATA_OUTPUTS = base / "outputs"; SC.DATA_OUTPUTS.mkdir()
SC.DATA_RAW = base / "raw"; SC.DATA_RAW.mkdir()
SC.USER_NOTES_DIR = base / "user_notes"
SC.NOTES_DIR = base / "web" / "notes"
SC.VIDEOS_DIR = base / "web" / "videos"

stem = "BVtest_p0"
pref = f"{stem}.large-v3.neural.texttile"
(SC.DATA_OUTPUTS / f"{pref}.summary.json").write_text(
    json.dumps([{"start": 0, "end": 42}]), encoding="utf-8")
(SC.DATA_OUTPUTS / f"{pref}.chapters.json").write_text(
    json.dumps({"chapters": [{"title": "C1"}, {"title": "C2"}]}), encoding="utf-8")
(SC.DATA_OUTPUTS / f"{pref}.keyframes").mkdir()
(SC.DATA_OUTPUTS / f"{pref}.keyframes" / "k0.jpg").write_bytes(b"img")
meta_stem = stem.split(".")[0]
(SC.DATA_RAW / f"{meta_stem}.meta.json").write_text(
    json.dumps({"title": "Python 入门", "uploader": "老师", "webpage_url": "http://u"}),
    encoding="utf-8")
(SC.DATA_RAW / f"{meta_stem}.mp4").write_bytes(b"video-bytes")

note_id, storage_path, fields = SC.publish_private(stem, "u1")
nd = Path(storage_path)
check(note_id == stem, "note_id == stem")
check(str(nd).replace("\\", "/").endswith(f"user_notes/u1/{stem}"),
      f"私有目录在 user_notes/u1 下 -> {nd}")
check((nd / "summary.json").exists() and (nd / "chapters.json").exists(),
      "summary/chapters 落位")
check((nd / "meta.json").exists(), "meta.json 落位")
check((nd / "keyframes" / "k0.jpg").exists(), "keyframes 落位")
check((nd / "video.mp4").read_bytes() == b"video-bytes", "视频随目录放为 video.mp4")
check(not (SC.VIDEOS_DIR / f"{stem}.mp4").exists(), "私有视频不进公开 videos 目录")
check(fields["title"] == "Python 入门" and fields["domain"] == "编程教学",
      f"字段抽取 title/domain -> {fields.get('title')}/{fields.get('domain')}")
check(fields["duration_sec"] == 42 and fields["chunks"] == 1 and fields["chapters"] == 2,
      f"字段 dur/chunks/chapters -> {fields}")
check(fields["uploader"] == "老师" and fields["webpage_url"] == "http://u",
      "字段 uploader/webpage_url")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ==="); sys.exit(1)
print("=== ALL CHECKS PASSED ===")
```

- [ ] **Step 2: 运行确认失败**

Run: `PYTHONIOENCODING=utf-8 E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/test_publish_private.py`
Expected: FAIL — `AttributeError: module 'service_common' has no attribute 'publish_private'`

- [ ] **Step 3: 修改 `src/service_common.py`**

3a. 在路径常量区（`DATA_RAW = ...` 那行之后，约第 17 行）追加：

```python
USER_NOTES_DIR = ROOT / "data" / "user_notes"
```

3b. 把现有 `publish_to_web` 整个函数（约 65-108 行）替换为下面的「共用核心 + 公开 + 私有 + 字段抽取 + 域猜测」：

```python
def _guess_domain(title: str) -> str:
    t = (title or "").lower()
    if "python" in t or "代码" in t or "编程" in t:
        return "编程教学"
    if "考研" in t or "操作系统" in t or "计算机网络" in t or "线代" in t or "线性代数" in t:
        return "考研专业课"
    if "vlog" in t or "日常" in t or "外卖" in t or "小镇" in t:
        return "Vlog"
    if "评测" in t or "iphone" in t or "ios" in t:
        return "数码评测"
    return "学习"


def _copy_artifacts(stem: str, note_dir: Path) -> None:
    """把 outputs 的 summary/chapters/keyframes + raw 的 meta.json copy 进 note_dir。"""
    note_dir.mkdir(parents=True, exist_ok=True)

    def _pick_latest(pattern: str) -> Optional[Path]:
        cands = sorted(DATA_OUTPUTS.glob(pattern), key=lambda p: -p.stat().st_mtime)
        return cands[0] if cands else None

    for kind in ("summary", "chapters"):
        src = _pick_latest(f"{stem}.large-v3.neural.texttile*.{kind}.json")
        if src:
            shutil.copy(src, note_dir / f"{kind}.json")

    meta_stem = stem.split(".")[0]
    meta_src = DATA_RAW / f"{meta_stem}.meta.json"
    if meta_src.exists():
        shutil.copy(meta_src, note_dir / "meta.json")

    kf_candidates = sorted(
        [p for p in DATA_OUTPUTS.glob(f"{stem}.large-v3.neural.texttile*.keyframes")
         if p.is_dir()], key=lambda p: -p.stat().st_mtime)
    if kf_candidates:
        kf_dst = note_dir / "keyframes"
        kf_dst.mkdir(parents=True, exist_ok=True)
        for f in kf_candidates[0].iterdir():
            if f.is_file():
                try:
                    shutil.copy(f, kf_dst / f.name)
                except PermissionError:
                    pass


def _find_source_video(stem: str) -> Optional[Path]:
    meta_stem = stem.split(".")[0]
    for cand in [DATA_RAW / f"{meta_stem}_p0.mp4",
                 DATA_RAW / f"{meta_stem}.mp4",
                 *DATA_RAW.glob(f"{meta_stem}*.mp4")]:
        if cand.exists():
            return cand
    return None


def extract_note_fields(note_dir: Path) -> dict:
    """从 note_dir 的 summary/chapters/meta 读出列表展示冗余字段。"""
    import json
    title = note_dir.name
    uploader = webpage_url = ""
    duration_sec = chunks = chapters = 0
    sp = note_dir / "summary.json"
    if sp.exists():
        try:
            summary = json.loads(sp.read_text(encoding="utf-8"))
            chunks = len(summary)
            if summary:
                duration_sec = int(summary[-1].get("end", 0))
        except Exception:
            pass
    cp = note_dir / "chapters.json"
    if cp.exists():
        try:
            chapters = len(json.loads(cp.read_text(encoding="utf-8")).get("chapters", []))
        except Exception:
            pass
    mp = note_dir / "meta.json"
    if mp.exists():
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
            title = meta.get("title") or title
            uploader = meta.get("uploader", "")
            webpage_url = meta.get("webpage_url", "")
        except Exception:
            pass
    return {"title": title, "domain": _guess_domain(title),
            "duration_sec": duration_sec, "chunks": chunks, "chapters": chapters,
            "uploader": uploader, "webpage_url": webpage_url}


def publish_to_web(stem: str) -> str:
    """公开发布：copy 产物到 web/public/{notes,videos}/，返回 note_id。
    （公开展示区/admin 用；新用户生成走 publish_private。）"""
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    note_dir = NOTES_DIR / stem
    _copy_artifacts(stem, note_dir)
    vid = _find_source_video(stem)
    if vid:
        shutil.copy(vid, VIDEOS_DIR / f"{stem}.mp4")
    return stem


def publish_private(stem: str, user_id: str) -> tuple[str, str, dict]:
    """私有发布：copy 产物 + 视频(video.mp4) 到 data/user_notes/{uid}/{stem}/（公开静态不可达）。
    返回 (note_id, storage_path, 展示字段 dict)。"""
    note_dir = USER_NOTES_DIR / user_id / stem
    _copy_artifacts(stem, note_dir)
    vid = _find_source_video(stem)
    if vid:
        shutil.copy(vid, note_dir / "video.mp4")
    return stem, str(note_dir), extract_note_fields(note_dir)
```

注意：`extract_note_fields` 内部 `import json` 是局部的，避免在文件顶部新增 import（保持 diff 小）；若文件顶部已有 `import json` 则可删除局部那行。当前 `service_common.py` 顶部**没有** `import json`，故保留局部导入。

- [ ] **Step 4: 运行确认通过 + 回归 worker 集成（它 monkeypatch 了 publish_to_web，应不受影响）**

Run: `PYTHONIOENCODING=utf-8 E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/test_publish_private.py`
Expected: PASS（全部）

Run: `E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/test_worker_integration.py`
Expected: PASS（不受影响）

- [ ] **Step 5: 提交**

```bash
git add src/service_common.py scripts/test_publish_private.py
git commit -m "feat(service_common): 私有发布 publish_private + 字段抽取(域猜测迁入)"
```

---

### Task 8: worker 私有发布 + SQLite 终态镜像（修改 `src/worker_tasks.py`）

worker 按 `opts["user_id"]` 分流：有 uid → 私有发布 + 写 `notes` 行 + 镜像 `jobs` 终态；无 uid → 走公开 `publish_to_web`（旧路径/admin，保持既有集成测试不破）。

**Files:**
- Modify: `src/worker_tasks.py`
- Test: `scripts/test_worker_user_mirror.py`

- [ ] **Step 1: 写失败测试 `scripts/test_worker_user_mirror.py`**

```python
"""worker 带 user_id：enqueue→SimpleWorker→私有 publish→notes 行写入→jobs 终态 done。
fakeredis + 临时 SQLite + mock subprocess/publish_private。不碰 GPU。
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_worker_user_mirror.py"""
import sys, os, socket, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import db  # noqa: E402
db.set_db_path(os.path.join(tempfile.mkdtemp(), "t.db"))
db.init_db()
import fakeredis  # noqa: E402
from rq import SimpleWorker  # noqa: E402
from rq.timeouts import TimerDeathPenalty  # noqa: E402
import jobqueue as JQ  # noqa: E402
import worker_tasks as WT  # noqa: E402
import service_common as SC  # noqa: E402
from userdata import notes_repo, jobs_repo  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

def fresh():
    srv = fakeredis.FakeServer()
    kv = fakeredis.FakeStrictRedis(server=srv, decode_responses=True)
    rq_conn = fakeredis.FakeStrictRedis(server=srv)
    JQ.set_connections(kv=kv, rq=rq_conn)
    return rq_conn

def run_burst(conn):
    w = SimpleWorker([JQ.get_queue()], connection=conn, prepare_for_work=False)
    w.hostname = socket.gethostname(); w.pid = os.getpid()
    w.death_penalty_class = TimerDeathPenalty
    w.work(burst=True, logging_level="ERROR")

conn = fresh()
WT._run_pipeline_subprocess = lambda j, s, o: ("BVuser_p0", 0)
# 假私有发布：不真 copy，返回字段
SC.publish_private = lambda stem, uid: (
    stem, f"data/user_notes/{uid}/{stem}",
    {"title": "私有笔记", "domain": "学习", "duration_sec": 60,
     "chunks": 4, "chapters": 2, "uploader": "u", "webpage_url": ""})

opts = {"quality": "360p", "user_id": "u1"}
jid, _ = JQ.enqueue_generate("https://x/v", opts)
# enqueue 镜像由 server 端做；这里手动补一行 queued 模拟 api 已记录
jobs_repo.record(jid, "u1", "https://x/v", is_local=False, quality="360p", status="queued")
run_burst(conn)

st = JQ.job_state(jid)
check(st["stage"] == "done" and st["note_id"] == "BVuser_p0", "Redis 仍 done(热路径不变)")
note = notes_repo.get("BVuser_p0")
check(note is not None and note["owner_id"] == "u1" and note["visibility"] == "private",
      "私有 notes 行写入(owner/visibility)")
check(note["title"] == "私有笔记" and note["chapters"] == 2, "notes 展示字段镜像")
job = jobs_repo.get(jid)
check(job["status"] == "done" and job["note_id"] == "BVuser_p0", "jobs 终态镜像 done")
check(job["finished_at"] is not None, "jobs.finished_at 已写")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ==="); sys.exit(1)
print("=== ALL CHECKS PASSED ===")
```

- [ ] **Step 2: 运行确认失败**

Run: `PYTHONIOENCODING=utf-8 E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/test_worker_user_mirror.py`
Expected: FAIL（notes 行未写入——worker 尚未分流私有发布/镜像）

- [ ] **Step 3: 修改 `src/worker_tasks.py`**

3a. 在顶部 import 区（`import service_common as SC` 之后）追加：

```python
import userdata
```

3b. 在 `run_generate` 函数**之前**（紧接 `_no_retry` 之后）新增镜像/发布 helper：

```python
def _mirror_job(opts: dict, job_id: str, status: str, *, note_id=None, error=None) -> None:
    """有 user_id 才镜像 SQLite jobs 终态（无 uid = 旧/公开路径，不写库）。"""
    if opts.get("user_id"):
        userdata.jobs_repo.update_status(job_id, status, note_id=note_id, error=error)


def _publish(stem: str, opts: dict) -> str:
    """按 user_id 分流：有 uid → 私有发布 + 写 notes 行；否则公开发布。返回 note_id。"""
    uid = opts.get("user_id")
    if uid:
        note_id, storage_path, fields = SC.publish_private(stem, uid)
        userdata.notes_repo.upsert(id=note_id, owner_id=uid, visibility="private",
                                   storage_path=storage_path, **fields)
        return note_id
    return SC.publish_to_web(stem)
```

3c. 在 `run_generate` 里：把开头 `set_progress(... stage="running" ...)` 之后补一行镜像 running；把 `note_id = SC.publish_to_web(stem)` 改为 `_publish`；在各 `failed` 分支补镜像；done 分支补镜像。具体——

将 `run_generate` 整个函数体替换为：

```python
def run_generate(job_id: str, source: str, opts: dict) -> Optional[str]:
    started = time.time()
    jobqueue.set_progress(job_id, stage="running", percent=4, msg="启动 pipeline")
    _mirror_job(opts, job_id, "running")
    try:
        stem, returncode = _run_pipeline_subprocess(job_id, source, opts)
    except Exception as e:
        jobqueue.set_progress(job_id, stage="failed", percent=0, msg=f"运行错误：{e}")
        _mirror_job(opts, job_id, "failed", error=f"运行错误：{e}")
        raise

    if not stem:
        stem = _scan_output_fallback(job_id, started)
        if stem:
            jobqueue.set_progress(job_id, stage="收尾", percent=98,
                                  msg=f"进程异常退出但输出完整（{stem}），尝试 publish")

    if not stem:
        jobqueue.set_progress(job_id, stage="failed", percent=0,
                              msg=f"pipeline 退出码 {returncode}，未找到输出文件",
                              returncode=returncode)
        _mirror_job(opts, job_id, "failed", error=f"无输出(rc={returncode})")
        _no_retry()
        raise PipelineFailed(f"job {job_id}: no output (rc={returncode})")

    try:
        note_id = _publish(stem, opts)
    except Exception as e:
        jobqueue.set_progress(job_id, stage="failed", percent=0, msg=f"产出复制失败：{e}")
        _mirror_job(opts, job_id, "failed", error=f"产出复制失败：{e}")
        raise

    msg = "完成"
    if returncode not in (0, None):
        msg = f"完成（pipeline 退出码 {returncode}，已知 Windows cleanup 问题，不影响输出）"
    jobqueue.set_progress(job_id, stage="done", percent=100, msg=msg,
                          note_id=note_id, returncode=returncode)
    _mirror_job(opts, job_id, "done", note_id=note_id)
    return note_id
```

- [ ] **Step 4: 运行确认通过 + 回归既有 worker 集成（无 uid 路径）**

Run: `PYTHONIOENCODING=utf-8 E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/test_worker_user_mirror.py`
Expected: PASS（全部）

Run: `E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/test_worker_integration.py`
Expected: PASS（无 user_id 时不写 SQLite，旧 6 组仍过）

- [ ] **Step 5: 提交**

```bash
git add src/worker_tasks.py scripts/test_worker_user_mirror.py
git commit -m "feat(worker): 按 user_id 私有发布 + SQLite jobs/notes 终态镜像"
```

---

### Task 9: 鉴权端点 + DB 初始化接线（修改 `src/server.py`、`scripts/run_worker.py`）

新增 `/api/auth/*`（register/verify/login/logout/me），DB 在 api 与 worker 启动时 `init_db()`。

**Files:**
- Modify: `src/server.py`
- Modify: `scripts/run_worker.py`
- Test: `scripts/test_auth_api.py`

- [ ] **Step 1: 写失败测试 `scripts/test_auth_api.py`**

```python
"""鉴权 API（TestClient）：注册→未验证登录 403→验证→登录下发 cookie→me→登出→me 401。
临时库；不需 Redis（不碰队列端点）。验证 token 直接从 DB 取，跳过控制台解析。
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_auth_api.py"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ["NOTEGEN_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
import db  # noqa: E402
db.set_db_path(os.environ["NOTEGEN_DB_PATH"])
from fastapi.testclient import TestClient  # noqa: E402
import server  # noqa: E402
import authdeps as AD  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

c = TestClient(server.app)

r = c.post("/api/auth/register",
           json={"email": "Bob@X.com", "password": "pw123456", "display_name": "Bob"})
check(r.status_code == 201, f"注册 201 -> {r.status_code}")

# 未验证 → 登录 403
r = c.post("/api/auth/login", json={"email": "bob@x.com", "password": "pw123456"})
check(r.status_code == 403, f"未验证登录 403 -> {r.status_code}")

# 从 DB 取验证 token（替代解析控制台）
conn = db.connect()
tok = conn.execute("SELECT token FROM email_verifications").fetchone()["token"]
conn.close()
r = c.get(f"/api/auth/verify?token={tok}")
check(r.status_code == 200, f"验证 200 -> {r.status_code}")

# 登录成功 + 下发 httpOnly cookie
r = c.post("/api/auth/login", json={"email": "bob@x.com", "password": "pw123456"})
check(r.status_code == 200, f"验证后登录 200 -> {r.status_code}")
check(AD.SESSION_COOKIE in r.cookies, "登录下发会话 cookie")
check(r.json()["email"] == "bob@x.com", "登录返回 profile")

# 错密码统一文案
rb = c.post("/api/auth/login", json={"email": "bob@x.com", "password": "WRONG"})
check(rb.status_code == 401, f"错密码 401 -> {rb.status_code}")

# me（TestClient 自动带 cookie jar）
r = c.get("/api/auth/me")
check(r.status_code == 200 and r.json()["email"] == "bob@x.com", "me 返回当前用户")

# 重复邮箱注册 409
r = c.post("/api/auth/register",
           json={"email": "bob@x.com", "password": "x2345678", "display_name": "B2"})
check(r.status_code == 409, f"重复邮箱 409 -> {r.status_code}")

# 登出 → me 401
r = c.post("/api/auth/logout")
check(r.status_code == 200, "登出 200")
r = c.get("/api/auth/me")
check(r.status_code == 401, f"登出后 me 401 -> {r.status_code}")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ==="); sys.exit(1)
print("=== ALL CHECKS PASSED ===")
```

- [ ] **Step 2: 运行确认失败**

Run: `PYTHONIOENCODING=utf-8 E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/test_auth_api.py`
Expected: FAIL — `404` on `/api/auth/register`（端点尚不存在）

- [ ] **Step 3: 修改 `src/server.py`**

3a. 顶部 import 区改动：

把现有
```python
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
```
替换为
```python
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
```

3b. 在 `from service_common import (...)` 之后追加新模块 import + DB 初始化：

```python
import db  # noqa: E402
import accounts  # noqa: E402
import authdeps  # noqa: E402
from authdeps import current_user, require_user  # noqa: E402
from userdata import notes_repo, jobs_repo  # noqa: E402

db.init_db()  # 启动即建表（幂等）

import os as _os  # noqa: E402
_COOKIE_SECURE = _os.environ.get("NOTEGEN_COOKIE_SECURE", "0") == "1"
_VERIFY_BASE = _os.environ.get("NOTEGEN_VERIFY_BASE", "http://localhost:3000")
```

3c. 在 `class GenerateReq` 之前（HTTP endpoints 段开头）插入鉴权请求模型 + 端点：

```python
class RegisterReq(BaseModel):
    email: str
    password: str
    display_name: str


class LoginReq(BaseModel):
    email: str
    password: str


@app.post("/api/auth/register", status_code=201)
def auth_register(req: RegisterReq):
    email = (req.email or "").strip()
    if not email or "@" not in email:
        raise HTTPException(400, "邮箱格式不正确")
    if len(req.password or "") < 8:
        raise HTTPException(400, "密码至少 8 位")
    try:
        uid = accounts.create_user(email, req.password, req.display_name or email)
    except ValueError:
        raise HTTPException(409, "该邮箱已注册")
    token = accounts.create_verification_token(uid)
    # dev：不发真邮件，把验证链接打到控制台
    print(f"[VERIFY] {_VERIFY_BASE}/verify?token={token}", flush=True)
    return {"ok": True, "message": "注册成功，请查看控制台验证链接完成邮箱验证"}


@app.get("/api/auth/verify")
def auth_verify(token: str):
    uid = accounts.consume_verification_token(token)
    if uid is None:
        raise HTTPException(400, "验证链接无效或已过期")
    return {"ok": True, "message": "邮箱验证成功，请登录"}


@app.post("/api/auth/login")
def auth_login(req: LoginReq):
    user = accounts.verify_login(req.email, req.password)
    if user is None:
        raise HTTPException(401, "邮箱或密码错误")
    if not user["email_verified"]:
        raise HTTPException(403, "请先验证邮箱（查看控制台验证链接）")
    token = accounts.create_session(user["id"])
    resp = JSONResponse(user)
    resp.set_cookie(authdeps.SESSION_COOKIE, token, httponly=True, samesite="lax",
                    max_age=accounts.SESSION_TTL, secure=_COOKIE_SECURE, path="/")
    return resp


@app.post("/api/auth/logout")
def auth_logout(request: Request):
    token = request.cookies.get(authdeps.SESSION_COOKIE)
    if token:
        accounts.delete_session(token)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(authdeps.SESSION_COOKIE, path="/")
    return resp


@app.get("/api/auth/me")
def auth_me(user: dict = Depends(require_user)):
    return user
```

3d. 修改 `scripts/run_worker.py`：在 `import jobqueue` 之后追加 `import db` 并在 `main()` 开头调用 `db.init_db()`：

把
```python
import jobqueue  # noqa: E402


def main():
    conn = jobqueue.get_rq()
```
替换为
```python
import jobqueue  # noqa: E402
import db  # noqa: E402


def main():
    db.init_db()  # worker 先于 api 起也能写库
    conn = jobqueue.get_rq()
```

- [ ] **Step 4: 运行确认通过**

Run: `PYTHONIOENCODING=utf-8 E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/test_auth_api.py`
Expected: PASS（全部）

- [ ] **Step 5: 提交**

```bash
git add src/server.py scripts/run_worker.py scripts/test_auth_api.py
git commit -m "feat(server): 鉴权端点 register/verify/login/logout/me + DB 启动初始化"
```

---

### Task 10: 队列/笔记/历史端点加鉴权与归属（修改 `src/server.py`）

generate/upload 要登录 + 每用户在飞 1 + 入队镜像；jobs 归属校验；`/api/notes` 拆 public/mine；新增 `/api/history`、`/api/jobs/{id}/retry`、私有文件托管；DELETE 加归属。集成测试在 Task 11 统一覆盖；本任务先用 TestClient 烟测鉴权门禁。

**Files:**
- Modify: `src/server.py`
- Test: `scripts/test_endpoints_authz.py`

- [ ] **Step 1: 写失败测试 `scripts/test_endpoints_authz.py`（门禁烟测，不跑队列）**

```python
"""端点门禁烟测：匿名访问受保护端点应 401；公开端点开放。临时库。
完整多用户队列链路在 test_multiuser_integration.py。
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_endpoints_authz.py"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ["NOTEGEN_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
import db  # noqa: E402
db.set_db_path(os.environ["NOTEGEN_DB_PATH"])
from fastapi.testclient import TestClient  # noqa: E402
import server  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

c = TestClient(server.app)

# 匿名受保护端点 → 401
for method, path in [("post", "/api/generate"), ("get", "/api/notes/mine"),
                     ("get", "/api/history")]:
    r = getattr(c, method)(path, json={} if method == "post" else None)
    check(r.status_code == 401, f"匿名 {method.upper()} {path} -> 401 (got {r.status_code})")

# 公开端点开放（空库返空 list）
r = c.get("/api/notes/public")
check(r.status_code == 200 and r.json() == [], f"匿名 /api/notes/public 200 [] -> {r.status_code}")

# 私有文件端点：未知 note 匿名 → 404（不泄露）
r = c.get("/api/notes/ghost/file/summary.json")
check(r.status_code == 404, f"匿名取未知私有文件 404 -> {r.status_code}")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ==="); sys.exit(1)
print("=== ALL CHECKS PASSED ===")
```

- [ ] **Step 2: 运行确认失败**

Run: `PYTHONIOENCODING=utf-8 E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/test_endpoints_authz.py`
Expected: FAIL —`/api/generate` 当前匿名可入（422/503 而非 401），`/api/notes/mine` 404 等。

- [ ] **Step 3: 修改 `src/server.py`**

3a. 替换 `generate`（约 78-88 行）为：

```python
@app.post("/api/generate")
def generate(req: GenerateReq, user: dict = Depends(require_user)):
    url = (req.url or "").strip()
    if not url:
        raise HTTPException(400, "url is required")
    quality = normalize_quality(req.quality)
    if jobs_repo.count_active(user["id"]) >= 1:
        raise HTTPException(409, "你已有任务在处理中，请等它完成后再提交")
    opts = {"quality": quality, "user_id": user["id"]}
    try:
        job_id, is_new = jobqueue.enqueue_generate(url, opts)
    except _redis_pkg.exceptions.ConnectionError:
        raise HTTPException(503, "队列服务暂不可用，请稍后再试")
    if is_new:
        jobs_repo.record(job_id, user["id"], url, is_local=False,
                         quality=quality, status="queued")
    return {"job_id": job_id}
```

3b. 在 `upload` 的签名里加用户依赖，并在落盘后注入 user_id + 在飞校验 + 入队镜像。把 `async def upload(` 的参数列表改为：

```python
async def upload(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    uploader: Optional[str] = Form(None),
    user: dict = Depends(require_user),
):
```

并把 upload 里
```python
    opts = {"is_local": True, "quality": "best", "local_meta": meta}
    try:
        job_id, _is_new = jobqueue.enqueue_generate(str(dest), opts)
    except _redis_pkg.exceptions.ConnectionError:
        raise HTTPException(503, "队列服务暂不可用，请稍后再试")
    return {"job_id": job_id, "filename": file.filename,
            "duration": dur, "stored_as": dest.name}
```
替换为
```python
    if jobs_repo.count_active(user["id"]) >= 1:
        try: dest.unlink(missing_ok=True)
        except Exception: pass
        raise HTTPException(409, "你已有任务在处理中，请等它完成后再提交")
    opts = {"is_local": True, "quality": "best", "local_meta": meta,
            "user_id": user["id"]}
    try:
        job_id, is_new = jobqueue.enqueue_generate(str(dest), opts)
    except _redis_pkg.exceptions.ConnectionError:
        raise HTTPException(503, "队列服务暂不可用，请稍后再试")
    if is_new:
        jobs_repo.record(job_id, user["id"], str(dest), is_local=True,
                         quality="best", status="queued")
    return {"job_id": job_id, "filename": file.filename,
            "duration": dur, "stored_as": dest.name}
```

3c. 在 `job_status` 之前插入归属 helper：

```python
def _owned_job_or_404(job_id: str, user: dict) -> dict:
    row = jobs_repo.get(job_id)
    if row is None or row["user_id"] != user["id"]:
        raise HTTPException(404, "job not found")
    return row
```

3d. 把 `job_status`（约 149-157 行）替换为：

```python
@app.get("/api/jobs/{job_id}")
def job_status(job_id: str, user: dict = Depends(require_user)):
    _owned_job_or_404(job_id, user)
    st = jobqueue.job_state(job_id)
    if st is None:
        raise HTTPException(404, "job not found")
    pos = jobqueue.queue_position(job_id)
    if pos is not None:
        st["queue_ahead"] = pos
    return st
```

3e. 把 `job_events`（约 160-176 行）签名与首段改为带归属校验：

```python
@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str, user: dict = Depends(require_user)):
    _owned_job_or_404(job_id, user)
    if jobqueue.job_state(job_id) is None:
        raise HTTPException(404, "job not found")
```
（其后 `async def gen(): ...` 主体不变。）

3f. 删除 server.py 里的 `_guess_domain`（约 179-189 行，已迁入 service_common）。

3g. 把 `list_notes`（`@app.get("/api/notes")` 约 192-226 行）整段替换为 public/mine + history：

```python
def _note_view(n: dict) -> dict:
    return {"id": n["id"], "title": n["title"], "domain": n["domain"],
            "duration_sec": n["duration_sec"], "chunks": n["chunks"],
            "chapters": n["chapters"], "uploader": n["uploader"],
            "webpage_url": n["webpage_url"], "visibility": n["visibility"]}


@app.get("/api/notes/public")
def list_public_notes():
    return [_note_view(n) for n in notes_repo.list_public()]


@app.get("/api/notes/mine")
def list_my_notes(user: dict = Depends(require_user)):
    return [_note_view(n) for n in notes_repo.list_mine(user["id"])]


@app.get("/api/history")
def list_history(user: dict = Depends(require_user)):
    return jobs_repo.list_history(user["id"])


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: str, user: dict = Depends(require_user)):
    row = _owned_job_or_404(job_id, user)
    if jobs_repo.count_active(user["id"]) >= 1:
        raise HTTPException(409, "你已有任务在处理中，请等它完成后再提交")
    opts = {"quality": row["quality"], "user_id": user["id"],
            "is_local": bool(row["is_local"])}
    try:
        new_id, is_new = jobqueue.enqueue_generate(row["source"], opts)
    except _redis_pkg.exceptions.ConnectionError:
        raise HTTPException(503, "队列服务暂不可用，请稍后再试")
    if is_new:
        jobs_repo.record(new_id, user["id"], row["source"],
                         is_local=bool(row["is_local"]), quality=row["quality"],
                         status="queued")
    return {"job_id": new_id}


@app.get("/api/notes/{note_id}/file/{path:path}")
def note_file(note_id: str, path: str, user: Optional[dict] = Depends(current_user)):
    """私有笔记鉴权托管（公开笔记走 Next.js 静态，不绕此端点）。
    非 owner / 未登录 / 不存在 → 一律 404，不泄露存在性。Starlette FileResponse 自带 Range。"""
    row = notes_repo.get(note_id)
    if row is None or row["visibility"] != "private":
        raise HTTPException(404, "not found")
    if user is None or row["owner_id"] != user["id"]:
        raise HTTPException(404, "not found")
    base = Path(row["storage_path"]).resolve()
    target = (base / path).resolve()
    if not target.is_relative_to(base) or not target.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(str(target))
```

3h. 把 `delete_note`（`@app.delete("/api/notes/{note_id}")` 约 229-246 行）替换为带归属/admin 的版本：

```python
@app.delete("/api/notes/{note_id}")
def delete_note(note_id: str, user: dict = Depends(require_user)):
    safe = (note_id or "").strip()
    if not safe or "/" in safe or "\\" in safe or ".." in safe:
        raise HTTPException(400, "invalid note id")
    row = notes_repo.get(safe)
    if row is None:
        raise HTTPException(404, "note not found")
    if row["visibility"] == "private":
        if row["owner_id"] != user["id"]:
            raise HTTPException(404, "note not found")
    else:  # public：仅 admin
        if user.get("role") != "admin":
            raise HTTPException(403, "仅管理员可删除公开笔记")
    removed = []
    if row["visibility"] == "private":
        d = Path(row["storage_path"])
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            removed.append(str(d))
    else:
        note_dir = NOTES_DIR / safe
        video = VIDEOS_DIR / f"{safe}.mp4"
        if note_dir.exists():
            shutil.rmtree(note_dir, ignore_errors=True)
            removed.append(str(note_dir))
        if video.exists():
            video.unlink()
            removed.append(str(video))
    notes_repo.delete(safe)
    return {"deleted": safe, "removed": removed}
```

3i. server.py 顶部已 `from pathlib import Path`（现有 line 17），`shutil` 也已 import（line 15）——无需新增。确认 `Path`/`shutil` 在 import 区存在。

- [ ] **Step 4: 运行确认通过 + 鉴权/auth 回归**

Run: `PYTHONIOENCODING=utf-8 E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/test_endpoints_authz.py`
Expected: PASS（全部）

Run: `PYTHONIOENCODING=utf-8 E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/test_auth_api.py`
Expected: PASS（鉴权端点未回归）

- [ ] **Step 5: 提交**

```bash
git add src/server.py scripts/test_endpoints_authz.py
git commit -m "feat(server): 队列/笔记/历史/retry/私有文件端点加鉴权与归属"
```

---

### Task 11: 多用户端到端集成测试（TestClient + fakeredis + SimpleWorker）

覆盖 spec 集成验收：两用户隔离、私有笔记 404 跨用户、每用户在飞 1、按用户幂等、私有文件 owner 200/非 owner 404。mock subprocess/publish_private，不碰 GPU。

**Files:**
- Test: `scripts/test_multiuser_integration.py`

- [ ] **Step 1: 写测试 `scripts/test_multiuser_integration.py`**

```python
"""多用户端到端：注册/验证/登录→提交→worker→私有笔记+历史→跨用户隔离/404→
在飞 1 上限→按用户幂等。TestClient + fakeredis + SimpleWorker(burst)，mock pipeline。
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_multiuser_integration.py"""
import sys, os, socket, tempfile
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
TMP = tempfile.mkdtemp()
os.environ["NOTEGEN_DB_PATH"] = os.path.join(TMP, "t.db")
import db  # noqa: E402
db.set_db_path(os.environ["NOTEGEN_DB_PATH"])
import fakeredis  # noqa: E402
from rq import SimpleWorker  # noqa: E402
from rq.timeouts import TimerDeathPenalty  # noqa: E402
import jobqueue as JQ  # noqa: E402
import worker_tasks as WT  # noqa: E402
import service_common as SC  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import server  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

# 单一 fakeredis server，api 与 worker 共享
SRV = fakeredis.FakeServer()
KV = fakeredis.FakeStrictRedis(server=SRV, decode_responses=True)
RQc = fakeredis.FakeStrictRedis(server=SRV)
JQ.set_connections(kv=KV, rq=RQc)

# mock pipeline + 私有发布（真写一个 summary.json 让文件端点可服务）
_counter = {"n": 0}
def fake_sub(job_id, source, opts):
    _counter["n"] += 1
    return f"BV{_counter['n']}_p0", 0
WT._run_pipeline_subprocess = fake_sub

def fake_publish_private(stem, uid):
    d = Path(TMP) / "user_notes" / uid / stem
    d.mkdir(parents=True, exist_ok=True)
    (d / "summary.json").write_text('[{"start":0,"end":30}]', encoding="utf-8")
    return stem, str(d), {"title": "我的笔记", "domain": "学习", "duration_sec": 30,
                          "chunks": 1, "chapters": 1, "uploader": "", "webpage_url": ""}
SC.publish_private = fake_publish_private

def run_burst():
    w = SimpleWorker([JQ.get_queue()], connection=RQc, prepare_for_work=False)
    w.hostname = socket.gethostname(); w.pid = os.getpid()
    w.death_penalty_class = TimerDeathPenalty
    w.work(burst=True, logging_level="ERROR")

def signup(client, email):
    client.post("/api/auth/register",
                json={"email": email, "password": "pw123456", "display_name": email})
    conn = db.connect()
    tok = conn.execute(
        "SELECT ev.token FROM email_verifications ev JOIN users u ON u.id=ev.user_id "
        "WHERE u.email=?", (email.lower(),)).fetchone()["token"]
    conn.close()
    client.get(f"/api/auth/verify?token={tok}")
    r = client.post("/api/auth/login", json={"email": email, "password": "pw123456"})
    assert r.status_code == 200, r.text

c1 = TestClient(server.app)
c2 = TestClient(server.app)
signup(c1, "u1@x.com")
signup(c2, "u2@x.com")

# --- 每用户在飞 1：u1 提交 A(queued) 后提交 B → 409 ---
r = c1.post("/api/generate", json={"url": "https://a/v", "quality": "360p"})
check(r.status_code == 200, f"u1 提交 A 200 -> {r.status_code}")
jidA = r.json()["job_id"]
r = c1.post("/api/generate", json={"url": "https://b/v", "quality": "360p"})
check(r.status_code == 409, f"u1 在飞时第二单 409 -> {r.status_code}")

run_burst()  # 处理 A

# --- u1 历史/私有库 ---
hist = c1.get("/api/history").json()
check(len(hist) == 1 and hist[0]["status"] == "done", f"u1 历史 1 条 done -> {hist}")
noteid = hist[0]["note_id"]
mine = c1.get("/api/notes/mine").json()
check(len(mine) == 1 and mine[0]["id"] == noteid, "u1 私有库 1 条")

# --- u2 看不到 u1 的私有 ---
check(c2.get("/api/notes/mine").json() == [], "u2 私有库为空")
check(c2.get("/api/history").json() == [], "u2 历史为空")

# --- 私有文件：owner 200 / 非 owner 404 / 匿名 404 ---
r = c1.get(f"/api/notes/{noteid}/file/summary.json")
check(r.status_code == 200, f"owner 取私有文件 200 -> {r.status_code}")
r = c2.get(f"/api/notes/{noteid}/file/summary.json")
check(r.status_code == 404, f"非 owner 取私有文件 404 -> {r.status_code}")
anon = TestClient(server.app)
r = anon.get(f"/api/notes/{noteid}/file/summary.json")
check(r.status_code == 404, f"匿名取私有文件 404 -> {r.status_code}")
# 路径越级拦截
r = c1.get(f"/api/notes/{noteid}/file/../../../etc/passwd")
check(r.status_code == 404, f"路径越级 404 -> {r.status_code}")

# --- u2 跨用户取 u1 的 job → 404 ---
r = c2.get(f"/api/jobs/{jidA}")
check(r.status_code == 404, f"u2 取 u1 job 404 -> {r.status_code}")
check(c1.get(f"/api/jobs/{jidA}").status_code == 200, "u1 取自己 job 200")

# --- 按用户幂等：u1 同 URL 再提（A 已 done）→ 复用同 job，历史不增 ---
r = c1.post("/api/generate", json={"url": "https://a/v", "quality": "360p"})
check(r.status_code == 200 and r.json()["job_id"] == jidA, "u1 同 URL 命中幂等(同 job)")
check(len(c1.get("/api/history").json()) == 1, "幂等不新增历史行")

# --- 不同用户同 URL → 各自独立 job ---
r = c2.post("/api/generate", json={"url": "https://a/v", "quality": "360p"})
check(r.status_code == 200 and r.json()["job_id"] != jidA, "u2 同 URL 不复用 u1 的 job")
run_burst()
m2 = c2.get("/api/notes/mine").json()
check(len(m2) == 1 and m2[0]["id"] != noteid, "u2 得到独立私有笔记")

# --- 公开展示区匿名可读（此处空，断结构）---
check(anon.get("/api/notes/public").status_code == 200, "匿名可读公开展示区")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ==="); sys.exit(1)
print("=== ALL CHECKS PASSED ===")
```

- [ ] **Step 2: 运行确认通过**

Run: `PYTHONIOENCODING=utf-8 E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/test_multiuser_integration.py`
Expected: PASS（全部）。若失败，按断言定位（常见：cookie jar 未隔离 → 用独立 TestClient 实例；fakeredis 未在 import server 后仍生效 → set_connections 在 enqueue 前调用即可）。

- [ ] **Step 3: 提交**

```bash
git add scripts/test_multiuser_integration.py
git commit -m "test: 多用户端到端集成(隔离/404/在飞1/按用户幂等/私有文件)"
```

---

### Task 12: 公开笔记迁移/seed admin 脚本（`scripts/migrate_seed_public_notes.py`）

幂等：建 seed admin 用户 + 把 `web/public/notes/` 既有目录登记为公开笔记（`visibility='public', owner_id=admin`）。可重跑。

**Files:**
- Create: `scripts/migrate_seed_public_notes.py`
- Test: `scripts/test_migrate_seed.py`

- [ ] **Step 1: 写失败测试 `scripts/test_migrate_seed.py`**

```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `PYTHONIOENCODING=utf-8 E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/test_migrate_seed.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'migrate_seed_public_notes'`

- [ ] **Step 3: 实现 `scripts/migrate_seed_public_notes.py`**

```python
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
```

- [ ] **Step 4: 运行确认通过**

Run: `PYTHONIOENCODING=utf-8 E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/test_migrate_seed.py`
Expected: PASS（全部）

- [ ] **Step 5: 提交**

```bash
git add scripts/migrate_seed_public_notes.py scripts/test_migrate_seed.py
git commit -m "feat(migrate): seed admin + 既有公开笔记登记(幂等)"
```

---

### Task 13: 全量测试回归 + 真实迁移 + 手动 e2e

无新代码，验证整套后端在真实 Redis/SQLite 上自洽。

- [ ] **Step 1: 跑全部 assert 脚本（应全绿）**

Run（逐个，任一非零退出即停下排查）：
```
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_db_schema.py
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_accounts_unit.py
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_userdata_unit.py
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_idempotency_user.py
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_authdeps_unit.py
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_publish_private.py
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_worker_user_mirror.py
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_auth_api.py
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_endpoints_authz.py
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_multiuser_integration.py
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_migrate_seed.py
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_worker_integration.py
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_quality_format.py
```
Expected: 每个都 `=== ALL CHECKS PASSED ===`。

- [ ] **Step 2: 对真实库跑迁移（生成 data/notegen.db + 登记现有公开笔记）**

Run: `E:/claudeproject/notegen/.venv/Scripts/python.exe scripts/migrate_seed_public_notes.py`
Expected: `[migrate] admin=admin@notegen.local 公开笔记登记 N 条`（N = web/public/notes 现有目录数）。

- [ ] **Step 3: 手动 e2e（四组件原生起，见 service-native-redis 记忆的顺序）**

1. 起 Redis：`E:\claudeproject\redis\redis-server.exe`（已在跑则跳过）。
2. 起 worker：`.venv\Scripts\python.exe scripts\run_worker.py`。
3. 起 api：`.venv\Scripts\python.exe server.py`（`/api/health` 返回 `{ok:true}`）。
4. 用 `curl`/REST 客户端走一遍（web 前端在后续前端计划接）：
   - 注册两个账号 → 看 api 控制台两条 `[VERIFY] ...` → 各 GET verify。
   - 各登录拿 cookie → 各 `POST /api/generate {url, quality:"360p"}`（短视频省时）。
   - worker 串行处理 → `GET /api/history` 各见自己 1 条 done；`GET /api/notes/mine` 各见自己 1 条。
   - 拿 A 账号的 note id，用 B 账号 cookie 请求 `/api/notes/{id}/file/summary.json` → 404；A 自己 → 200。
   - `GET /api/notes/public`（匿名）→ 见迁移登记的公开笔记。
   - A 在飞时再提一单 → 409。

Expected: 全部符合预期；并发=1（worker 串行）；私有/公开隔离正确。

- [ ] **Step 4: 提交（若 e2e 中发现并修了小问题）**

```bash
git add -A
git commit -m "chore: 子项目#2 后端回归 + 真实迁移验证"
```

> e2e 是手动验证，若纯绿无改动则跳过本提交。

---

## Self-Review（计划完成后的对照检查，已执行）

**1. Spec 覆盖：**
- 鉴权（注册/验证/登录/登出/me、bcrypt、服务端会话、防枚举）→ Task 2/3/6/9 ✓
- SQLite 五表 WAL → Task 1 ✓；笔记归属/历史仓储 → Task 4 ✓
- 私有发布 `data/user_notes/{uid}/{id}/` + 视频 video.mp4 → Task 7/8 ✓
- 私有文件鉴权托管（owner 404、Range、越级拦截）→ Task 10（FileResponse 自带 Range）✓
- API 变更（generate/upload require_user、jobs 归属、notes public/mine、history、retry、DELETE 归属）→ Task 10 ✓
- 幂等加 user_id → Task 5 ✓；每用户在飞 1 → Task 10/11 ✓
- 迁移 seed admin + 公开登记（幂等）→ Task 12 ✓
- 并发=1 铁律不变（单 worker）→ 未触碰队列并发，Task 8 仅加镜像 ✓

**2. Placeholder 扫描：** 无 TBD/TODO；每个代码步给完整代码。

**3. 类型/签名一致性：** `db.set_db_path/connect/init_db`、`accounts.*`、`notes_repo/jobs_repo` 方法名在 Task 4 定义后于 Task 8/10/11/12 一致引用；`SC.publish_private(stem,uid)->(note_id,storage_path,fields)` 在 Task 7 定义、Task 8/11 一致使用；`authdeps.SESSION_COOKIE/current_user/require_user` Task 6 定义、Task 9/10 引用一致。

**4. 已知边界/前提：** 测试用 `db.set_db_path` + `NOTEGEN_DB_PATH`；server import 时 `db.init_db()`，故测试须在 import server 前设好 db 路径与 fakeredis；worker 与 api 同进程跑集成测试共享 fakeredis server 与临时 DB。

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-07-notegen-multiuser-accounts-backend.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — 每个 Task 派新 subagent 实现，任务间我做两段式复核，迭代快、主上下文干净。

**2. Inline Execution** — 在本会话内逐 Task 执行（executing-plans），批量推进 + 检查点复核。

**先决一件事：实现分支。** 建议基于 `feature/service-hardening` 新建 `feature/multiuser-accounts`（#1 尚未合 main）——这是你的决定，定了我再开工。

**Which approach, and which branch?**
