"""验证 Pegasus 章标题 copy-detection + fallback 在 p39 + 其它视频上效果。
不重跑 pipeline，复用已有 summary.json + chapters.json，只重新跑 title_fn。
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

# Windows 默认 stdout 编码 GBK，输出中文 / emoji 会崩。强制 UTF-8。
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from summarize_neural import (  # noqa: E402
    summarize_text, post_clean_headline,
    _is_chapter_title_copy, _fallback_chapter_title,
)


CASES = [
    "BV19E411D78Q_p39_p0.large-v3.neural.texttile",
    "BV1YE411D7nH_p37_p0.large-v3.neural.texttile",
    "BV1SddcBFESs_p0.large-v3.neural.texttile",
]


def regen_chapter_titles(stem: str):
    summary_path = Path(f"data/outputs/{stem}.summary.json")
    chapters_path = Path(f"data/outputs/{stem}.chapters.json")
    if not summary_path.exists() or not chapters_path.exists():
        print(f"[{stem}] missing files, skip")
        return
    summaries = json.loads(summary_path.read_text(encoding="utf-8"))
    payload = json.loads(chapters_path.read_text(encoding="utf-8"))
    chapters = payload.get("chapters", payload) if isinstance(payload, dict) else payload

    print(f"\n=== {stem} ===")
    for ci, ch in enumerate(chapters, 1):
        members = [summaries[i] for i in ch["indices"]]
        headlines = [m.get("headline", "") for m in members if m.get("headline")]
        old_title = ch["title"]

        if not headlines:
            new_title = old_title  # 无 headline 跳过
            note = "no headlines"
        elif len(headlines) == 1:
            new_title = headlines[0]
            note = "single chunk → use headline"
        else:
            joined = "。".join(headlines)
            pegasus_out = post_clean_headline(summarize_text(joined))
            is_copy = _is_chapter_title_copy(pegasus_out, headlines)
            use_fallback = len(headlines) <= 3 and is_copy
            if use_fallback:
                new_title = _fallback_chapter_title(headlines)
                note = f"COPY → fallback (pegasus said '{pegasus_out}')"
            elif is_copy:
                new_title = pegasus_out
                note = f"COPY but kept (n_chunks={len(headlines)} > 3, pegasus may have selected representative)"
            else:
                new_title = pegasus_out
                note = "pegasus synthesized OK"

        diff = "" if new_title == old_title else "  [CHANGED]"
        print(f"  章 {ci} (n_chunks={len(headlines)}): {note}{diff}")
        print(f"    old: {old_title}")
        if new_title != old_title:
            print(f"    new: {new_title}")


def main():
    for stem in CASES:
        regen_chapter_titles(stem)


if __name__ == "__main__":
    main()
