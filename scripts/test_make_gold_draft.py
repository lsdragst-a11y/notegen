"""Offline test for make_gold_draft.build_gold_draft pure assembly.
Run: .venv/Scripts/python.exe scripts/test_make_gold_draft.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import make_gold_draft as M  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

d = M.build_gold_draft(
    video_id="BVX_p0", local_source="data/raw/BVX_p0.mp4", duration=2705.0,
    domain="learning", label="王道计组",
    boundaries=[364.9, 773.0, 1190.8], draft_source="llm:vl.chapters")
check(d["video_id"] == "BVX_p0", "(5a) video_id")
check(d["boundaries_sec"] == [364.9, 773.0, 1190.8], "(5b) boundaries 升序保留")
check(d["n_segments"] == 4, f"(5c) n_segments == len+1 -> {d['n_segments']}")
check(d["annotated_by"] == "draft", "(5d) 草稿标记")
check(d["schema_version"] == 1, "(5e) schema_version")
# 边界乱序输入 -> 自动排序
d2 = M.build_gold_draft("v", "s.mp4", 100.0, "vlog", "x", [50.0, 10.0], "llm")
check(d2["boundaries_sec"] == [10.0, 50.0], "(5f) 边界自动升序")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ===")
    sys.exit(1)
print("=== ALL CHECKS PASSED ===")
