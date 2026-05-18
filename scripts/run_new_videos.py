"""扩 benchmark：跑 2 个新视频 × {chars, texttile} × cc=400 + α=0.3。

只为 gold 标注做准备：chars@cc=400 输出 chunks 用于标 chars_gold；
texttile@cc=400 输出 chunks 用于标 texttile_gold。
cc=800 主操作点由 eval_texttile_at_cc800.py 自动反推 boundary_times 跑。
"""
from __future__ import annotations

import io
import subprocess
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PY = sys.executable

VIDEOS = [
    ("https://www.bilibili.com/video/BV1YE411D7nH?p=37", "王道OS 哲学家进餐 (15min)"),
    ("https://www.bilibili.com/video/BV1L24y1i7v3", "百度 5分钟看懂深度学习"),
]

CONFIGS = [
    # (chunker, chunk_chars)
    ("chars", 400),
    ("texttile", 400),
]


def main():
    project_root = Path(__file__).resolve().parents[1]
    for url, label in VIDEOS:
        print(f"\n{'='*70}\n>>> {label}\n    url={url}\n{'='*70}")
        for chunker, cc in CONFIGS:
            print(f"\n--- chunker={chunker} cc={cc} ---")
            t0 = time.time()
            cmd = [
                PY, "src/pipeline.py", url,
                "--summarizer", "neural",
                "--chunker", chunker,
                "--chunk-chars", str(cc),
                "--chapters",  # auto
                "--keyframes",
                "--mm-alpha", "0.3",
            ]
            result = subprocess.run(
                cmd, cwd=str(project_root),
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            dt = time.time() - t0
            tail = "\n".join((result.stdout or "").splitlines()[-12:])
            print(tail)
            if result.returncode != 0:
                print(f"!! FAILED rc={result.returncode}, stderr tail:")
                err_tail = "\n".join((result.stderr or "").splitlines()[-20:])
                print(err_tail)
                return
            print(f"  [{dt:.1f}s]")


if __name__ == "__main__":
    main()
