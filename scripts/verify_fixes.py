"""验证三个 fix 在 p39 + 王道 OS + 计网 p38 上的效果。
不跑 Pegasus/CLIP，只跑 dedupe → chunker → detect_boundaries (text-only)。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from asr import dedupe_consecutive_segments  # noqa: E402
from summarize import chunk_by_texttile, keywords_for  # noqa: E402
from segment import detect_boundaries  # noqa: E402


CASES = [
    ("BV19E411D78Q_p39_p0", "计网 p39 VLAN (20min)"),
    ("BV1YE411D7nH_p37_p0", "王道 OS 哲学家 (15min)"),
    ("BV19E411D78Q_p38",     "计网 p38 (30min, large-v3)"),
]


def run_case(stem: str, label: str, cc: int = 800):
    asr_path = Path(f"data/outputs/{stem}.large-v3.asr.json")
    if not asr_path.exists():
        print(f"[{label}] missing {asr_path}")
        return
    asr = json.loads(asr_path.read_text(encoding="utf-8"))
    for dd_label, segs in [
        ("no-dedupe", asr["segments"]),
        ("dedupe",
         dedupe_consecutive_segments(asr)[0]["segments"]),
    ]:
        chunks = chunk_by_texttile(segs, target_chunk_chars=cc)
        for c in chunks:
            c["keywords"] = keywords_for(c["text"])
        # 新公式驱动 default K（不传 num_chapters）
        bounds = detect_boundaries(chunks)
        dur = chunks[-1]["end"] - chunks[0]["start"]
        print(f"[{label}] cc={cc} {dd_label:>10}: "
              f"n_chunks={len(chunks):>2} dur={dur/60:.1f}min "
              f"auto_K={len(bounds)+1} boundaries={bounds}")


def main():
    for stem, label in CASES:
        run_case(stem, label)
        print()


if __name__ == "__main__":
    main()
