"""Offline pure-function test for src/seg_eval.py segmentation metrics.
No GPU / no IO. Run: .venv/Scripts/python.exe scripts/test_seg_eval.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import seg_eval as E  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

def approx(a, b, eps=1e-6):
    return abs(a - b) < eps

# --- boundary_prf: 完美命中 ---
r = E.boundary_prf([100.0, 200.0, 300.0], [100.0, 200.0, 300.0], tol=15.0)
check(r["tp"] == 3 and r["fp"] == 0 and r["fn"] == 0, f"(1a) 完美 tp/fp/fn -> {r}")
check(approx(r["F1"], 1.0), f"(1a) 完美 F1=1.0 -> {r['F1']}")

# --- 部分命中 + 容差边界 ---
# gold 200 的最近 pred 是 212（差 12 ≤15 命中）；gold 300 无 pred 在 ±15 内 -> fn
r = E.boundary_prf([100.0, 212.0, 500.0], [100.0, 200.0, 300.0], tol=15.0)
check(r["tp"] == 2 and r["fn"] == 1, f"(1b) 部分命中 tp=2 fn=1 -> {r}")
check(r["fp"] == 1, f"(1b) pred 500 无配 -> fp=1 -> {r}")

# --- 容差刚好边界：差恰好 = tol 命中，> tol 不命中 ---
check(E.boundary_prf([115.0], [100.0], tol=15.0)["tp"] == 1, "(1c) 差=tol 命中")
check(E.boundary_prf([116.0], [100.0], tol=15.0)["tp"] == 0, "(1c) 差>tol 不命中")

# --- nearest-greedy 反例：grab-nearest 会少算，earliest-compatible 双指针配满 ---
# gold=[10,12] pred=[11,13] tol=2：双指针 10<-11, 12<-13 => tp=2
r = E.boundary_prf([11.0, 13.0], [10.0, 12.0], tol=2.0)
check(r["tp"] == 2, f"(1d) 双指针配满 tp=2（nearest-greedy 会得 1）-> {r}")

# --- 退化：双空 -> F1=1.0 ---
r = E.boundary_prf([], [], tol=15.0)
check(approx(r["F1"], 1.0) and r["tp"] == 0, f"(1e) 双空 F1=1.0 -> {r}")
# --- 退化：仅 pred 空 -> F1=0.0 ---
r = E.boundary_prf([], [100.0], tol=15.0)
check(approx(r["F1"], 0.0) and r["fn"] == 1, f"(1f) pred 空 F1=0.0 -> {r}")
# --- 退化：仅 gold 空 -> F1=0.0 ---
r = E.boundary_prf([100.0], [], tol=15.0)
check(approx(r["F1"], 0.0) and r["fp"] == 1, f"(1g) gold 空 F1=0.0 -> {r}")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ===")
    sys.exit(1)
print("=== ALL CHECKS PASSED ===")
