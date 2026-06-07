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
