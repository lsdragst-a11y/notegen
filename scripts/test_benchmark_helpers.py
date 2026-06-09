"""Offline test for benchmark_segmentation pure helpers (no subprocess).
Run: .venv/Scripts/python.exe scripts/test_benchmark_helpers.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import benchmark_segmentation as B  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

row = B.assemble_row(
    video_id="v1", domain="learning", condition="free-K", chunk_chars=800,
    pred=[110.0, 320.0], gold=[100.0, 200.0, 300.0], duration=400.0)
check(row["pred_n_segments"] == 3, f"(7a) pred_n_segments=len(pred)+1 -> {row['pred_n_segments']}")
check(row["gold_n_segments"] == 4, f"(7b) gold_n_segments=len(gold)+1 -> {row['gold_n_segments']}")
check(row["k_error"] == 3 - 4, f"(7c) k_error 带符号 -> {row['k_error']}")
check("tol15" in row and "tol30" in row and "pk" in row and "windowdiff" in row,
      "(7d) 指标字段齐全")
check(row["tol15"]["tp"] >= 1, f"(7e) tol15 命中 -> {row['tol15']}")
check(row["pipeline_failed"] is False, "(7e2) pipeline_failed 默认 False")

# 失败/空 pred 路径：pipeline 挂了应能干净组行，pipeline_failed 透传，F1=0（非崩溃）
frow = B.assemble_row(
    video_id="v2", domain="learning", condition="given-K", chunk_chars=600,
    pred=[], gold=[100.0, 200.0], duration=300.0, pipeline_failed=True)
check(frow["pipeline_failed"] is True, "(7h) pipeline_failed 透传")
check(frow["pred_n_segments"] == 1 and frow["tol15"]["F1"] == 0.0,
      f"(7i) 空 pred -> n=1, F1=0 -> {frow['pred_n_segments']}, {frow['tol15']}")

# aggregate：按 domain×condition 求 F1@15 均值
rows = [
    {"domain": "learning", "condition": "free-K", "tol15": {"F1": 0.8},
     "tol30": {"F1": 0.9}, "pk": 0.2, "windowdiff": 0.25},
    {"domain": "learning", "condition": "free-K", "tol15": {"F1": 0.6},
     "tol30": {"F1": 0.7}, "pk": 0.3, "windowdiff": 0.35},
]
agg = B.aggregate(rows)
check(abs(agg[("learning", "free-K")]["F1@15"] - 0.7) < 1e-6,
      f"(7f) 均值 F1@15=0.7 -> {agg[('learning','free-K')]['F1@15']}")
check(agg[("learning", "free-K")]["n"] == 2, "(7g) 计数=2")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ===")
    sys.exit(1)
print("=== ALL CHECKS PASSED ===")
