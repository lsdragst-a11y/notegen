"""统计 ASR segment 末尾标点的分布。

faster-whisper 中文 ASR 已知 "长视频中段后丢失标点" 现象（memory 第 7 条）。
但 segment 边界本身是 VAD 在停顿点切出来的，可能仍带某种结束符。
看看每个 video 的 segment 末尾字符种类分布，决定能否拿"段尾标点"做 chunk 切分信号。
"""
from __future__ import annotations

import io
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

VIDEOS = [
    ("BV19E411D78Q_p38.f30280", "计网（PPT）"),
    ("BV1SddcBFESs_p0",          "ClaudeCode（PPT）"),
    ("BV1G85V6cE1g_p0",          "懂王评论（实拍）"),
    ("BV1W8AGzwEFW_p0",          "外卖 Vlog（实拍）"),
]

SENT_END = set("。！？!?；;.")
COMMA = set(",，、")


def categorize(ch: str) -> str:
    if ch in SENT_END:
        return "sent-end"
    if ch in COMMA:
        return "comma"
    return "other"


def main():
    for stem, label in VIDEOS:
        asr_path = Path(f"data/outputs/{stem}.large-v3.asr.json")
        if not asr_path.exists():
            print(f"[skip] {label}: {asr_path} 不存在")
            continue
        data = json.loads(asr_path.read_text(encoding="utf-8"))
        segs = data["segments"]
        cats = Counter()
        last_chars = Counter()
        for s in segs:
            t = s["text"].rstrip()
            if not t:
                continue
            last = t[-1]
            cats[categorize(last)] += 1
            last_chars[last] += 1
        n = sum(cats.values())
        print(f"\n=== {label} (n={n} segments) ===")
        for k in ("sent-end", "comma", "other"):
            v = cats.get(k, 0)
            print(f"  {k:>10s}: {v:4d}  ({v / n * 100:5.1f}%)")
        print(f"  top-10 末尾字符:")
        for ch, c in last_chars.most_common(10):
            print(f"    '{ch}' : {c}")

        # 看末尾标点的时间分布：前半段 vs 后半段
        if not segs:
            continue
        total_dur = segs[-1]["end"]
        first_half = [s for s in segs if s["end"] < total_dur / 2]
        second_half = [s for s in segs if s["end"] >= total_dur / 2]
        def pct(group, cat):
            if not group:
                return 0.0
            c = sum(1 for s in group if s["text"].rstrip()
                    and categorize(s["text"].rstrip()[-1]) == cat)
            return c / len(group) * 100
        print(f"  前半段 sent-end%: {pct(first_half, 'sent-end'):5.1f}, "
              f"后半段 sent-end%: {pct(second_half, 'sent-end'):5.1f}")
        print(f"  前半段 comma%:    {pct(first_half, 'comma'):5.1f}, "
              f"后半段 comma%:    {pct(second_half, 'comma'):5.1f}")


if __name__ == "__main__":
    main()
