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


def _boundaries_to_mask(boundaries: list[float], n: int, duration: float) -> list[int]:
    """长度 n 的 0/1 mask（after-semantics，对齐 nltk）：mask[j]=1 表示单元 j 之后紧跟段边界。
    先丢弃 b<=0 或 b>=duration（起点/片尾非内部边界），再 u=floor(b)，保留 1<=u<n，
    置 mask[u-1]=1（边界落在单元 u-1 与 u 之间）。写 u-1 而非 u 才能让 mask 直接是
    合法 nltk 输入（B[i:i+k] 计数无 edge off-by-one）。"""
    mask = [0] * n
    for b in boundaries:
        b = float(b)
        if b <= 0.0 or b >= duration:
            continue
        u = int(math.floor(b))
        if 1 <= u < n:
            mask[u - 1] = 1
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


def extract_pred_boundaries(chapters_obj: dict, start_eps: float = 1.0) -> list[float]:
    """从 chapters.json 的 dict 取各章 `start` 作为预测边界，去掉首章起点(≈0)。
    返回升序内部边界（秒）。chapters 已按时间排序时直接用；否则排序后取。"""
    chs = chapters_obj.get("chapters") or []
    starts = sorted(float(c.get("start", 0.0)) for c in chs)
    return [s for s in starts if s >= start_eps]
