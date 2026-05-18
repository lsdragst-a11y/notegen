"""章节切分：基于相邻 chunk 关键词 Jaccard 距离的 TextTiling 风格 baseline。

输入：summarize_chunks 输出的列表（要求每项含 keywords / headline / start / end）。
输出：章节列表 [{title, start, end, indices: [chunk_idx, ...]}, ...]。

这是论文创新点"多模态章节切分"的纯文本 baseline；后续在 boundary score 上叠加
CLIP 帧相似度 / PPT 翻页信号，得到多模态版本。
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np


def jaccard_distance(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return 1.0 - len(a & b) / len(a | b)


def adjacent_distances(chunks: Sequence[dict]) -> list[float]:
    """相邻 chunk i, i+1 的 keyword Jaccard 距离序列，长度 = len(chunks) - 1。"""
    out = []
    for i in range(len(chunks) - 1):
        a = set(chunks[i].get("keywords", []))
        b = set(chunks[i + 1].get("keywords", []))
        out.append(jaccard_distance(a, b))
    return out


def visual_adjacent_distances(visual_feats: Sequence[np.ndarray | None]
                              ) -> list[float | None]:
    """相邻 chunk 视觉 embedding 的 cosine 距离。某段抽帧失败则该位置为 None。"""
    out: list[float | None] = []
    for i in range(len(visual_feats) - 1):
        a, b = visual_feats[i], visual_feats[i + 1]
        if a is None or b is None:
            out.append(None)
        else:
            cos = float(np.dot(a, b))
            out.append(1.0 - cos)
    return out


def _minmax(xs: Sequence[float | None]) -> list[float | None]:
    valid = [x for x in xs if x is not None]
    if not valid:
        return list(xs)
    lo, hi = min(valid), max(valid)
    if hi - lo < 1e-9:
        return [0.5 if x is not None else None for x in xs]
    return [(x - lo) / (hi - lo) if x is not None else None for x in xs]


def fuse_distances(text_dists: Sequence[float],
                   visual_dists: Sequence[float | None],
                   alpha: float = 0.5,
                   slide_dists: Sequence[float] | None = None,
                   slide_weight: float = 0.0) -> list[float]:
    """加权融合 text + visual boundary score。alpha=0 纯文本，1.0 纯视觉。
    两个序列各自先做 min-max 归一化到 [0,1] —— 否则 text(0.67~1.00) 会淹没
    visual(0.01~0.22)。某位置视觉缺失则退回该位置归一化后的文本值。

    slide_dists: 可选第三路 cue —— PPT slide 转场密度（[[slide.py]] 输出），
        作为 PPT 域专属 boundary 信号。slide_weight 是"加性 bonus"权重：
            fused[i] = (1-α)·t + α·v + slide_weight · slide_norm[i]
        不参与 α 校准（保持现有 α=0.3 设定不被破坏），slide_weight=0.1 意味着
        翻页密度峰值最多额外贡献 +0.1 depth。slide 信号在无翻页视频上全 0，
        此时退化为现有两路融合。"""
    t_norm = _minmax(text_dists)
    has_visual = any(v is not None for v in visual_dists)
    v_norm = _minmax(visual_dists) if has_visual else [None] * len(text_dists)
    s_norm: list[float | None]
    if slide_dists is not None and slide_weight > 0 and any(s > 0 for s in slide_dists):
        s_norm = _minmax(list(slide_dists))
    else:
        s_norm = [None] * len(text_dists)
    fused: list[float] = []
    for i, (tn, vn, t) in enumerate(zip(t_norm, v_norm, text_dists)):
        base = tn if tn is not None else t
        if vn is None:
            val = base
        else:
            val = alpha * vn + (1.0 - alpha) * base
        if s_norm[i] is not None:
            val += slide_weight * s_norm[i]
        fused.append(val)
    return fused


def depth_scores(distances: list[float]) -> list[float]:
    """TextTiling depth score 简化版：对每个 distance 位置 i，
    depth[i] = distances[i] - 0.5 * (left_neighbor + right_neighbor)。
    高 depth 意味着这是一个 "话题切换的山峰"。"""
    n = len(distances)
    out = [0.0] * n
    for i in range(n):
        left = distances[i - 1] if i > 0 else distances[i]
        right = distances[i + 1] if i < n - 1 else distances[i]
        out[i] = distances[i] - 0.5 * (left + right)
    return out


def _adaptive_K(depths: Sequence[float], n_chunks: int,
                min_K: int = 2) -> int:
    """自适应章数：在 depth_scores 上找正峰、NMS 合并相邻双峰，K = peaks + 1。

    取代旧的纯时长公式 ceil(dur/6)。动机：时长公式假设"每 6 分钟一个知识点"是
    错的——讲师可能 3 分钟讲一个，也可能 10 分钟讲一个。真正的"知识点边界"信号
    在 chunker 输出的 depth_scores 里：高 depth = 关键词分布跳变 = 话题切换。

    在 10 视频 benchmark 上：
    - Python基础 8 chunks: depth peaks 2 个 (idx 1, 4) → K=3（取代旧 K=4，章数减少
      但更紧凑，避免"单 chunk 一章"孤儿）
    - 王道 OS 11 chunks: depth peaks 4 个 → K=5（取代旧 K=3，原 [-0.242, 0.304,
      -0.15, 0.216, -0.11, -0.05, -0.014, 0.48, -0.753, 0.319] 4 个明显切点全用上）
    - 计网 p38: K=5（与旧相同）
    - ClaudeCode 4 chunks: K=2（取代旧 K=3，4 chunks 下 2 章更合理）

    Clamp 上限 n_chunks-1 避免章数超过 chunks gap 数。下限 min_K=2 兜底。
    """
    if not depths:
        return min_K
    n = len(depths)
    # 找 positive local peaks (允许平峰：>= left and >= right and > 0)
    raw_peaks: list[int] = []
    for i in range(n):
        if depths[i] <= 0:
            continue
        left = depths[i - 1] if i > 0 else -float("inf")
        right = depths[i + 1] if i < n - 1 else -float("inf")
        if depths[i] >= left and depths[i] >= right:
            raw_peaks.append(i)
    # NMS：按 depth 降序选，禁用 ±1 邻居（避免相邻双峰登记两次）
    raw_peaks.sort(key=lambda i: -depths[i])
    selected: list[int] = []
    for p in raw_peaks:
        if not any(abs(p - s) <= 1 for s in selected):
            selected.append(p)
    K = max(min_K, len(selected) + 1)
    K = min(K, max(min_K, n_chunks - 1))
    return K


def detect_boundaries(chunks: Sequence[dict], num_chapters: int | None = None,
                      min_chapter_len: int = 2,
                      visual_feats: Sequence[np.ndarray | None] | None = None,
                      alpha: float = 0.5,
                      slide_dists: Sequence[float] | None = None,
                      slide_weight: float = 0.0,
                      return_debug: bool = False):
    """返回章节边界索引列表（在 chunk 之间的位置），长度 = num_chapters - 1。

    boundary k 意味着第 k+1 章从 chunk[boundary] 开始。
    num_chapters=None 时调 `_adaptive_K(depth_scores, n_chunks)` 自适应——根据
    depth peaks 数量决定章数，不再用时长公式。num_chapters=int 时强制 K。
    visual_feats: 各 chunk 的 L2-normalized 视觉 embedding 列表；提供时用文本 +
        视觉融合距离做切分（论文创新点：多模态章节切分）。
    return_debug: True 时多返回一个 dict 含 text_dists / visual_dists / fused / scores。
    """
    n = len(chunks)
    if n <= 2:
        return ([], {}) if return_debug else []

    text_dists = adjacent_distances(chunks)
    if visual_feats is not None:
        visual_dists = visual_adjacent_distances(visual_feats)
        dists = fuse_distances(text_dists, visual_dists, alpha=alpha,
                               slide_dists=slide_dists, slide_weight=slide_weight)
    else:
        visual_dists = [None] * len(text_dists)
        if slide_dists is not None and slide_weight > 0:
            dists = fuse_distances(text_dists, visual_dists, alpha=0.0,
                                   slide_dists=slide_dists,
                                   slide_weight=slide_weight)
        else:
            dists = list(text_dists)
    scores = depth_scores(dists)

    if num_chapters:
        target = num_chapters
    else:
        target = _adaptive_K(scores, n)
    target = max(2, min(target, n))
    need = target - 1  # 边界数

    # 按 depth 降序排，挑出 need 个互不冲突（间隔 >= min_chapter_len）的边界
    candidates = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    # 优先满足 K-1 个边界：先用严格 min_chapter_len，选不满再逐级放宽到 1
    chosen: list[int] = []
    for attempt_min in range(min_chapter_len, 0, -1):
        chosen = []
        for idx in candidates:
            boundary = idx + 1  # 边界落在 chunk[idx] 和 chunk[idx+1] 之间
            if any(abs(boundary - b) < attempt_min for b in chosen):
                continue
            if boundary < attempt_min or boundary > n - attempt_min:
                continue
            chosen.append(boundary)
            if len(chosen) >= need:
                break
        if len(chosen) >= need:
            break
    chosen.sort()
    if return_debug:
        debug = {"text_dists": list(text_dists), "visual_dists": visual_dists,
                 "fused_dists": list(dists), "depth_scores": scores}
        return chosen, debug
    return chosen


def _default_title(members: Sequence[dict]) -> str:
    """缺神经摘要时的兜底标题：首段 headline 或 keywords 前 3。"""
    head = members[0]
    return head.get("headline") or " · ".join(head.get("keywords", [])[:3])


def group_into_chapters(chunks: Sequence[dict],
                        boundaries: Sequence[int],
                        title_fn=None) -> list[dict]:
    """根据边界把 chunks 分组成章节。title_fn(members)->str 自定义如何取标题。"""
    n = len(chunks)
    splits = [0, *boundaries, n]
    fn = title_fn or _default_title
    chapters = []
    for i in range(len(splits) - 1):
        lo, hi = splits[i], splits[i + 1]
        members = list(chunks[lo:hi])
        if not members:
            continue
        chapters.append({
            "title": fn(members),
            "start": members[0]["start"],
            "end": members[-1]["end"],
            "indices": list(range(lo, hi)),
            "chunks": members,
        })
    return chapters


def segment_chunks(chunks: Sequence[dict], num_chapters: int | None = None,
                   title_fn=None,
                   visual_feats: Sequence[np.ndarray | None] | None = None,
                   alpha: float = 0.5) -> list[dict]:
    """端到端入口：chunks → chapters。
    visual_feats 提供时启用多模态融合。"""
    boundaries = detect_boundaries(chunks, num_chapters=num_chapters,
                                   visual_feats=visual_feats, alpha=alpha)
    return group_into_chapters(chunks, boundaries, title_fn=title_fn)
