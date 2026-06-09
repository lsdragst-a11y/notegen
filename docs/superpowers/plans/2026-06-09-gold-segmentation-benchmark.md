# 30 视频 Gold 切分基准 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立一个标准化、冻结、可复现的 30 视频 gold 切分基准，量化当前 LLM 章节切分路径在人工 gold 上的边界准确度，并作为 roadmap #4（混合切分）的对比标尺与 #5 白皮书的数据来源。

**Architecture:** 纯函数指标库 `src/seg_eval.py`（无 IO，可被 #4 直接复用）+ 冻结的 `data/gold/manifest.json` 与每视频 `*.gold.json`（时间制边界）+ 半自动草稿脚本 `scripts/make_gold_draft.py` + 跑批脚本 `scripts/benchmark_segmentation.py`（free-K + given-K 两条件，对齐 web worker 的生产 pipeline 参数）。给 `segment_hierarchical` 加可选 `target_chapters` 使 given-K 真正约束 LLM 章数。

**Tech Stack:** Python 3（stdlib `math`/`json`/`subprocess`），现有 `src/pipeline.py` / `src/segment_llm.py` / `src/service_common.py`；测试用仓库惯例的 `__main__` 断言脚本（非 pytest），跑 `.venv/Scripts/python.exe scripts/test_*.py`。**nltk 未安装**——Pk/WindowDiff 走 vendored 实现，对齐 nltk 的标准算法并以手算单测钉死 off-by-one。

**给 reviewer 的待决项（given-K 深度，见 Task 4）：** 本计划对 given-K 采用 **Option A（软约束）**——`target_chapters` 仅作 prompt 层强提示（把顶层数 hint 钉成「正好 N」），**不**改 `_diagnose_outline` / `_validate_outline`（这两个校验函数各自重算 `_cap_for_category` 上限，内含 p57/BV1q6/NAT 等历史修复，硬改风险高）。残留章数滑移由输出的 `k_error` 量化。备选 **Option B（硬约束）** 会进一步改校验器强制恰好 K 章，但触碰生产 fallback 逻辑、风险大。given-K 是「oracle 参考」非主指标，故选低风险 Option A。**若 reviewer 要 Option B，在执行 Task 4 前提出。**

---

## File Structure

| 文件 | 职责 | 动作 |
|---|---|---|
| `src/seg_eval.py` | 纯函数指标库：boundary 匹配 + P/R/F1@tol、Pk、WindowDiff、pred 边界提取。无 IO。 | 新建 |
| `scripts/test_seg_eval.py` | 指标库单测（手算核对 + 退化情形 + nearest-greedy 反例）。 | 新建 |
| `src/segment_llm.py` | 加 `target_chapters` 参数 + 抽出纯函数 `_resolve_top_count`。free-K 行为不变。 | 改 |
| `scripts/test_target_chapters.py` | `_resolve_top_count` 纯函数单测（free-K 不变 / given-K 钉死 K）。 | 新建 |
| `src/pipeline.py` | `_do_llm_chapters` 把 `cfg.chapters>0` 透传为 `target_chapters`。 | 改 |
| `scripts/make_gold_draft.py` | 半自动：扫候选 → LLM chapters.json 出 silver 草稿 gold + 带时间戳转写 + manifest 候选/缺口报告。 | 新建 |
| `data/gold/manifest.json` | 冻结的 30 视频清单（权威集合）。 | 人工生成（Task 6） |
| `data/gold/<video_id>.gold.json` | 每视频人工校正 gold。 | 人工生成（Task 6） |
| `scripts/benchmark_segmentation.py` | 跑批：读 manifest → free-K + given-K 跑 pipeline → seg_eval → JSON + 报表。 | 新建 |
| `paper/segmentation_benchmark.md` | 分档均值报表，供白皮书引用。 | benchmark 生成（Task 7） |
| `scripts/eval_segmentation.py` | 旧 TextTiling 评估，标 legacy，**不删不改逻辑**。 | 仅加注释 |

---

## Task 1: `seg_eval.py` — Boundary 匹配 + P/R/F1@tolerance

**Files:**
- Create: `E:\claudeproject\notegen\src\seg_eval.py`
- Test: `E:\claudeproject\notegen\scripts\test_seg_eval.py`

- [ ] **Step 1: Write the failing test**

Create `scripts/test_seg_eval.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe scripts/test_seg_eval.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'seg_eval'`

- [ ] **Step 3: Write minimal implementation**

Create `src/seg_eval.py`:

```python
"""纯函数切分指标库（无 IO / 无 GPU）。输入输出皆为「秒为单位边界 list + 视频时长」。
roadmap #4 混合切分系统可直接 import 复用。
- boundary_prf: 边界 P/R/F1，±tolerance 容差，earliest-compatible 双指针最大一对一匹配。
- pk / windowdiff: 1s 单元离散后按 nltk 标准算法 vendored 实现（本机无 nltk）。
metrics_version = 1
"""
from __future__ import annotations

import math
from typing import Optional

METRICS_VERSION = 1


def match_boundaries(pred: list[float], gold: list[float], tol: float) -> tuple[int, int, int]:
    """earliest-compatible 双指针，返回 (tp, fp, fn)。
    pred/gold 各自升序，对一维点集 + 对称容差窗口该匹配 = 最大二分匹配。
    禁止 nearest-greedy（边界密集时少算 TP）。"""
    p = sorted(pred)
    g = sorted(gold)
    i = j = tp = 0
    while i < len(g) and j < len(p):
        if p[j] < g[i] - tol:
            j += 1                      # 该 pred 配不上任何后续 gold（gold 递增），丢弃
        elif p[j] <= g[i] + tol:
            tp += 1; i += 1; j += 1     # 命中
        else:
            i += 1                      # 该 gold 无 pred 可配
    fp = len(p) - tp
    fn = len(g) - tp
    return tp, fp, fn


def boundary_prf(pred: list[float], gold: list[float], tol: float) -> dict:
    """边界 P/R/F1@tol。退化：双空 -> F1=1.0；仅一边空 -> F1=0.0。"""
    if not pred and not gold:
        return {"tp": 0, "fp": 0, "fn": 0, "P": 1.0, "R": 1.0, "F1": 1.0}
    tp, fp, fn = match_boundaries(pred, gold, tol)
    P = tp / len(pred) if pred else 0.0
    R = tp / len(gold) if gold else 0.0
    F1 = (2 * P * R / (P + R)) if (P + R) > 0 else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "P": P, "R": R, "F1": F1}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe scripts/test_seg_eval.py`
