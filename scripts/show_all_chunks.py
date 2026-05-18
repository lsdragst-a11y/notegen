"""列出所有 8 视频 × 2 chunker 的 chunks，便于一次性标 gold。"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

VIDEOS = [
    ("BV19E411D78Q_p38.f30280", "计网（PPT, 30min）"),
    ("BV1SddcBFESs_p0",          "ClaudeCode（PPT, 11min）"),
    ("BV1G85V6cE1g_p0",          "懂王（实拍, 7min）"),
    ("BV1W8AGzwEFW_p0",          "外卖 Vlog（实拍, 17min）"),
    ("BV1x25P6tEKe_p0",          "iOS 评测（数码科普, 10min）"),
    ("BV1XY546vE1o_p0",          "影视飓风×刘谦（多镜头, 14min）"),
    ("BV1cwdzBDEL3_p0",          "日本小镇 Vlog（实拍, 15min）"),
    ("BV1ygo9BeEvV_p0",          "多 Agent 可视化（编程, 11min）"),
]


def fmt_t(s: float) -> str:
    m, sec = divmod(int(s), 60)
    return f"{m:02d}:{sec:02d}"


def show(path: Path):
    chunks = json.loads(path.read_text(encoding="utf-8"))
    for i, c in enumerate(chunks, 1):
        head = (c.get("headline") or "?")[:40]
        kw = " · ".join(c.get("keywords", [])[:4])
        print(f"  #{i:2d} [{fmt_t(c['start'])}-{fmt_t(c['end'])}] "
              f"{len(c.get('text', '')):4d}c  {head}\n      kw={kw}")


def main():
    for stem, label in VIDEOS:
        chars_path = Path(f"data/outputs/{stem}.large-v3.neural.summary.json")
        tt_path = Path(f"data/outputs/{stem}.large-v3.neural.texttile.summary.json")
        print(f"\n{'=' * 72}\n=== {label} ===")
        chars = json.loads(chars_path.read_text(encoding="utf-8"))
        tt = json.loads(tt_path.read_text(encoding="utf-8"))
        print(f"\n--- chars ({len(chars)} chunks) ---")
        show(chars_path)
        print(f"\n--- texttile ({len(tt)} chunks) ---")
        show(tt_path)


if __name__ == "__main__":
    main()
