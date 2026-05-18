"""快速对比 chunk_by_chars vs chunk_by_texttile 的切分结果。"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from summarize import chunk_by_chars, chunk_by_texttile  # noqa: E402

VIDEOS = [
    ("BV19E411D78Q_p38.f30280", "计网（PPT, 30min）", 800),
    ("BV1SddcBFESs_p0",          "ClaudeCode（PPT, 11min）", 800),
    ("BV1G85V6cE1g_p0",          "懂王评论（实拍, 7min）", 800),
    ("BV1W8AGzwEFW_p0",          "外卖 Vlog（实拍, 17min）", 800),
]


def fmt_t(s: float) -> str:
    m, sec = divmod(int(s), 60)
    return f"{m:02d}:{sec:02d}"


def main():
    for stem, label, cc in VIDEOS:
        asr_path = Path(f"data/outputs/{stem}.large-v3.asr.json")
        if not asr_path.exists():
            print(f"[skip] {asr_path} 不存在")
            continue
        segs = json.loads(asr_path.read_text(encoding="utf-8"))["segments"]

        chars_chunks = chunk_by_chars(segs, chunk_chars=cc)
        tt_chunks, debug = chunk_by_texttile(segs, target_chunk_chars=cc,
                                             return_debug=True)
        print(f"\n=== {label} ===")
        print(f"  chunk_by_chars  : {len(chars_chunks)} chunks")
        print(f"  chunk_by_texttile: {len(tt_chunks)} chunks  "
              f"(target_breaks={debug.get('target_breaks')}, "
              f"actual={len(tt_chunks) - 1})")
        print(f"\n  --- chars 切点 ---")
        for i, ch in enumerate(chars_chunks):
            head = ch["text"].replace("\n", " ")[:50]
            print(f"  #{i + 1:2d} [{fmt_t(ch['start'])}-{fmt_t(ch['end'])}] "
                  f"{len(ch['text']):4d}c  {head}…")
        print(f"\n  --- texttile 切点 ---")
        for i, ch in enumerate(tt_chunks):
            head = ch["text"].replace("\n", " ")[:50]
            print(f"  #{i + 1:2d} [{fmt_t(ch['start'])}-{fmt_t(ch['end'])}] "
                  f"{len(ch['text']):4d}c  {head}…")


if __name__ == "__main__":
    main()