Expected: `=== ALL CHECKS PASSED ===`

- [ ] **Step 5: Commit**

```bash
git add src/seg_eval.py scripts/test_seg_eval.py
git commit -m "feat(seg_eval): boundary P/R/F1@tol with earliest-compatible matching"
```

---

## Task 2: `seg_eval.py` — Pk + WindowDiff（vendored，对齐 nltk）

**Files:**
- Modify: `E:\claudeproject\notegen\src\seg_eval.py`
- Test: `E:\claudeproject\notegen\scripts\test_seg_eval.py:<append>`

> **离散规则（写死，保证可复现）**：`n = max(1, ceil(duration))`，1s 单元 `0..n-1`。边界 `b`：先丢弃 `b<=0` 或 `b>=duration`，再 `u = floor(b)`，保留 `1 <= u < n`（同单元多边界去重）。窗口 `k = max(1, round(n / (len(gold)+1) / 2))`（按 gold 平均段长算，pred/gold 共用），算出后 clamp 到 `[1, n]`；单段 gold 也走同一公式、不特殊钳到 1。滑窗按 **nltk 标准** `range(n - k + 1)`（**修正 spec 草稿里 `i=0..n-k-1` 的 off-by-one——采用 nltk 规范以保证可引用性，已在 Task 7 报表注明**）。WindowDiff 用 `min(1, |Δcount|)`（unweighted）；Pk 比较窗口内「是否有边界」的异同。

- [ ] **Step 1: Write the failing test (append to `scripts/test_seg_eval.py`)**

在 `print()` 收尾块**之前**插入：

```python
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

# --- 手算 toy：n=10, k=1, gold=[5], pred=[3] ---
# duration=10 -> n=10。k = max(1, round(10/2/2)) = round(2.5)=2。
# 用 k=1 显式核对：windowdiff(pred,gold,duration,k=1)
# mask_gold[5]=1，mask_pred[3]=1，其余 0。窗口宽 1，range(10-1+1)=range(10)。
# 仅 i=3（pred 有、gold 无）与 i=5（gold 有、pred 无）Δ=1 -> wd=2/10=0.2
check(approx(E.windowdiff([3.0], [5.0], duration=10.0, k=1), 0.2),
      f"(2h) WD 手算 k=1 = 0.2 -> {E.windowdiff([3.0],[5.0],10.0,1)}")
# pk k=1：窗口宽 1，每个单元自身有/无边界。i=3 ref无hyp有, i=5 ref有hyp无 -> err=2/10=0.2
check(approx(E.pk([3.0], [5.0], duration=10.0, k=1), 0.2),
      f"(2i) Pk 手算 k=1 = 0.2 -> {E.pk([3.0],[5.0],10.0,1)}")

# --- window_k 钳位：极短视频 k>=1 ---
check(E.window_k([], duration=1.0) >= 1, "(2j) window_k 钳到 >=1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe scripts/test_seg_eval.py`
Expected: FAIL — `AttributeError: module 'seg_eval' has no attribute 'pk'`

- [ ] **Step 3: Write minimal implementation (append to `src/seg_eval.py`)**

```python
def _boundaries_to_mask(boundaries: list[float], n: int, duration: float) -> list[int]:
    """长度 n 的 0/1 mask；mask[u]=1 表示单元 u 起始处有内部边界。
    先丢弃 b<=0 或 b>=duration（起点/片尾非内部边界），再 u=floor(b)，保留 1<=u<n。"""
    mask = [0] * n
    for b in boundaries:
        b = float(b)
        if b <= 0.0 or b >= duration:
            continue
        u = int(math.floor(b))
        if 1 <= u < n:
            mask[u] = 1
    return mask


def _n_units(duration: float) -> int:
    return max(1, int(math.ceil(duration)))


def window_k(gold: list[float], duration: float) -> int:
    """k = max(1, round(平均真段长_单元 / 2))；平均段长 = n / (len(gold)+1)。"""
    n = _n_units(duration)
    n_seg = len(gold) + 1
    return max(1, int(round((n / n_seg) / 2.0)))


def windowdiff(pred: list[float], gold: list[float], duration: float,
               k: Optional[int] = None) -> float:
    """nltk 标准 WindowDiff（unweighted: min(1,|Δ|)）。越低越好。"""
    n = _n_units(duration)
    if k is None:
        k = window_k(gold, duration)
    k = max(1, min(k, n))
    ref = _boundaries_to_mask(gold, n, duration)
    hyp = _boundaries_to_mask(pred, n, duration)
    positions = n - k + 1
    if positions <= 0:
        return 0.0
    wd = 0
    for i in range(positions):
        diff = abs(sum(ref[i:i + k]) - sum(hyp[i:i + k]))
        wd += 1 if diff > 0 else 0
    return wd / positions


def pk(pred: list[float], gold: list[float], duration: float,
       k: Optional[int] = None) -> float:
    """nltk 标准 Pk：窗口内「是否有边界」的 ref/hyp 异同计数。越低越好。"""
    n = _n_units(duration)
    if k is None:
        k = window_k(gold, duration)
    k = max(1, min(k, n))
    ref = _boundaries_to_mask(gold, n, duration)
    hyp = _boundaries_to_mask(pred, n, duration)
    positions = n - k + 1
    if positions <= 0:
        return 0.0
    err = 0
    for i in range(positions):
        r = sum(ref[i:i + k]) > 0
        h = sum(hyp[i:i + k]) > 0
        if r != h:
            err += 1
    return err / positions
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe scripts/test_seg_eval.py`
Expected: `=== ALL CHECKS PASSED ===`

