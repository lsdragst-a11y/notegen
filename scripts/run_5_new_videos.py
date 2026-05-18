"""扩 21+ corpus：5 个新视频，下载 + mm.vl 完整 pipeline。

每个视频：texttile + cc=800 + chapters auto + keyframes + mm-alpha 0.3
        + llm-chapters + vlm-captions（VL caption 三层 gate）。

下次扩 corpus 时直接改 VIDEOS 列表复用。失败时自动 retry-once（ASR transient
crash rc=0xC0000409 在 Windows 上偶发，ASR cache 已写盘，重跑 cache 命中即解决）。
"""
from __future__ import annotations

import io
import subprocess
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PY = sys.executable
LOG_DIR = Path("logs/batch_stderr")

# 清理 ?t= 时间戳参数，保留 ?p= playlist 参数
VIDEOS = [
    ("https://www.bilibili.com/video/BV1C8L36jEYN", "BV1C8L36jEYN"),
    ("https://www.bilibili.com/video/BV1pB5T6hEWW", "BV1pB5T6hEWW p1"),
    ("https://www.bilibili.com/video/BV1pB5T6hEWW?p=3", "BV1pB5T6hEWW p3"),
    ("https://www.bilibili.com/video/BV19E411D78Q?p=34", "BV19E411D78Q p34 (计网)"),
    ("https://www.bilibili.com/video/BV1E7wtzaEdq", "BV1E7wtzaEdq"),
]

# Windows STATUS_FATAL_APP_EXIT —— faster-whisper 退出阶段偶发，cache 写盘后崩
_RETRY_CODES = {3221226505}


def _run_once(cmd: list[str], project_root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=str(project_root),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def main():
    project_root = Path(__file__).resolve().parents[1]
    (project_root / LOG_DIR).mkdir(parents=True, exist_ok=True)
    overall_t0 = time.time()
    for idx, (url, label) in enumerate(VIDEOS, 1):
        print(f"\n{'='*70}\n>>> [{idx}/{len(VIDEOS)}] {label}\n    url={url}\n{'='*70}",
              flush=True)
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
        result = _run_once(cmd, project_root)
        if result.returncode in _RETRY_CODES:
            # ASR cache 应已写盘，retry 跳 ASR 直接进下游
            print(f"  ! rc={result.returncode}（ASR transient crash），retry once ...",
                  flush=True)
            err_path = project_root / LOG_DIR / f"{label.replace(' ', '_').replace('(', '').replace(')', '').replace('/', '_')}.crash1.stderr"
            err_path.write_text(result.stderr or "", encoding="utf-8")
            result = _run_once(cmd, project_root)
        dt = time.time() - t0
        tail = "\n".join((result.stdout or "").splitlines()[-25:])
        print(tail, flush=True)
        if result.returncode != 0:
            err_path = project_root / LOG_DIR / f"{label.replace(' ', '_').replace('(', '').replace(')', '').replace('/', '_')}.fail.stderr"
            err_path.write_text(result.stderr or "", encoding="utf-8")
            print(f"!! FAILED rc={result.returncode}, full stderr -> {err_path}",
                  flush=True)
            err_tail = "\n".join((result.stderr or "").splitlines()[-30:])
            print(err_tail, flush=True)
        print(f"  [{dt:.1f}s] {label}", flush=True)
    print(f"\n=== TOTAL {time.time()-overall_t0:.1f}s ===", flush=True)


if __name__ == "__main__":
    main()
