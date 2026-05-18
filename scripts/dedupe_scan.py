"""扫所有 ASR cache 看 dedupe 影响。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from asr import dedupe_consecutive_segments  # noqa: E402


def main():
    out_dir = Path("data/outputs")
    for f in sorted(out_dir.glob("*.asr.json")):
        asr = json.loads(f.read_text(encoding="utf-8"))
        new, stats = dedupe_consecutive_segments(asr)
        name = f.stem.split(".")[0]
        n_segs = len(asr["segments"])
        if stats["dropped"]:
            print(f"{name}: {n_segs} segs → dropped {stats['dropped']} "
                  f"({len(stats['runs'])} runs)")
            for r in stats["runs"]:
                print(f"  run x{r['run_len']} @ {r['start']:.1f}s: {r['text'][:40]}")
        else:
            print(f"{name}: {n_segs} segs, no changes")


if __name__ == "__main__":
    main()
