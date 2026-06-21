"""内存滑动窗口限速器（ROADMAP 阶段 B #7）。零新依赖，单进程内存态——
与单 API 进程的部署形态匹配；进程重启即清零，可接受（限速不是审计）。

用法（server.py）：
    LOGIN_LIMITER = SlidingWindowLimiter.from_env("NOTEGEN_LOGIN_LIMIT", "10/60")
    if not LOGIN_LIMITER.allow(ip): raise HTTPException(429, ...)
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from typing import Callable


class SlidingWindowLimiter:
    """每 key（通常是客户端 IP）在 window_sec 滑动窗口内最多 max_hits 次。"""

    def __init__(self, max_hits: int, window_sec: float,
                 clock: Callable[[], float] = time.monotonic):
        if max_hits < 1 or window_sec <= 0:
            raise ValueError("max_hits >= 1 and window_sec > 0 required")
        self.max_hits = max_hits
        self.window_sec = window_sec
        self._clock = clock
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls, env_name: str, default: str) -> "SlidingWindowLimiter":
        """解析 'N/秒' 形式（如 '10/60'）。解析失败回落 default。"""
        raw = os.environ.get(env_name, default)
        try:
            n, w = raw.split("/")
            return cls(int(n), float(w))
        except (ValueError, AttributeError):
            n, w = default.split("/")
            return cls(int(n), float(w))

    def _prune(self, dq: deque, now: float) -> None:
        edge = now - self.window_sec
        while dq and dq[0] <= edge:
            dq.popleft()

    def allow(self, key: str) -> bool:
        """记一次命中并返回是否放行。超限时不记录（拒绝的请求不占窗口）。"""
        now = self._clock()
        with self._lock:
            dq = self._hits[key]
            self._prune(dq, now)
            if len(dq) >= self.max_hits:
                return False
            dq.append(now)
            return True

    def retry_after(self, key: str) -> int:
        """还要等多少秒才有空位（给 Retry-After 头），向上取整，至少 1。"""
        now = self._clock()
        with self._lock:
            dq = self._hits[key]
            self._prune(dq, now)
            if len(dq) < self.max_hits:
                return 0
            wait = dq[0] + self.window_sec - now
            return max(1, int(wait) + (0 if wait == int(wait) else 1))

    def reset(self, key: str | None = None) -> None:
        """测试用：清掉某个 key 或全部。"""
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)
