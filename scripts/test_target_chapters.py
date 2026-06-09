"""Offline pure-function test for given-K target_chapters resolution.
No GPU / no model load (imports segment_llm, runs autoawq shim only).
Run: .venv/Scripts/python.exe scripts/test_target_chapters.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import segment_llm as S  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

CAP = S.CAP_TEACHING  # 5

# --- free-K 不变：短视频 n<=10 -> hint "[3, 6]" ---
mn, mx, hint = S._resolve_top_count(8, CAP, None)
check(hint == "[3, 6]", f"(4a) free-K 短视频 hint -> {hint!r}")

# --- free-K 不变：长视频 n=31 cap=5 -> ceil(31/5)=7, max=9 ---
mn, mx, hint = S._resolve_top_count(31, 5, None)
check(mn == 7 and mx == 9, f"(4b) free-K 长视频 算术区间 -> {(mn, mx)}")
check("7, 9" in hint, f"(4c) free-K 长视频 hint 含区间 -> {hint!r}")

# --- given-K：target 钉死 K，min==max==target，hint 含「正好 N」---
mn, mx, hint = S._resolve_top_count(31, 5, 7)
check(mn == 7 and mx == 7, f"(4d) given-K min==max==7 -> {(mn, mx)}")
check("正好 7" in hint, f"(4e) given-K hint 含 正好 7 -> {hint!r}")

# --- given-K 对短视频同样覆盖（target 优先于 [3,6]）---
mn, mx, hint = S._resolve_top_count(8, 5, 4)
check(mn == 4 and mx == 4 and "正好 4" in hint, f"(4f) given-K 短视频 -> {(mn, mx, hint)}")

# --- target<=0 视为未设（防御）---
mn, mx, hint = S._resolve_top_count(8, 5, 0)
check(hint == "[3, 6]", f"(4g) target=0 当作 free-K -> {hint!r}")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ===")
    sys.exit(1)
print("=== ALL CHECKS PASSED ===")
