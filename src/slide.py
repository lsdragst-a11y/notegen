"""PPT slide 转场检测：在视频时间轴上找"slide 翻页"时间戳。

动机：[[project-focus-learning]] 早就指出 PPT 教学视频上 slide 翻页频繁但话题未变，
通用 CLIP 帧嵌入信号会被 slide 切换淹没——所以 α=0.3 才稳健不主导。但 slide 翻页
本身是 PPT 域专属、跟章节切换更明确（虽不完美）对应的信号：章节切换处往往落在
一组 slide 翻页之间，而非密集翻页中间。把 slide 翻页时间戳转成"chunk gap 周围
翻页密度"作为第三路视觉 cue，在论文 §4.2 多模态融合上再叠一层。

实现要点：
- 用 HSV 直方图相关性（HISTCMP_CORREL）作 frame 间差异度量。对 slide 内文字小改/
  光标移动不敏感（HSV 量化后稳），对整面 layout 变化敏感（背景/前景配色突变）。
  这正是 slide 翻页的特征。比 SSIM 快一个量级，比 frame diff 鲁棒（不受亮度抖动）。
- 默认 1 fps 采样：PPT 翻页持续 0.3-1s，1 fps 足以抓住；30min 视频 1800 samples
  HSV 直方图计算 < 5s。
- corr_threshold=0.5：实测同 slide 不同帧 corr > 0.9，翻页时 corr < 0.3，0.5 是
  保守中点；连续多帧低 corr（翻页过渡）只保留首个，避免一次翻页登记多次。
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def detect_slide_transitions(video_path: Path | str,
                             sample_every_sec: float = 1.0,
                             corr_threshold: float = 0.5,
                             hist_bins: tuple[int, int, int] = (8, 8, 8),
                             min_gap_sec: float = 1.5) -> list[float]:
    """扫视频找 slide 翻页时间戳。

    Args:
        sample_every_sec: 帧采样间隔（秒）。默认 1.0 = 1 fps。
        corr_threshold: HSV 直方图相关性低于此值视为翻页。默认 0.5。
        hist_bins: HSV 三通道 bin 数。8×8×8=512 bins 在精度与速度间平衡。
        min_gap_sec: 两次翻页最小间隔（秒），合并翻页过渡的连续低相关帧。
            默认 1.5s = 翻页本身约 0.3-1s + 安全余量。

    Returns:
        翻页时间戳列表（秒），单调递增。
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"opencv 打不开视频: {video_path}")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration = total_frames / fps if total_frames else 0.0
        if duration <= 0:
            return []

        sample_times = np.arange(0.0, duration, sample_every_sec)
        prev_hist = None
        transitions: list[float] = []
        last_transition = -1e9
        for t in sample_times:
            cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000.0)
            ok, frame = cap.read()
            if not ok:
                continue
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1, 2], None, list(hist_bins),
                                [0, 180, 0, 256, 0, 256])
            cv2.normalize(hist, hist)
            if prev_hist is not None:
                corr = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
                if corr < corr_threshold and (t - last_transition) >= min_gap_sec:
                    transitions.append(float(t))
                    last_transition = t
            prev_hist = hist
        return transitions
    finally:
        cap.release()


def transitions_to_gap_density(transitions: list[float],
                               chunks: list[dict],
                               window_sec: float = 5.0) -> list[float]:
    """把 slide 翻页时间戳转成 chunk 间隙的"翻页密度"距离信号。

    对每个相邻 chunk gap i（在 chunks[i].end 时刻附近），数 ±window_sec 窗口内
    的翻页次数；归一化到 [0, 1] 作为距离信号（密度越高，越像章节切换处）。

    设计选择：
    - 用 ±window 而非"严格落在 gap 时刻"：实际章节切换处的 slide 翻页可能在
      讲师停顿前后 3-5s 内发生，窗口给容忍度。
    - 不直接用 binary "有/无翻页"：密度可以连续融合，与 jaccard/cos 距离同质。

    Returns:
        长度 = len(chunks) - 1 的距离列表，[0, 1] 内。
    """
    if len(chunks) <= 1:
        return []
    out: list[float] = []
    for i in range(len(chunks) - 1):
        gap_t = chunks[i].get("end", 0.0)
        lo = gap_t - window_sec
        hi = gap_t + window_sec
        count = sum(1 for t in transitions if lo <= t <= hi)
        out.append(float(count))
    # 归一化到 [0, 1]
    mx = max(out) if out else 0.0
    if mx > 0:
        out = [v / mx for v in out]
    return out


