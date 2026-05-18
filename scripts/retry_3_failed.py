"""重跑 batch_5_new 里 3 个失败 case；前两个 ASR cache 命中。"""
from __future__ import annotations

import io
import subprocess
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PY = sys.executable

VIDEOS = [
    ("https://www.bilibili.com/video/BV1C8L36jEYN", "BV1C8L36jEYN (ASR cache)"),
    ("https://www.bilibili.com/video/BV1pB5T6hEWW?p=1", "BV1pB5T6hEWW p1 (fresh)"),
    ("https://www.bilibili.com/video/BV1pB5T6hEWW?p=3", "BV1pB5T6hEWW p3 (ASR cache)"),
]


def main():
    project_root = Path(__file__).resolve().parents[1]
    overall_t0 = time.time()
    for url, label in VIDEOS:
        print(f"\n{'='*70}\n>>> {label}\n    url={url}\n{'='*70}", flush=True)
        t0 = time.time()
        cmd = [
            PY, "src/pipeline.py", url,
            "--summarizer", "neural",
            "--chunker", "texttile",
            "--chunk-chars", "800",
            "--chapters",
            "--keyframes",
            "--mm-alpha", "0.3",
            "--llm-chapters",
            "--vlm-captions",
        ]
        result = subprocess.run(
            cmd, cwd=str(project_root),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        dt = time.time() - t0
        tail = "\n".join((result.stdout or "").splitlines()[-30:])
        print(tail, flush=True)
        if result.returncode != 0:
            print(f"!! FAILED rc={result.returncode}, stderr tail:", flush=True)
            err_tail = "\n".join((result.stderr or "").splitlines()[-40:])
            print(err_tail, flush=True)
        print(f"  [{dt:.1f}s] {label}", flush=True)
    print(f"\n=== TOTAL {time.time()-overall_t0:.1f}s ===", flush=True)


if __name__ == "__main__":
    main()
