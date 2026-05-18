"""把 8 视频 × 2 chunker 的 summary.json 锁在 cc=800 + α=0.3 状态。

这是 headline 评估的输入。之前的 sweep 脚本会跑不同 cc，会留下不一致的 summary.json。
"""
from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PY = r"C:\Users\19145\miniconda3\envs\notegen\python.exe"

VIDEOS = [
    ("data/raw/BV19E411D78Q_p38.f30280.m4a", 5, []),
    ("data/raw/BV1SddcBFESs_p0.mp4",         3, ["--term", "主绘画=主会话"]),
    ("data/raw/BV1G85V6cE1g_p0.mp4",         2, []),
    ("data/raw/BV1W8AGzwEFW_p0.mp4",         5, []),
    ("data/raw/BV1x25P6tEKe_p0.mp4",         3, []),
    ("data/raw/BV1XY546vE1o_p0.mp4",         4, []),
    ("data/raw/BV1cwdzBDEL3_p0.mp4",         5, []),
    ("data/raw/BV1ygo9BeEvV_p0.mp4",         3, []),
]


def main():
    for video, K, extras in VIDEOS:
        for chunker in ["chars", "texttile"]:
            print(f">>> {Path(video).stem} | {chunker}")
            cmd = [PY, "src/pipeline.py", video, "--local",
                   "--model", "large-v3", "--summarizer", "neural",
                   "--chunker", chunker, "--chunk-chars", "800",
                   "--chapters", str(K), "--keyframes",
                   "--mm-alpha", "0.3", *extras]
            subprocess.run(cmd, capture_output=True, check=False)


if __name__ == "__main__":
    main()