def detect_clip_transitions(video_path: Path | str,
                            sample_every_sec: float = 1.0,
                            cos_threshold: float = 0.92,
                            min_gap_sec: float = 1.5,
                            batch_size: int = 32) -> list[float]:
    """用 CLIP image embedding 距离替代 HSV 直方图检测 transition。

    动机：HSV 检测在"固定母版 + 字幕动画"型视频（王道系列）上失效——整面布局
    HSV 几乎不变，但实际话题切换处字幕标题/核心内容会跳变。CLIP image
    embedding 通过 ViT patches attends to 文字与文字布局，对字幕内容变化敏感。

    实现：1 fps 采样 → batch CLIP image encoder → 相邻帧 L2-normalized embedding
    cosine 距离 > 1-cos_threshold（即 cosine similarity < cos_threshold）视为
    transition。复用 keyframe.load_clip 缓存，无新模型依赖。

    Args:
        sample_every_sec: 帧采样间隔（秒）。
        cos_threshold: 相邻帧 cosine similarity 低于此值视为 transition。
            同 slide 不同帧 sim 通常 > 0.98，slide 切换时 sim < 0.85，0.92 是中点。
        min_gap_sec: 两次 transition 最小间隔，合并切换过渡。
        batch_size: CLIP image forward 子批大小（显存折中）。
    """
    # 延迟 import，避免 slide.py 在不需要 CLIP 的场景被强制 load
    import torch
    from keyframe import load_clip

    model, processor, device, _dtype = load_clip()

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"opencv 打不开视频: {video_path}")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration = total_frames / fps if total_frames else 0.0
        if duration <= 0:
            return []

        from PIL import Image
        sample_times = np.arange(0.0, duration, sample_every_sec)
        frames: list = []
        ts: list[float] = []
        for t in sample_times:
            cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000.0)
            ok, frame = cap.read()
            if not ok:
                continue
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(Image.fromarray(rgb))
            ts.append(float(t))
    finally:
        cap.release()

    if not frames:
        return []

    feats_chunks: list = []
    with torch.no_grad():
        for s in range(0, len(frames), batch_size):
            batch = frames[s:s + batch_size]
            inputs = processor(images=batch, return_tensors="pt").to(device)
            f = model.get_image_features(**inputs)
            f = f / f.norm(dim=-1, keepdim=True)
            feats_chunks.append(f)
    feats = torch.cat(feats_chunks, dim=0)
    # 相邻帧 cosine similarity
    sims = (feats[:-1] * feats[1:]).sum(dim=-1).cpu().tolist()

    transitions: list[float] = []
    last_t = -1e9
    for i, sim in enumerate(sims):
        if sim < cos_threshold and (ts[i + 1] - last_t) >= min_gap_sec:
            transitions.append(ts[i + 1])
            last_t = ts[i + 1]
    return transitions


if __name__ == "__main__":
    import sys
    import time
    mode = sys.argv[1] if len(sys.argv) > 1 else "hsv"
    video = Path(sys.argv[2])
    t0 = time.time()
    if mode == "clip":
        tr = detect_clip_transitions(video)
    else:
        tr = detect_slide_transitions(video)
    print(f"[{mode}] {video.name}: {len(tr)} transitions in {time.time() - t0:.1f}s")
    print(f"first 15: {[round(t, 1) for t in tr[:15]]}")
    if len(tr) > 1:
        gaps = np.diff(tr)
        print(f"gap stats: median={np.median(gaps):.1f}s, "
              f"p25={np.percentile(gaps, 25):.1f}s, "
              f"p75={np.percentile(gaps, 75):.1f}s")
