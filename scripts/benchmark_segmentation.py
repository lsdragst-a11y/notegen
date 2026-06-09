"""30 视频 gold 切分基准跑批：读 data/gold/manifest.json，对每个视频跑生产 pipeline
(free-K + given-K oracle)，用 src/seg_eval 算 Boundary F1@15/@30 + Pk + WindowDiff，
出 data/outputs/benchmark_segmentation.json + paper/segmentation_benchmark.md.

pipeline 参数与 web worker (worker_tasks._build_cmd) 完全对齐：
  --local --chunker texttile --chunk-chars <adaptive> --summarizer neural
  --keyframes --llm-chapters --vlm-captions
chunk_chars 按 gold.duration 走 service_common.adaptive_chunk_chars。

Run: .venv/Scripts/python.exe scripts/benchmark_segmentation.py [--limit N] [--conditions free-K,given-K]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import os
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import seg_eval as E  # noqa: E402
import service_common as SC  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GOLD_DIR = ROOT / "data" / "gold"
OUTPUTS = ROOT / "data" / "outputs"
OUT_JSON = OUTPUTS / "benchmark_segmentation.json"
REPORT_MD = ROOT / "paper" / "segmentation_benchmark.md"

STATIC_ARGS = ["--local", "--chunker", "texttile", "--summarizer", "neural",
               "--keyframes", "--llm-chapters", "--vlm-captions"]
TOL15, TOL30 = 15.0, 30.0


def assemble_row(video_id: str, domain: str, condition: str, chunk_chars: int,
                 pred: list[float], gold: list[float], duration: float,
                 pipeline_failed: bool = False) -> dict:
    """组一行结果（纯函数）。pipeline_failed=True 标记本次跑批失败（崩溃/没产出 chapters），
    供分析时把「真预测了 0 章」与「pipeline 挂了」区分开，避免污染聚合均值。"""
    t15 = E.boundary_prf(pred, gold, TOL15)
    t30 = E.boundary_prf(pred, gold, TOL30)
    pred_n = len(pred) + 1
    gold_n = len(gold) + 1
    return {
        "video_id": video_id, "domain": domain, "condition": condition,
        "chunk_chars": chunk_chars, "pipeline_failed": pipeline_failed,
        "pred_boundaries_sec": pred, "gold_boundaries_sec": gold,
        "pred_n_segments": pred_n, "gold_n_segments": gold_n,
        "k_error": pred_n - gold_n,
        "tol15": {k: round(v, 4) if isinstance(v, float) else v for k, v in t15.items()},
        "tol30": {k: round(v, 4) if isinstance(v, float) else v for k, v in t30.items()},
        "pk": round(E.pk(pred, gold, duration), 4),
        "windowdiff": round(E.windowdiff(pred, gold, duration), 4),
    }


def aggregate(rows: list[dict]) -> dict:
    """按 (domain, condition) 求均值。返回 {(domain,cond): {F1@15,F1@30,Pk,WD,n}}。"""
    buckets: dict[tuple, list[dict]] = {}
    for r in rows:
        buckets.setdefault((r["domain"], r["condition"]), []).append(r)
    out = {}
    for key, rs in buckets.items():
        n = len(rs)
        out[key] = {
            "F1@15": sum(x["tol15"]["F1"] for x in rs) / n,
            "F1@30": sum(x["tol30"]["F1"] for x in rs) / n,
            "Pk": sum(x["pk"] for x in rs) / n,
            "WD": sum(x["windowdiff"] for x in rs) / n,
            "n": n,
        }
    return out


def _git_commit() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           cwd=str(ROOT), capture_output=True, text=True, timeout=10)
        return (r.stdout or "").strip() or "unknown"
    except Exception:
        return "unknown"


def _run_pipeline(video_id: str, local_source: str, chunk_chars: int,
                  chapters_arg: list[str], condition: str,
                  run_start: float) -> tuple[list[float], bool]:
    """跑一次 pipeline，返回 (pred 边界, ok)。ok=False 表示本次跑批失败（非零退出码
    或没找到本次新写的 chapters.json）。靠 mtime 找本次新写的 chapters.json，并立即
    快照到 condition 专属路径（free-K/given-K 同 stem 会互相覆盖，快照便于 debug/replay）。"""
    stem0 = Path(local_source).stem
    cmd = [str(SC.PY), "src/pipeline.py", local_source, *STATIC_ARGS,
           "--chunk-chars", str(chunk_chars), *chapters_arg]
    print(f"  $ {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=str(ROOT),
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    # 找本次运行新写的 chapters.json（mtime >= run_start，前缀匹配 stem0）
    cands = [p for p in OUTPUTS.glob(f"{stem0}*.chapters.json")
             if p.stat().st_mtime >= run_start - 2]
    if proc.returncode != 0 or not cands:
        # rc!=0 但有新文件：保留 pred 供人工复核，仍标失败；无新文件则空 pred + 失败
        print(f"  [warn] {video_id} [{condition}] pipeline 失败：rc={proc.returncode} "
              f"新 chapters.json={len(cands)} 个", flush=True)
        if not cands:
            return [], False
    cands.sort(key=lambda p: -p.stat().st_mtime)
    chap = cands[0]
    obj = json.loads(chap.read_text(encoding="utf-8"))
    # 立即快照（避免被下个 condition 覆盖后无法追溯）
    snap_dir = OUTPUTS / "benchmark"
    snap_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(chap, snap_dir / f"{video_id}.{condition}.chapters.json")
    return E.extract_pred_boundaries(obj), proc.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--conditions", default="free-K,given-K")
    args = ap.parse_args()
    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]

    manifest = json.loads((GOLD_DIR / "manifest.json").read_text(encoding="utf-8"))
    videos = manifest["videos"][: args.limit] if args.limit else manifest["videos"]

    # --- 时长 pre-flight：gold.duration 既喂 chunk_chars 又喂 Pk/WD 离散，错了整批失真。
    #     用 ffprobe 实测核对，偏差 > max(30s, 5%) 即 fail fast；ffprobe 返回 0（失败）则跳过不阻断。---
    mism = []
    for v in videos:
        g = json.loads((ROOT / v["gold"]).read_text(encoding="utf-8"))
        gd = float(g["duration"])
        probed = SC.probe_duration(ROOT / g["local_source"])
        if probed > 0 and abs(probed - gd) > max(30.0, 0.05 * gd):
            mism.append((v["video_id"], gd, probed))
    if mism:
        print("[FATAL] gold.duration 与 ffprobe 实测偏差超阈值，中止：", flush=True)
        for vid, gd, pr in mism:
            print(f"  {vid}: gold={gd:.0f}s ffprobe={pr:.0f}s", flush=True)
        return 2

    rows = []
    for v in videos:
        gold = json.loads((ROOT / v["gold"]).read_text(encoding="utf-8"))
        gold_b = gold["boundaries_sec"]
        duration = float(gold["duration"])
        cc = SC.adaptive_chunk_chars(duration)
        src = str((ROOT / gold["local_source"]))
        print(f"\n=== {v['video_id']} ({v['domain']}) dur={duration:.0f}s cc={cc} ===", flush=True)
        for cond in conditions:
            if cond == "free-K":
                chap_arg = ["--chapters"]                       # bare = 自适应
            else:
                chap_arg = ["--chapters", str(gold["n_segments"])]  # given-K oracle
            t0 = time.time()
            pred, ok = _run_pipeline(v["video_id"], src, cc, chap_arg, cond, t0)
            rows.append(assemble_row(v["video_id"], v["domain"], cond, cc,
                                     pred, gold_b, duration, pipeline_failed=not ok))
            flag = "" if ok else "  [PIPELINE FAILED]"
            print(f"  [{cond}] pred_n={len(pred)+1} F1@15={rows[-1]['tol15']['F1']} "
                  f"Pk={rows[-1]['pk']} WD={rows[-1]['windowdiff']}{flag}", flush=True)

    header = {
        "metrics_version": E.METRICS_VERSION,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "commit": _git_commit(),
        "model": "Qwen2.5-7B-AWQ",
        "provider": "local",
        "static_pipeline_args": STATIC_ARGS,
        "chunk_chars_rule": "adaptive_chunk_chars(duration): <600s->400, <1500s->600, else 800",
        "chapters_arg": {"free-K": "--chapters (bare)", "given-K": "--chapters <n_segments>"},
        "results": rows,
    }
    OUT_JSON.write_text(json.dumps(header, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n写入 {OUT_JSON}（{len(rows)} 行）", flush=True)

    _write_report(aggregate(rows), header)
    print(f"报表写入 {REPORT_MD}", flush=True)
    return 0


def _write_report(agg: dict, header: dict) -> None:
    lines = ["# 切分基准报表", "",
             f"- run_at: {header['run_at']}  commit: `{header['commit']}`  "
             f"model: {header['model']} ({header['provider']})",
             f"- metrics_version: {header['metrics_version']}；主容差 ±15s，附 ±30s；Pk/WD 越低越好",
             f"- 滑窗遵 nltk 规范 `range(n-k+1)`；1s 单元离散（见 src/seg_eval.py）", "",
             "## 分档均值（learning 为主指标；vlog/english 作 OOD 参考）", "",
             "| domain | condition | n | F1@15 | F1@30 | Pk↓ | WD↓ |",
             "|---|---|---|---|---|---|---|"]
    for (dom, cond) in sorted(agg.keys()):
        a = agg[(dom, cond)]
        lines.append(f"| {dom} | {cond} | {a['n']} | {a['F1@15']:.3f} | "
                     f"{a['F1@30']:.3f} | {a['Pk']:.3f} | {a['WD']:.3f} |")
    lines += ["", "## free-K vs given-K（自适应定 K 的代价）", "",
              "given-K 给定 gold 章数作 oracle；free-K↔given-K 的 F1/Pk 差 + 各视频 "
              "`k_error`（见 benchmark_segmentation.json）量化「该切几章」误差与「边界放哪」误差。"]
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
