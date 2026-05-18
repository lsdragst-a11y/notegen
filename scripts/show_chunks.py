"""列出某个 summary.json 里所有 chunks 的 headline + keywords，便于人工标 gold 边界。"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def fmt_t(s: float) -> str:
    m, sec = divmod(int(s), 60)
    return f"{m:02d}:{sec:02d}"


def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/show_chunks.py <stem>")
        print("  stem 例: BV19E411D78Q_p38.f30280.large-v3.neural.texttile")
        sys.exit(1)
    stem = sys.argv[1]
    path = Path(f"data/outputs/{stem}.summary.json")
    if not path.exists():
        print(f"{path} 不存在")
        sys.exit(1)
    chunks = json.loads(path.read_text(encoding="utf-8"))
    print(f"=== {stem} ({len(chunks)} chunks) ===")
    for i, c in enumerate(chunks, 1):
        head = c.get("headline", "?")
        kw = " · ".join(c.get("keywords", [])[:5])
        chars = len(c.get("text", ""))
        print(f"#{i:2d} [{fmt_t(c['start'])}-{fmt_t(c['end'])}] {chars}c  "
              f"{head}\n    kw={kw}")


if __name__ == "__main__":
    main()
