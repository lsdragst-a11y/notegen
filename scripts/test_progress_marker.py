"""Pure-function test：[PROGRESS] marker 的 emit 格式 + parse + 带内插值。
无 GPU / 无 Redis。Run: .venv/Scripts/python.exe scripts/test_progress_marker.py"""
import io
import sys
import os
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import progress as P  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

# (a) emit 打印一行可被 parse 还原
buf = io.StringIO()
with redirect_stdout(buf):
    P.emit_progress("asr", "语音识别", 4, 18)
line = buf.getvalue().strip()
check(line.startswith("[PROGRESS] "), f"(a) emit 前缀 -> {line!r}")
parsed = P.parse_progress_marker(line)
check(parsed == {"stage": "asr", "label": "语音识别", "i": 4, "n": 18},
      f"(a) parse 还原 -> {parsed!r}")

# (b) 非 marker 行 parse 返回 None
check(P.parse_progress_marker("[asr] 12.0s / 100.0s") is None, "(b) 普通行 -> None")
check(P.parse_progress_marker("") is None, "(b) 空行 -> None")
check(P.parse_progress_marker("[PROGRESS] not-json") is None, "(b) 坏 json -> None")

# (c) stage 百分比带：i/n 映射到 [lo, hi]
lo, hi = P.stage_band(4, 18)
check(lo == round(3 / 18 * 100) and hi == round(4 / 18 * 100),
      f"(c) band(4,18) -> {(lo, hi)}")
check(P.stage_band(18, 18) == (round(17 / 18 * 100), 100), "(c) 末 stage hi=100")

# (d) 带内插值
check(P.interpolate(20, 60, 0.0) == 20, "(d) frac=0 -> lo")
check(P.interpolate(20, 60, 1.0) == 60, "(d) frac=1 -> hi")
check(P.interpolate(20, 60, 0.5) == 40, "(d) frac=0.5 -> 中点")
check(P.interpolate(20, 60, 2.0) == 60, "(d) frac>1 截到 hi")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ===")
    sys.exit(1)
print("=== ALL CHECKS PASSED ===")
