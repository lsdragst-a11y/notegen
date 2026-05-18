"""把 8 个 benchmark 视频 × 2 chunker 都用 chunk_chars=400 重跑一次。

ASR 有 cache，重跑只重新做 chunking + summarize + keyframes，每次约 30-60 秒。
跑完看 chunks 内容人工标 gold，再跑 alpha ablation。
"""
from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PY = r"C:\Users\19145\miniconda3\envs\notegen\python.exe"
CHUNK_CHARS = 400

VIDEOS = [
    ("data/raw/BV19E411D78Q_p38.f30280.m4a", []),
    ("data/raw/BV1SddcBFESs_p0.mp4", ["--term", "主绘画=主会话"]),
    ("data/raw/BV1G85V6cE1g_p0.mp4", []),
    ("data/raw/BV1W8AGzwEFW_p0.mp4", []),
    ("data/raw/BV1x25P6tEKe_p0.mp4", []),
    ("data/raw/BV1XY546vE1o_p0.mp4", []),
    ("data/raw/BV1cwdzBDEL3_p0.mp4", []),
    ("data/raw/BV1ygo9BeEvV_p0.mp4", []),
]
CHUNKERS = ["chars", "texttile"]


def main():
    for video, extras in VIDEOS:
        for chunker in CHUNKERS:
            print(f"\n>>> {Path(video).stem} | chunker={chunker} | chunk_chars={CHUNK_CHARS}")
            cmd = [PY, "src/pipeline.py", video, "--local",
                   "--model", "large-v3", "--summarizer", "neural",
                   "--chunker", chunker, "--chunk-chars", str(CHUNK_CHARS),
                   "--chapters", "--keyframes", "--mm-alpha", "0.3",
                   *extras]
            r = subprocess.run(cmd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            # 只打"章节切分"行和最后的 OK 行
            tail = (r.stdout or "").splitlines()[-15:]
            for line in tail:
                if "章节切分" in line or "[OK]" in line or "chunks" in line and "chunker" in line:
                    print(f"    {line.strip()}")


if __name__ == "__main__":
    main()
