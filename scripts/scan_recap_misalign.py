"""启发式扫全 corpus，找 recap 内容串到相邻章的「错位」笔记。

判据：对每章 i，把它的 recap 分词，分别和 [本章 title+abstract] / [下一章 title+abstract]
的 jieba 词集求 Jaccard。若 next 明显高于 self（差值过阈值且 next 不算太低），
判该章 recap 疑似错配到下一章内容（即 claudecode ch2/ch3 那种「ch2 recap 讲的是 ch3」）。

只报告，不改文件。跑法：
  .venv/Scripts/python.exe scripts/scan_recap_misalign.py
  .venv/Scripts/python.exe scripts/scan_recap_misalign.py --verbose
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re

import jieba

# next 比 self 高出这个差值，且 next 至少这么大，才判错位（避免噪声误报）
DELTA = 0.08
NEXT_MIN = 0.12
_STOP = set("的 了 与 和 及 在 是 中 对 上 下 等 这 那 个 我 你 他 们 一 也 就 都 把 被 让 使 以 为 用 到 会 能".split())
_TOKEN_RE = re.compile(r"[一-鿿]+|[A-Za-z][A-Za-z0-9_]+")


def toks(s: str) -> set[str]:
    s = s or ""
    out: set[str] = set()
    for m in _TOKEN_RE.findall(s):
        if re.match(r"[A-Za-z]", m):
            if len(m) > 1:
                out.add(m.lower())
        else:
            for w in jieba.cut(m):
                if len(w) >= 2 and w not in _STOP:
                    out.add(w)
    return out


def jac(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def ctx(ch: dict) -> set[str]:
    """章的「身份」词集：标题 + abstract（不含 recap，避免循环参照）。"""
    return toks((ch.get("title") or "") + " " + (ch.get("abstract") or ""))


def scan_note(path: str, verbose: bool) -> list[str]:
    d = json.load(open(path, encoding="utf-8"))
    chs = d.get("chapters", []) if isinstance(d, dict) else d
    if not isinstance(chs, list) or len(chs) < 2:
        return []
    flags = []
    self_ctx = [ctx(c) for c in chs]
    for i, c in enumerate(chs):
        if i + 1 >= len(chs):
            continue
        r = toks(c.get("recap") or "")
        if not r:
            continue
        s_self = jac(r, self_ctx[i])
        s_next = jac(r, self_ctx[i + 1])
        if s_next - s_self > DELTA and s_next >= NEXT_MIN:
            flags.append(f"ch{i}「{c.get('title')}」recap更像ch{i+1}「{chs[i+1].get('title')}」"
                         f"(self={s_self:.2f} next={s_next:.2f})")
            if verbose:
                flags.append(f"      recap: {(c.get('recap') or '')[:90]}")
    return flags


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    jieba.setLogLevel(60)
    files = sorted(glob.glob("web/public/notes/*/chapters.json"))
    hit = 0
    for f in files:
        note = os.path.basename(os.path.dirname(f))
        flags = scan_note(f, args.verbose)
        if flags:
            hit += 1
            print(f"[!] {note}")
            for fl in flags:
                print(f"    {fl}")
    print(f"\n扫描 {len(files)} 笔记，疑似 recap 错位 {hit} 个"
          f"（DELTA={DELTA} NEXT_MIN={NEXT_MIN}）")


if __name__ == "__main__":
    main()
