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
