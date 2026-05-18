"""并排对比两份 ASR 输出，统计字符级差异。

用法：
    python scripts/compare_asr.py \
        data/outputs/<stem>.small.asr.json \
        data/outputs/<stem>.large-v3.asr.json
"""
from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path


def load_segments(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["segments"]


def char_stats(a: str, b: str) -> dict:
    """字符级 Levenshtein 比例（基于 difflib SequenceMatcher）。"""
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    ratio = sm.ratio()
    matches = sum(t.size for t in sm.get_matching_blocks())
    return {
        "len_a": len(a), "len_b": len(b),
        "match_chars": matches,
        "similarity": round(ratio, 4),
        "diff_chars": max(len(a), len(b)) - matches,
    }


def print_side_by_side(a_segs: list[dict], b_segs: list[dict], n: int = 10) -> None:
    print(f"\n=== 前 {n} 段并排 ===\n")
    for i in range(min(n, len(a_segs), len(b_segs))):
        sa, sb = a_segs[i], b_segs[i]
        print(f"[{i+1}] A {sa['start']:.1f}-{sa['end']:.1f}s")
        print(f"     {sa['text']}")
        print(f"    B {sb['start']:.1f}-{sb['end']:.1f}s")
        print(f"     {sb['text']}")
        print()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("file_a", type=Path, help="第一份 ASR JSON（基线）")
    p.add_argument("file_b", type=Path, help="第二份 ASR JSON（对照）")
    p.add_argument("-n", type=int, default=10, help="并排打印前 N 段")
    args = p.parse_args()

    a_segs = load_segments(args.file_a)
    b_segs = load_segments(args.file_b)
    a_text = "".join(s["text"] for s in a_segs)
    b_text = "".join(s["text"] for s in b_segs)

    print(f"A = {args.file_a.name}  ({len(a_segs)} 段, {len(a_text)} 字)")
    print(f"B = {args.file_b.name}  ({len(b_segs)} 段, {len(b_text)} 字)")
    stats = char_stats(a_text, b_text)
    print(f"\n字符相似度: {stats['similarity']*100:.2f}%")
    print(f"差异字符数: ~{stats['diff_chars']} / {max(stats['len_a'], stats['len_b'])}")

    print_side_by_side(a_segs, b_segs, n=args.n)


if __name__ == "__main__":
    main()
