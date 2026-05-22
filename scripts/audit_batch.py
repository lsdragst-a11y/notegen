"""一次跑 6 个新视频审查批次。

- 顺序跑（避免 LLM/VL 互抢显存）
- 每个视频独立 try/except，单个失败不阻塞后续
- log 写 logs/audit_<ts>.log（tail -f 实时可看）
- 跑完打印精简汇总：每视频 attempts / repair / fallback / VL gate / 章节数
"""
from __future__ import annotations

import io
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PY = sys.executable
ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
OUT_DIR = ROOT / "data" / "outputs"

URLS = [
    "https://www.bilibili.com/video/BV1L35X62EbN",
    "https://www.bilibili.com/video/BV1B3DMByEDP",
    "https://www.bilibili.com/video/BV1orDVBbEHh",
    "https://www.bilibili.com/video/BV1eboQBCEqj",
    "https://www.bilibili.com/video/BV19SRSBeE6F",
    "https://www.bilibili.com/video/BV19E411D78Q?p=51",
]


def _bvid(url: str) -> str:
    m = re.search(r"(BV\w+)", url)
    p = re.search(r"[?&]p=(\d+)", url)
    return f"{m.group(1)}_p{p.group(1) if p else '0'}" if m else url[-20:]


def _seg_meta_summary(stem: str) -> str:
    """从 chapters.json 提关键字段做单行汇总。"""
    candidates = list(OUT_DIR.glob(f"{stem}*.large-v3.neural.texttile.mm.vl.chapters.json"))
    if not candidates:
        candidates = list(OUT_DIR.glob(f"{stem}*.large-v3.neural.texttile*.chapters.json"))
    if not candidates:
        return f"  {stem}: NO chapters.json"
    p = sorted(candidates, key=lambda x: -x.stat().st_mtime)[0]
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return f"  {stem}: parse fail {e}"
    ab = d.get("ablation") or {}
    sm = ab.get("seg_meta") or {}
    n_ch = ab.get("n_chapters") or len(d.get("chapters") or [])
    n_ck = ab.get("n_chunks") or "?"
    method = sm.get("method") or "?"
    via = sm.get("llm_pass_via") or "-"
    attempts = sm.get("llm_attempts", "?")
    repair = ",".join(sm.get("llm_repair_used") or []) or "-"
    fb = "FB" if sm.get("fallback_used") else "ok"
    vl_used = ab.get("vlm_captions_used")
    vl_dg = ab.get("vlm_degraded_reason") or "-"
    vl_rescue = sm.get("vl_rescue_used")
    lang = ab.get("lang", "?")
    return (f"  {p.name}\n"
            f"    chunks={n_ck} chapters={n_ch} lang={lang}\n"
            f"    method={method} attempts={attempts} via={via} repair={repair} {fb}\n"
            f"    VL used={vl_used} rescue={vl_rescue} degraded={vl_dg}")


def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"audit_{ts}.log"
    print(f"[batch] {len(URLS)} videos -> {log_path}")
    summary: list[str] = []
    t_start = time.time()

    with log_path.open("w", encoding="utf-8") as lf:
        for i, url in enumerate(URLS, 1):
            bv = _bvid(url)
            header = f"\n{'='*72}\n[{i}/{len(URLS)}] {bv}\n  url={url}\n  t0={datetime.now():%H:%M:%S}\n{'='*72}\n"
            print(header, end="", flush=True)
            lf.write(header); lf.flush()
            t0 = time.time()
            cmd = [
                PY, "src/pipeline.py", url,
                "--chunker", "texttile",
                "--chunk-chars", "800",
                "--chapters",
                "--summarizer", "neural",
                "--keyframes",
                "--llm-chapters",
                "--vlm-captions",
                "--quality", "720p",
            ]
            try:
                proc = subprocess.Popen(
                    cmd, cwd=str(ROOT),
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                )
                assert proc.stdout is not None
                for line in proc.stdout:
                    line = line.rstrip()
                    # tee: 写文件 + stdout 一行（让 monitor 能看到）
                    lf.write(line + "\n"); lf.flush()
                    print(line, flush=True)
                proc.wait()
                dt = time.time() - t0
                line = f"\n[{i}/{len(URLS)}] DONE rc={proc.returncode} elapsed={dt/60:.1f}min\n"
            except Exception as e:
                dt = time.time() - t0
                line = f"\n[{i}/{len(URLS)}] EXCEPTION {type(e).__name__}: {e} elapsed={dt/60:.1f}min\n"
            print(line, flush=True)
            lf.write(line); lf.flush()
            summary.append(_seg_meta_summary(bv))

        footer = f"\n\n{'#'*72}\n# SUMMARY (total {(time.time()-t_start)/60:.1f}min)\n{'#'*72}\n"
        print(footer, end="")
        lf.write(footer)
        for s in summary:
            print(s); lf.write(s + "\n")


if __name__ == "__main__":
    main()
