"""结构化日志（ROADMAP 阶段 B #5）。loguru：stderr + logs/<name>.log 轮转。
loguru 未安装时回落 stdlib logging 同签名 shim——保证「先拉代码后 pip install」
的窗口期 server/worker 也起得来，CI 不装 loguru 也能跑。

用法：
    from logging_setup import setup_logging
    log = setup_logging("server")          # 写 logs/server.log
    log.info("...")  log.warning("...")  log.error("...")
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = ROOT / "logs"

_LEVEL = os.environ.get("NOTEGEN_LOG_LEVEL", "INFO").upper()


def setup_logging(name: str):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        from loguru import logger
    except ImportError:
        return _stdlib_fallback(name)
    logger.remove()
    fmt = ("<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <7}</level> | "
           f"{name} | {{message}}")
    logger.add(sys.stderr, level=_LEVEL, format=fmt, colorize=True)
    logger.add(
        LOGS_DIR / f"{name}.log",
        level=_LEVEL,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | " + name + " | {message}",
        rotation="10 MB",
        retention=10,          # 保留 10 个轮转文件
        encoding="utf-8",
        enqueue=True,          # 线程/子进程安全
    )
    return logger


def _stdlib_fallback(name: str):
    import logging
    from logging.handlers import RotatingFileHandler
    lg = logging.getLogger(f"notegen.{name}")
    if lg.handlers:           # 幂等：重复 setup 不叠 handler
        return lg
    lg.setLevel(_LEVEL)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | " + name + " | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    fh = RotatingFileHandler(LOGS_DIR / f"{name}.log", maxBytes=10 * 1024 * 1024,
                             backupCount=10, encoding="utf-8")
    fh.setFormatter(fmt)
    lg.addHandler(sh)
    lg.addHandler(fh)
    return lg
