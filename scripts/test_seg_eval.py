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

# --- Pk / WindowDiff: 完美切分 = 0 ---
g = [100.0, 200.0]
check(approx(E.pk(g, g, duration=300.0), 0.0), "(2a) Pk 完美=0")
check(approx(E.windowdiff(g, g, duration=300.0), 0.0), "(2b) WD 完美=0")

# --- 退化：双空 -> 0.0（两个单段 mask 一致） ---
check(approx(E.pk([], [], duration=300.0), 0.0), "(2c) Pk 双空=0")
check(approx(E.windowdiff([], [], duration=300.0), 0.0), "(2d) WD 双空=0")

# --- gold 单段、pred 有边界：稳定返回（k 钳到 >=1），不抛异常，且 > 0 ---
v = E.pk([150.0], [], duration=300.0)
check(0.0 <= v <= 1.0, f"(2e) Pk gold单段稳定 -> {v}")
v = E.windowdiff([150.0], [], duration=300.0)
check(0.0 <= v <= 1.0, f"(2f) WD gold单段稳定 -> {v}")

# --- near-miss 惩罚 < 全错 ---
gold = [100.0, 200.0]
near = E.pk([105.0, 205.0], gold, duration=300.0)   # 边界各偏 5s
allwrong = E.pk([10.0, 290.0], gold, duration=300.0)  # 边界放两端
check(near < allwrong, f"(2g) Pk near-miss({near}) < 全错({allwrong})")

# --- 手算 toy：n=10, k=1, gold=[5], pred=[3]（after-semantics: b 写到 mask[floor(b)-1]）---
# duration=10 -> n=10。用 k=1 显式核对：windowdiff(pred,gold,duration,k=1)
# mask_gold[4]=1(u=5->4)，mask_pred[2]=1(u=3->2)，其余 0。窗口宽 1，range(10-1+1)=range(10)。
# 仅 i=2（pred 有、gold 无）与 i=4（gold 有、pred 无）Δ=1 -> wd=2/10=0.2
check(approx(E.windowdiff([3.0], [5.0], duration=10.0, k=1), 0.2),
      f"(2h) WD 手算 k=1 = 0.2 -> {E.windowdiff([3.0],[5.0],10.0,1)}")
# pk k=1：窗口宽 1，每个单元自身有/无边界。i=2 ref无hyp有, i=4 ref有hyp无 -> err=2/10=0.2
check(approx(E.pk([3.0], [5.0], duration=10.0, k=1), 0.2),
      f"(2i) Pk 手算 k=1 = 0.2 -> {E.pk([3.0],[5.0],10.0,1)}")

# --- window_k 钳位：极短视频 k>=1 ---
check(E.window_k([], duration=1.0) >= 1, "(2j) window_k 钳到 >=1")

# --- extract_pred_boundaries: 去掉首章起点(≈0)，返回内部边界 ---
chapters_obj = {"chapters": [
    {"title": "a", "start": 0.0, "end": 100.0},
    {"title": "b", "start": 100.0, "end": 250.0},
    {"title": "c", "start": 250.0, "end": 400.0},
]}
b = E.extract_pred_boundaries(chapters_obj)
check(b == [100.0, 250.0], f"(3a) 去首章起点 -> {b}")
# 首章 start 略 > 0 但 < eps 仍算起点
chapters_obj2 = {"chapters": [{"title": "a", "start": 0.4, "end": 50.0},
                              {"title": "b", "start": 50.0, "end": 100.0}]}
check(E.extract_pred_boundaries(chapters_obj2) == [50.0], "(3b) start<eps 视为起点")
# 空 / 单章 -> 无内部边界
check(E.extract_pred_boundaries({"chapters": []}) == [], "(3c) 空章 -> []")
check(E.extract_pred_boundaries({"chapters": [{"start": 0.0, "end": 10.0}]}) == [],
      "(3d) 单章 -> []")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ===")
    sys.exit(1)
print("=== ALL CHECKS PASSED ===")
