"""ratelimit.SlidingWindowLimiter 断言：窗口内放行/拒绝、滑动过期、
retry_after、key 隔离、from_env 解析。纯 stdlib，注入假时钟。
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_ratelimit_unit.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ratelimit import SlidingWindowLimiter  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)


class Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


clk = Clock()
lim = SlidingWindowLimiter(3, 60, clock=clk)

check(lim.allow("ip1") and lim.allow("ip1") and lim.allow("ip1"), "窗口内前 3 次放行")
check(not lim.allow("ip1"), "第 4 次拒绝")
check(lim.allow("ip2"), "不同 key 互不影响")
check(lim.retry_after("ip1") == 60, f"retry_after = 窗口剩余（{lim.retry_after('ip1')}）")

clk.t += 30
check(not lim.allow("ip1"), "30s 后仍满（窗口 60s）")
check(lim.retry_after("ip1") == 30, "retry_after 随时间递减")

clk.t += 31   # 首条命中过期
check(lim.allow("ip1"), "61s 后最早命中滑出窗口 → 放行")
check(lim.retry_after("ip1") == 0, "未满时 retry_after=0")

# 拒绝的请求不占窗口：连拒 10 次后窗口滑过仍按 3 个名额恢复
lim2 = SlidingWindowLimiter(3, 10, clock=clk)
for _ in range(3): lim2.allow("k")
for _ in range(10): lim2.allow("k")
clk.t += 11
ok = sum(1 for _ in range(3) if lim2.allow("k"))
check(ok == 3, f"被拒请求不占窗口，过期后恢复满额（{ok}/3）")

# reset
lim2.reset("k")
check(lim2.allow("k"), "reset(key) 后立即放行")

# from_env
os.environ["X_TEST_LIMIT"] = "5/30"
l3 = SlidingWindowLimiter.from_env("X_TEST_LIMIT", "10/60")
check(l3.max_hits == 5 and l3.window_sec == 30.0, "from_env 解析 '5/30'")
os.environ["X_TEST_LIMIT"] = "garbage"
l4 = SlidingWindowLimiter.from_env("X_TEST_LIMIT", "10/60")
check(l4.max_hits == 10 and l4.window_sec == 60.0, "非法值回落 default")
del os.environ["X_TEST_LIMIT"]

try:
    SlidingWindowLimiter(0, 60)
    check(False, "max_hits=0 应抛 ValueError")
except ValueError:
    check(True, "max_hits=0 抛 ValueError")

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("ALL PASS")
