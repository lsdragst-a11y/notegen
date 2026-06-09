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