- [ ] **Step 5: Commit**

```bash
git add src/seg_eval.py scripts/test_seg_eval.py
git commit -m "feat(seg_eval): vendored Pk/WindowDiff with pinned 1s discretization"
```

---

## Task 3: `seg_eval.py` — `extract_pred_boundaries`（脚本共用的纯提取）

**Files:**
- Modify: `E:\claudeproject\notegen\src\seg_eval.py`
- Test: `E:\claudeproject\notegen\scripts\test_seg_eval.py:<append>`

> pred 边界 = chapters.json 各 chapter 的 `start`（秒），去掉首章起点（`< start_eps`，默认 1.0s），与 gold「不含起点」对齐。

- [ ] **Step 1: Write the failing test (append before `print()` 收尾块)**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe scripts/test_seg_eval.py`
Expected: FAIL — `AttributeError: ... has no attribute 'extract_pred_boundaries'`

- [ ] **Step 3: Write minimal implementation (append to `src/seg_eval.py`)**

```python
def extract_pred_boundaries(chapters_obj: dict, start_eps: float = 1.0) -> list[float]:
    """从 chapters.json 的 dict 取各章 `start` 作为预测边界，去掉首章起点(≈0)。
    返回升序内部边界（秒）。chapters 已按时间排序时直接用；否则排序后取。"""
    chs = chapters_obj.get("chapters") or []
    starts = sorted(float(c.get("start", 0.0)) for c in chs)
    return [s for s in starts if s >= start_eps]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe scripts/test_seg_eval.py`
Expected: `=== ALL CHECKS PASSED ===`

- [ ] **Step 5: Commit**

```bash
git add src/seg_eval.py scripts/test_seg_eval.py
git commit -m "feat(seg_eval): extract_pred_boundaries from chapters.json"
```

---

## Task 4: `target_chapters` 让 given-K 真正约束 LLM（Option A 软约束）

**Files:**
- Modify: `E:\claudeproject\notegen\src\segment_llm.py:1348-1368`（K-hint 计算）+ `:1309-1318`（签名）
- Modify: `E:\claudeproject\notegen\src\pipeline.py:1213-1219`（`_do_llm_chapters` 透传）
- Test: `E:\claudeproject\notegen\scripts\test_target_chapters.py`（新建）

> **Option A**：抽出纯函数 `_resolve_top_count(n, cap, target_chapters)`，target 命中时把顶层数 hint 钉成「正好 N」+ 加硬约束 clause；`target_chapters=None`（free-K / 生产默认）时返回与现有完全一致的 min/max/hint。**不**改 `_diagnose_outline` / `_validate_outline`。残留滑移由 benchmark 的 `k_error` 量化。

- [ ] **Step 1: Write the failing test**

Create `scripts/test_target_chapters.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe scripts/test_target_chapters.py`
Expected: FAIL — `AttributeError: module 'segment_llm' has no attribute '_resolve_top_count'`

- [ ] **Step 3a: Add `_resolve_top_count` helper to `src/segment_llm.py`**

在 `def segment_hierarchical(` 定义（line 1309）**之前**插入：

```python
def _resolve_top_count(n: int, cap: int, target_chapters: Optional[int] = None):
    """决定顶层章数提示 (min_tops, max_tops, hint_str)。
    target_chapters>0 (given-K oracle) 时钉死 K；否则按算术参考给 free-K 区间
    （与历史 free-K 行为完全一致）。纯函数，便于单测。"""
    if target_chapters is not None and target_chapters > 0:
        t = int(target_chapters)
        return t, t, f"正好 {t}（given-K oracle）"
    min_tops = -(-n // cap)                       # ceil division
    max_tops = max(min_tops, min_tops + 2)
    hint = (f"[{min_tops}, {max_tops}]（见上方算术参考）" if n > 10 else "[3, 6]")
    return min_tops, max_tops, hint
```

- [ ] **Step 3b: Add `target_chapters` param to `segment_hierarchical` signature (`src/segment_llm.py:1309-1318`)**

把签名末尾的 `category: str = "teaching",` 那行之后、`) -> Optional[dict]:` 之前加一参数：

```python
def segment_hierarchical(chunks: list[dict],
                          headlines: Optional[list[str]] = None,
                          model_id: str = _DEFAULT_MODEL,
                          max_new_tokens: Optional[int] = None,
                          max_retries: int = 2,
                          visual_sims: Optional[list[float]] = None,
                          visual_captions: Optional[list[Optional[str]]] = None,
                          lang: str = "zh",
                          category: str = "teaching",
                          target_chapters: Optional[int] = None,
                          ) -> Optional[dict]:
```

- [ ] **Step 3c: Replace the K-hint computation block (`src/segment_llm.py:1351-1368`)**

把这段（从 `min_tops_arith = -(-n // chunks_per_top_cap)` 起到 `top_count_hint = (...)` 结束）：

```python
    min_tops_arith = -(-n // chunks_per_top_cap)  # ceil division
    # 上界 = 下界 + 2（给主题更细的视频一点余量）。
    # 旧实现用 min(6, min_tops_arith+2) 把上界钳在 6，但长视频（n>=31, cap=5）
    # 下界已 >=7，会打印出"7-6 / 8-6"这种倒挂区间，反而把 LLM 往"切太少→oversize
    # →程序化拆"的 churn 路径上推。校验函数本就不强制 6 上界，这里取 max 防倒挂。
    max_tops_arith = max(min_tops_arith, min_tops_arith + 2)
    arith_clause = ""
    if n > 10:
        arith_clause = (
            f"\n**算术参考**：{n} 段 / 单顶层 ≤ {chunks_per_top_cap}，"
            f"顶层数典型在 **{min_tops_arith}-{max_tops_arith}** 之间。"
            f"主题更细可超，但每章必须是**连续区间**——宁可少 1 章也不要为凑数跳着选 chunks。\n"
        )
    # 自检清单的顶层数目标：短视频 [3,6]；长视频（n>10）用算术参考区间，
    # 避免写死的 "6 上界" 与上面 arith_clause 矛盾（长视频 6 章塞不下会被逼成
    # 大章 → oversize → 程序化拆，边界反而乱）。
    top_count_hint = (f"[{min_tops_arith}, {max_tops_arith}]（见上方算术参考）"
                      if n > 10 else "[3, 6]")
```

替换为：

```python
    min_tops_arith, max_tops_arith, top_count_hint = _resolve_top_count(
        n, chunks_per_top_cap, target_chapters)
    arith_clause = ""
    if target_chapters is not None and target_chapters > 0:
        # given-K oracle：章数硬提示（仅 benchmark 传；生产默认 None 不进此分支）
        arith_clause = (
            f"\n**章数硬约束（given-K oracle）**：本次必须切成**正好 {int(target_chapters)}** 个"
            f"顶层章节，不多不少。每章仍须是**连续区间**，宁可章内主题略宽也不要改变章数。\n"
        )
    elif n > 10:
        arith_clause = (
            f"\n**算术参考**：{n} 段 / 单顶层 ≤ {chunks_per_top_cap}，"
            f"顶层数典型在 **{min_tops_arith}-{max_tops_arith}** 之间。"
            f"主题更细可超，但每章必须是**连续区间**——宁可少 1 章也不要为凑数跳着选 chunks。\n"
        )
```

> 注：`target_chapters=None` 时 `_resolve_top_count` 返回与原 inline 计算完全相同的 `(min_tops, max_tops, hint)`，且只走 `elif n > 10` 分支 —— **free-K / 生产行为零变化**。`_diagnose_outline` / `_validate_outline` 不动。

- [ ] **Step 3d: Thread `target_chapters` in `pipeline.py` (`src/pipeline.py:1213-1219`)**

把 `_do_llm_chapters` 里的 LLM 调用块：

```python
        print("[chapters] LLM 层级章节切分（Qwen2.5-7B-AWQ）...", flush=True)
        try:
            from segment_llm import segment_hierarchical
            outline = segment_hierarchical(state.summaries,
                                            visual_sims=state.visual_sims_for_llm,
                                            visual_captions=state.visual_captions_for_llm,
                                            lang=state.resolved_lang,
                                            category=state.inferred_category)
```

替换为：

```python
        print("[chapters] LLM 层级章节切分（Qwen2.5-7B-AWQ）...", flush=True)
        # given-K oracle：仅当 --chapters N（N>0）显式给定时约束章数；
        # bare --chapters（const=-1）或 --chapters 缺省走 free-K 自适应（生产默认）。
        _target_k = cfg.chapters if (cfg.chapters is not None and cfg.chapters > 0) else None
        try:
            from segment_llm import segment_hierarchical
            outline = segment_hierarchical(state.summaries,
                                            visual_sims=state.visual_sims_for_llm,
                                            visual_captions=state.visual_captions_for_llm,
                                            lang=state.resolved_lang,
                                            category=state.inferred_category,
                                            target_chapters=_target_k)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe scripts/test_target_chapters.py`
Expected: `=== ALL CHECKS PASSED ===`

回归既有 segment_llm 单测（确认 free-K 行为没破）：
Run: `.venv/Scripts/python.exe scripts/test_repair_overlap.py`
Expected: `=== ALL CHECKS PASSED ===`

- [ ] **Step 5: Commit**

```bash
git add src/segment_llm.py src/pipeline.py scripts/test_target_chapters.py
git commit -m "feat(segment): optional target_chapters for given-K oracle (Option A soft hint)"
```

---

## Task 5: `make_gold_draft.py` — 半自动草稿生成

**Files:**
- Create: `E:\claudeproject\notegen\scripts\make_gold_draft.py`
- Test: `E:\claudeproject\notegen\scripts\test_make_gold_draft.py`（仅测纯函数 `build_gold_draft`）

> 脚本对每个候选视频：读已有 LLM `*.chapters.json` → 抽 silver 边界 → 写 `data/gold/<id>.gold.json` 草稿（`annotated_by="draft"`）+ 旁附**带时间戳的转写 snippet**（取自 `summary.json`，供人工据原文校正而非被草稿锚定）→ 汇总 manifest 候选清单与「凑不满 30」缺口报告。纯函数 `build_gold_draft` 负责组 dict（含 `n_segments == len(boundaries)+1` 不变量），可单测；IO/扫目录在 `main`。

- [ ] **Step 1: Write the failing test**

Create `scripts/test_make_gold_draft.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe scripts/test_make_gold_draft.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'make_gold_draft'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/make_gold_draft.py`:

```python
"""半自动 gold 草稿生成：扫 data/outputs/*.chapters.json，对每个视频出
data/gold/<id>.gold.json 草稿（silver）+ 带时间戳转写 snippet（供人工校正）+
manifest 候选与缺口报告。

人工流程：跑本脚本 -> 编辑各 *.gold.json（据 snippet 与原视频校正 boundaries_sec、
把 annotated_by 改 "human"）-> 据候选填 data/gold/manifest.json（冻结 30 视频）。

Run: .venv/Scripts/python.exe scripts/make_gold_draft.py [--limit N]
"""
from __future__ import annotations

import argparse
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import seg_eval as E  # noqa: E402
from service_common import _guess_domain  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "data" / "outputs"
GOLD_DIR = ROOT / "data" / "gold"

_DOMAIN_MAP = {"编程教学": "learning", "考研专业课": "learning", "学习": "learning",
               "Vlog": "vlog", "数码评测": "vlog"}


def build_gold_draft(video_id: str, local_source: str, duration: float,
                     domain: str, label: str, boundaries: list[float],
                     draft_source: str) -> dict:
    """组装 gold 草稿 dict，保证 n_segments == len(boundaries)+1，boundaries 升序。"""
    b = sorted(float(x) for x in boundaries)
    return {
        "schema_version": 1,
        "video_id": video_id,
        "local_source": local_source,
        "duration": float(duration),
        "domain": domain,
        "label": label,
        "boundaries_sec": b,
        "n_segments": len(b) + 1,
        "annotated_by": "draft",
        "draft_source": draft_source,
        "notes": "",
    }


def _transcript_snippets(stem: str, boundaries: list[float], window: float = 8.0) -> list[dict]:
    """从 summary.json 取每个边界 ±window 秒附近的转写 snippet，辅助人工校正。"""
    sp = OUTPUTS / f"{stem}.summary.json"
    cands = sorted(OUTPUTS.glob(f"{Path(stem).name.split('.')[0]}*.summary.json"))
    if not sp.exists() and cands:
        sp = cands[0]
    if not sp.exists():
        return [{"boundary_sec": b, "near_text": "(no summary.json)"} for b in boundaries]
    try:
        rows = json.loads(sp.read_text(encoding="utf-8"))
    except Exception:
        return [{"boundary_sec": b, "near_text": "(summary parse failed)"} for b in boundaries]
    out = []
    for b in boundaries:
        near = [r.get("summary", r.get("text", ""))[:60]
                for r in rows if abs(float(r.get("start", -1e9)) - b) <= window]
        out.append({"boundary_sec": b, "near_text": " / ".join(near) or "(no nearby chunk)"})
    return out


def _meta_for(stem0: str) -> dict:
    mp = ROOT / "data" / "raw" / f"{stem0}.meta.json"
    if mp.exists():
        try:
            return json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 个候选（0=全部）")
    args = ap.parse_args()

    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    # 每视频取最新（mtime）的一份 chapters.json 作草稿源
    by_video: dict[str, Path] = {}
    for p in sorted(OUTPUTS.glob("*.chapters.json"), key=lambda q: -q.stat().st_mtime):
        stem0 = p.name.split(".")[0]
        by_video.setdefault(stem0, p)

    candidates = []
    items = list(by_video.items())
    if args.limit:
        items = items[: args.limit]
    for stem0, chap_path in items:
        try:
            obj = json.loads(chap_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        boundaries = E.extract_pred_boundaries(obj)
        chs = obj.get("chapters") or []
        duration = float(chs[-1].get("end", 0.0)) if chs else 0.0
        meta = _meta_for(stem0)
        title = meta.get("title", stem0)
        domain = _DOMAIN_MAP.get(_guess_domain(title), "learning")
        # local_source：优先 data/raw 下的 mp4
        src = ""
        for cand in [ROOT / "data" / "raw" / f"{stem0}.mp4",
                     ROOT / "data" / "raw" / f"{stem0}_p0.mp4"]:
            if cand.exists():
                src = str(cand.relative_to(ROOT)).replace("\\", "/")
                break
        draft = build_gold_draft(stem0, src, duration, domain, title,
                                 boundaries, f"llm:{chap_path.name}")
        draft["_draft_snippets"] = _transcript_snippets(chap_path.stem, boundaries)
        out = GOLD_DIR / f"{stem0}.gold.json"
        out.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
        candidates.append({"video_id": stem0, "domain": domain,
                           "gold": f"data/gold/{stem0}.gold.json",
                           "n_segments_draft": draft["n_segments"], "has_source": bool(src)})
        print(f"[draft] {stem0}  domain={domain}  segs={draft['n_segments']}  src={'Y' if src else 'N'}")

    n = len(candidates)
    by_dom: dict[str, int] = {}
    for c in candidates:
        by_dom[c["domain"]] = by_dom.get(c["domain"], 0) + 1
    print(f"\n候选 {n} 个；分档 {by_dom}；目标 30。缺口 {max(0, 30 - n)}。")
    # manifest 候选（人工据此筛选/冻结成 30）
    (GOLD_DIR / "manifest_candidates.json").write_text(
        json.dumps({"schema_version": 1, "candidates": candidates}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"manifest 候选写入 {GOLD_DIR / 'manifest_candidates.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe scripts/test_make_gold_draft.py`
Expected: `=== ALL CHECKS PASSED ===`

烟雾跑（真实扫目录，确认不崩；产物先落 `data/gold/` 草稿）：
Run: `.venv/Scripts/python.exe scripts/make_gold_draft.py --limit 2`
Expected: 打印 2 条 `[draft] ...` + 候选汇总，无异常。

- [ ] **Step 5: Commit**

```bash
git add scripts/make_gold_draft.py scripts/test_make_gold_draft.py
git commit -m "feat(gold): semi-auto gold draft generator from LLM chapters.json"
```

---

## Task 6: 【人工断点】校正 gold + 冻结 manifest（用户动作）

**Files:**
- Edit (人工): `E:\claudeproject\notegen\data\gold\<video_id>.gold.json` × 30
- Create (人工): `E:\claudeproject\notegen\data\gold\manifest.json`

> ⚠️ **这是计划里唯一的人工断点**，无自动化代码。执行到此处需暂停，由用户完成 gold 校正，然后才能跑 Task 7。

- [ ] **Step 1: 跑全量草稿**

Run: `.venv/Scripts/python.exe scripts/make_gold_draft.py`
产出 `data/gold/*.gold.json` 草稿 + `data/gold/manifest_candidates.json`（含分档与缺口）。

- [ ] **Step 2: 人工校正每个 gold（权威步骤）**

对每个要纳入基准的 `*.gold.json`：
- 据 `_draft_snippets`（边界附近转写）+ 原视频，逐个核对/修正 `boundaries_sec`（段开始秒，升序，不含起点 0 与片尾）。
- 改 `annotated_by` 为 `"human"`，按需填 `notes`。
- 删掉辅助字段 `_draft_snippets`（gold 正本不留草稿辅助）。
- 确认不变量 `n_segments == len(boundaries_sec) + 1`。
- 确认 `local_source` 指向**带画面的视频**（生产路径含 keyframes/VLM，纯音频不够）。`has_source=N` 的需补本地视频或剔除。

> **Gold 权威性**：人工校正后的 gold 是唯一权威；LLM 草稿仅降工作量，勿被其边界锚定——以转写原文与视频为准。

- [ ] **Step 3: 选定并冻结 30 视频 manifest**

据 `manifest_candidates.json` 挑选 ~22 learning + ~6 vlog + ~2 english，手写 `data/gold/manifest.json`：

```json
{
  "schema_version": 1,
  "created": "2026-06-09",
  "description": "frozen 30-video segmentation gold benchmark set",
  "videos": [
    {"video_id": "BV1BE411D7ii_p68_p0", "domain": "learning", "gold": "data/gold/BV1BE411D7ii_p68_p0.gold.json"}
  ]
}
```

- [ ] **Step 4: 校验 gold 一致性（脚本辅助，可选但推荐）**

可临时跑一行内联校验（确认每个 manifest 引用的 gold 满足不变量）：

Run:
```bash
.venv/Scripts/python.exe -c "import json,sys; sys.path.insert(0,'src'); m=json.load(open('data/gold/manifest.json',encoding='utf-8')); [ (lambda g: (print(v['video_id'], 'OK' if g['n_segments']==len(g['boundaries_sec'])+1 and g['annotated_by']=='human' else 'BAD')) )(json.load(open(v['gold'],encoding='utf-8'))) for v in m['videos'] ]"
```
Expected: 每行 `... OK`。任何 `BAD` 需回 Step 2 修。

- [ ] **Step 5: Commit（冻结）**

```bash
git add data/gold/manifest.json data/gold/*.gold.json
git commit -m "data(gold): freeze 30-video segmentation gold benchmark set"
```

---

## Task 7: `benchmark_segmentation.py` — 跑批 + 报表

**Files:**
- Create: `E:\claudeproject\notegen\scripts\benchmark_segmentation.py`
- Test: `E:\claudeproject\notegen\scripts\test_benchmark_helpers.py`（测纯函数 `assemble_row` / `aggregate`）
- Output: `data/outputs/benchmark_segmentation.json`、`paper/segmentation_benchmark.md`

> 读 manifest → 逐视频读 gold → 算 `chunk_chars = adaptive_chunk_chars(duration)` → 跑 free-K（bare `--chapters`）读 chapters.json → 跑 given-K（`--chapters n_segments`）读 chapters.json → 各算指标组行 → 写 JSON（含 header 元信息）+ 分档报表 md。
>
> **关键执行约束**：free-K 与 given-K 用**相同** stem/路径（chapters 数不进文件名），第二次跑会覆盖第一次的 chapters.json —— 必须**先跑 free-K 并读出 pred，再跑 given-K**（顺序读，不并行）。given-K 复用 free-K 已写的 ASR cache（不传 `--force-asr`）；VLM 是否缓存取决于 pipeline 现状，首跑时实测耗时（见风险）。

- [ ] **Step 1: Write the failing test (pure helpers)**

Create `scripts/test_benchmark_helpers.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe scripts/test_benchmark_helpers.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'benchmark_segmentation'`

- [ ] **Step 3: Write implementation**

Create `scripts/benchmark_segmentation.py`:

```python
"""30 视频 gold 切分基准跑批：读 data/gold/manifest.json，对每个视频跑生产 pipeline
(free-K + given-K oracle)，用 src/seg_eval 算 Boundary F1@15/@30 + Pk + WindowDiff，
出 data/outputs/benchmark_segmentation.json + paper/segmentation_benchmark.md。

pipeline 参数与 web worker (worker_tasks._build_cmd) 完全对齐：
  --local --chunker texttile --chunk-chars <adaptive> --summarizer neural
  --keyframes --llm-chapters --vlm-captions
chunk_chars 按 gold.duration 走 service_common.adaptive_chunk_chars。

Run: .venv/Scripts/python.exe scripts/benchmark_segmentation.py [--limit N] [--conditions free-K,given-K]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import os
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import seg_eval as E  # noqa: E402
import service_common as SC  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GOLD_DIR = ROOT / "data" / "gold"
OUTPUTS = ROOT / "data" / "outputs"
OUT_JSON = OUTPUTS / "benchmark_segmentation.json"
REPORT_MD = ROOT / "paper" / "segmentation_benchmark.md"

STATIC_ARGS = ["--local", "--chunker", "texttile", "--summarizer", "neural",
               "--keyframes", "--llm-chapters", "--vlm-captions"]
TOL15, TOL30 = 15.0, 30.0


def assemble_row(video_id: str, domain: str, condition: str, chunk_chars: int,
                 pred: list[float], gold: list[float], duration: float) -> dict:
    """组一行结果（纯函数）。"""
    t15 = E.boundary_prf(pred, gold, TOL15)
    t30 = E.boundary_prf(pred, gold, TOL30)
    pred_n = len(pred) + 1
    gold_n = len(gold) + 1
    return {
        "video_id": video_id, "domain": domain, "condition": condition,
        "chunk_chars": chunk_chars,
        "pred_boundaries_sec": pred, "gold_boundaries_sec": gold,
        "pred_n_segments": pred_n, "gold_n_segments": gold_n,
        "k_error": pred_n - gold_n,
        "tol15": {k: round(v, 4) if isinstance(v, float) else v for k, v in t15.items()},
        "tol30": {k: round(v, 4) if isinstance(v, float) else v for k, v in t30.items()},
        "pk": round(E.pk(pred, gold, duration), 4),
        "windowdiff": round(E.windowdiff(pred, gold, duration), 4),
    }


def aggregate(rows: list[dict]) -> dict:
    """按 (domain, condition) 求均值。返回 {(domain,cond): {F1@15,F1@30,Pk,WD,n}}。"""
    buckets: dict[tuple, list[dict]] = {}
    for r in rows:
        buckets.setdefault((r["domain"], r["condition"]), []).append(r)
    out = {}
    for key, rs in buckets.items():
        n = len(rs)
        out[key] = {
            "F1@15": sum(x["tol15"]["F1"] for x in rs) / n,
            "F1@30": sum(x["tol30"]["F1"] for x in rs) / n,
            "Pk": sum(x["pk"] for x in rs) / n,
            "WD": sum(x["windowdiff"] for x in rs) / n,
            "n": n,
        }
    return out


def _git_commit() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           cwd=str(ROOT), capture_output=True, text=True, timeout=10)
        return (r.stdout or "").strip() or "unknown"
    except Exception:
        return "unknown"


def _run_pipeline(video_id: str, local_source: str, chunk_chars: int,
                  chapters_arg: list[str], condition: str, run_start: float) -> list[float]:
    """跑一次 pipeline，返回 pred 边界。靠 mtime 找本次新写的 chapters.json，并立即
    快照到 condition 专属路径（free-K/given-K 同 stem 会互相覆盖，快照便于 debug/replay）。"""
    import shutil
    stem0 = Path(local_source).stem
    cmd = [str(SC.PY), "src/pipeline.py", local_source, *STATIC_ARGS,
           "--chunk-chars", str(chunk_chars), *chapters_arg]
    print(f"  $ {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=str(ROOT),
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    # 找本次运行新写的 chapters.json（mtime >= run_start，前缀匹配 stem0）
    cands = [p for p in OUTPUTS.glob(f"{stem0}*.chapters.json")
             if p.stat().st_mtime >= run_start - 2]
    if not cands:
        print(f"  [warn] rc={proc.returncode} 未找到 chapters.json", flush=True)
        return []
    cands.sort(key=lambda p: -p.stat().st_mtime)
    chap = cands[0]
    obj = json.loads(chap.read_text(encoding="utf-8"))
    # 立即快照（避免被下个 condition 覆盖后无法追溯）
    snap_dir = OUTPUTS / "benchmark"
    snap_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(chap, snap_dir / f"{video_id}.{condition}.chapters.json")
    return E.extract_pred_boundaries(obj)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--conditions", default="free-K,given-K")
    args = ap.parse_args()
    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]

    manifest = json.loads((GOLD_DIR / "manifest.json").read_text(encoding="utf-8"))
    videos = manifest["videos"][: args.limit] if args.limit else manifest["videos"]

    rows = []
    for v in videos:
        gold = json.loads((ROOT / v["gold"]).read_text(encoding="utf-8"))
        gold_b = gold["boundaries_sec"]
        duration = float(gold["duration"])
        cc = SC.adaptive_chunk_chars(duration)
        src = str((ROOT / gold["local_source"]))
        print(f"\n=== {v['video_id']} ({v['domain']}) dur={duration:.0f}s cc={cc} ===", flush=True)
        for cond in conditions:
            if cond == "free-K":
                chap_arg = ["--chapters"]                       # bare = 自适应
            else:
                chap_arg = ["--chapters", str(gold["n_segments"])]  # given-K oracle
            t0 = time.time()
            pred = _run_pipeline(v["video_id"], src, cc, chap_arg, cond, t0)
            rows.append(assemble_row(v["video_id"], v["domain"], cond, cc,
                                     pred, gold_b, duration))
            print(f"  [{cond}] pred_n={len(pred)+1} F1@15={rows[-1]['tol15']['F1']} "
                  f"Pk={rows[-1]['pk']} WD={rows[-1]['windowdiff']}", flush=True)

    header = {
        "metrics_version": E.METRICS_VERSION,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "commit": _git_commit(),
        "model": "Qwen2.5-7B-AWQ",
        "provider": "local",
        "static_pipeline_args": STATIC_ARGS,
        "chunk_chars_rule": "adaptive_chunk_chars(duration): <600s->400, <1500s->600, else 800",
        "chapters_arg": {"free-K": "--chapters (bare)", "given-K": "--chapters <n_segments>"},
        "results": rows,
    }
    OUT_JSON.write_text(json.dumps(header, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n写入 {OUT_JSON}（{len(rows)} 行）", flush=True)

    _write_report(aggregate(rows), header)
    print(f"报表写入 {REPORT_MD}", flush=True)
    return 0


def _write_report(agg: dict, header: dict) -> None:
    lines = ["# 切分基准报表", "",
             f"- run_at: {header['run_at']}  commit: `{header['commit']}`  "
             f"model: {header['model']} ({header['provider']})",
             f"- metrics_version: {header['metrics_version']}；主容差 ±15s，附 ±30s；Pk/WD 越低越好",
             f"- 滑窗遵 nltk 规范 `range(n-k+1)`；1s 单元离散（见 src/seg_eval.py）", "",
             "## 分档均值（learning 为主指标；vlog/english 作 OOD 参考）", "",
             "| domain | condition | n | F1@15 | F1@30 | Pk↓ | WD↓ |",
             "|---|---|---|---|---|---|---|"]
    for (dom, cond) in sorted(agg.keys()):
        a = agg[(dom, cond)]
        lines.append(f"| {dom} | {cond} | {a['n']} | {a['F1@15']:.3f} | "
                     f"{a['F1@30']:.3f} | {a['Pk']:.3f} | {a['WD']:.3f} |")
    lines += ["", "## free-K vs given-K（自适应定 K 的代价）", "",
              "given-K 给定 gold 章数作 oracle；free-K↔given-K 的 F1/Pk 差 + 各视频 "
              "`k_error`（见 benchmark_segmentation.json）量化「该切几章」误差与「边界放哪」误差。"]
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe scripts/test_benchmark_helpers.py`
Expected: `=== ALL CHECKS PASSED ===`

- [ ] **Step 5: Commit（先提交脚本，跑批是单独动作）**

```bash
git add scripts/benchmark_segmentation.py scripts/test_benchmark_helpers.py
git commit -m "feat(benchmark): segmentation gold benchmark runner + report"
```

---

## Task 8: 首轮跑批 + review（GPU，长耗时）

**Files:**
- Output: `data/outputs/benchmark_segmentation.json`、`paper/segmentation_benchmark.md`

> ⚠️ GPU 长耗时：30 视频 × 2 条件，VLM + LLM 串行（见 [[feedback-serial-model-loading]]）。先 `--limit 2` 验证链路再全量。

- [ ] **Step 1: 小样验证链路（2 视频）**

Run: `.venv/Scripts/python.exe scripts/benchmark_segmentation.py --limit 2`
Expected: 每视频两条件各跑出 pred、打印 F1/Pk/WD，写出 JSON + md，无异常。
检查点：given-K 的 `pred_n_segments` 应比 free-K 更贴近 `gold_n_segments`（`k_error` 更接近 0）；若 given-K 完全没约束住章数，回看 Task 4（可能需 Option B）。

- [ ] **Step 2: 全量跑批**

Run: `.venv/Scripts/python.exe scripts/benchmark_segmentation.py`
（耗时长，建议后台跑。given-K 复用 free-K 的 ASR cache。）

- [ ] **Step 3: review 结果**

- 看 `paper/segmentation_benchmark.md` 分档均值是否合理（learning F1@15 是否在可解释范围）。
- 据首轮按需迭代容差（±15/±30 是否合适）、`window_k` 约定。
- 量化 free-K vs given-K 差，写入对 roadmap #4 的基线结论。

- [ ] **Step 4: Commit 结果**

```bash
git add data/outputs/benchmark_segmentation.json paper/segmentation_benchmark.md
git commit -m "data(benchmark): first-round 30-video segmentation gold results"
```

---

## Notes for the executor

- **测试惯例**：纯 `__main__` 断言脚本（`check(cond,msg)` + `FAILS` + 末尾 `sys.exit(1)`），跑 `.venv/Scripts/python.exe scripts/test_*.py`。不要引入 pytest。
- **不改**：`scripts/eval_segmentation.py` 逻辑（仅可加一行 legacy 注释）、生产 pipeline 行为（`target_chapters=None` 时零变化）、`_diagnose_outline` / `_validate_outline`。
- **不 push**：所有 commit 留本地，push 是不可逆动作，等用户发话（见 [[project-roadmap-2026-06-09]] 收口惯例）。
- **Task 6 是人工断点**：执行到此暂停交还用户，校正 gold 后再继续 Task 7。
- **given-K Option A/B**：已选 Option A（见文首待决项）。Task 8 Step 1 是验证 Option A 是否够用的检查点。
