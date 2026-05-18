"""分析 ASR segment 间静音 gap 的分布，定 VAD chunking 阈值。

对每个 benchmark 视频：
- 打印 gap 分布的分位数（p50/p75/p90/p95/max）
- 列出 top-N 长 gap 位置（segment idx 和对应时间）
- 与 gold 章节边界（按 chunk 标的）对比时，需要 chunker-aware 映射，所以这里
  只看 segment 级 gap 分布
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

VIDEOS = [
    ("BV19E411D78Q_p38.f30280", "计网（PPT）"),
    ("BV1SddcBFESs_p0",          "ClaudeCode（PPT）"),
    ("BV1G85V6cE1g_p0",          "懂王评论（实拍）"),
    ("BV1W8AGzwEFW_p0",          "外卖 Vlog（实拍）"),
]


def gaps_of(asr_path: Path) -> list[tuple[int, float, float, str, str]]:
    """返回每个 gap 的 (seg_idx_after_gap, gap_seconds, gap_start_time, prev_text, next_text)。"""
    data = json.loads(asr_path.read_text(encoding="utf-8"))
    segs = data["segments"]
    out = []
    for i in range(1, len(segs)):
        prev, cur = segs[i - 1], segs[i]
        gap = cur["start"] - prev["end"]
        out.append((i, gap, prev["end"], prev["text"], cur["text"]))
    return out


def quantile(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def main():
    for stem, label in VIDEOS:
        asr_path = Path(f"data/outputs/{stem}.large-v3.asr.json")
        if not asr_path.exists():
            print(f"[skip] {label}: {asr_path} 不存在")
            continue
        gaps = gaps_of(asr_path)
        vals = [g[1] for g in gaps]
        print(f"\n=== {label} ({len(vals)} segments) ===")
        print(f"  total segments = {len(vals) + 1}")
        print(f"  gap p50 = {quantile(vals, 0.5):.2f}s,  "
              f"p75 = {quantile(vals, 0.75):.2f}s,  "
              f"p90 = {quantile(vals, 0.90):.2f}s,  "
              f"p95 = {quantile(vals, 0.95):.2f}s,  "
              f"max = {max(vals):.2f}s")
        print(f"  >0.5s: {sum(1 for v in vals if v > 0.5)}, "
              f">1.0s: {sum(1 for v in vals if v > 1.0)}, "
              f">2.0s: {sum(1 for v in vals if v > 2.0)}, "
              f">3.0s: {sum(1 for v in vals if v > 3.0)}")
        # top-10 长 gap
        top = sorted(gaps, key=lambda g: -g[1])[:10]
        print(f"  top-10 长 gap:")
        for idx, gap, t, prev, nxt in top:
            mm, ss = divmod(int(t), 60)
            print(f"    seg#{idx:3d} @ {mm:02d}:{ss:02d}  gap={gap:5.2f}s  "
                  f"  …{prev[-15:]} | {nxt[:15]}…")


if __name__ == "__main__":
    main()
