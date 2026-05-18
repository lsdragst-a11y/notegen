"""chunk_chars sweep ablation：固定 chunker=chars + α=0.0，扫 chunk_chars ∈ {200,400,600,800,1000}.

假设 H1：strict F1 随 chunk_chars 变细单调下降（量化噪声导致 chunk-level 评估在细粒度下不公平）
假设 H2：F1@1 容差指标相对稳定（容差吃掉量化噪声）

Gold 自动映射：每个视频的"语义章节边界时间"从 chunk_chars=400 下的 chars gold 反查出来；
在新 chunk_chars 下，找最接近这些时间的 chunk 边界 idx 作为新 gold。这样保持 gold 在
不同 chunk_chars 间语义一致，避免人工标 40 套。
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PY = r"C:\Users\19145\miniconda3\envs\notegen\python.exe"
CHUNK_CHARS_SWEEP = [200, 400, 600, 800, 1000]
ALPHA = 0.0
CHUNKER = "chars"

# 从 eval_segmentation.py 复用 8 视频配置（chars_gold 在 chunk_chars=400 下）
GOLDS = {
    "BV19E411D78Q_p38.f30280": {
        "video": "data/raw/BV19E411D78Q_p38.f30280.m4a",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural"],
        "num_chapters": 5,
        "label": "计网（PPT, 30min）",
        "domain": "ppt",
        "chars_gold_at_400": [7, 14, 18, 22],
    },
    "BV1SddcBFESs_p0": {
        "video": "data/raw/BV1SddcBFESs_p0.mp4",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural",
                       "--term", "主绘画=主会话"],
        "num_chapters": 3,
        "label": "ClaudeCode（PPT, 11min）",
        "domain": "ppt",
        "chars_gold_at_400": [5, 10],
    },
    "BV1G85V6cE1g_p0": {
        "video": "data/raw/BV1G85V6cE1g_p0.mp4",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural"],
        "num_chapters": 2,
        "label": "懂王（实拍, 7min）",
        "domain": "live",
        "chars_gold_at_400": [4],
    },
    "BV1W8AGzwEFW_p0": {
        "video": "data/raw/BV1W8AGzwEFW_p0.mp4",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural"],
        "num_chapters": 5,
        "label": "外卖 Vlog（实拍, 17min）",
        "domain": "live",
        "chars_gold_at_400": [2, 4, 7, 9],
    },
    "BV1x25P6tEKe_p0": {
        "video": "data/raw/BV1x25P6tEKe_p0.mp4",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural"],
        "num_chapters": 3,
        "label": "iOS（科普, 10min）",
        "domain": "ppt",
        "chars_gold_at_400": [2, 5],
    },
    "BV1XY546vE1o_p0": {
        "video": "data/raw/BV1XY546vE1o_p0.mp4",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural"],
        "num_chapters": 4,
        "label": "影视飓风（多镜头, 14min）",
        "domain": "live",
        "chars_gold_at_400": [4, 5, 7],
    },
    "BV1cwdzBDEL3_p0": {
        "video": "data/raw/BV1cwdzBDEL3_p0.mp4",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural"],
        "num_chapters": 5,
        "label": "日本 Vlog（实拍, 15min）",
        "domain": "live",
        "chars_gold_at_400": [1, 5, 9, 13],
    },
    "BV1ygo9BeEvV_p0": {
        "video": "data/raw/BV1ygo9BeEvV_p0.mp4",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural"],
        "num_chapters": 3,
        "label": "多 Agent（编程, 11min）",
        "domain": "ppt",
        "chars_gold_at_400": [1, 5],
    },
}


def derive_boundary_times(stem: str, gold_chunk_idx: list[int]) -> list[float]:
    """从 chunk_chars=400 下的 chars summary.json 反查 gold 边界的时间点。
    gold idx i (1-indexed) 表示"第 i 个 chunk 之后切"，即 chunks[i-1].end。
    """
    path = Path(f"data/outputs/{stem}.large-v3.neural.summary.json")
    chunks = json.loads(path.read_text(encoding="utf-8"))
    return [float(chunks[i - 1]["end"]) for i in gold_chunk_idx]


def map_times_to_gold(chunks: list[dict], boundary_times: list[float]) -> list[int]:
    """给定 chunks 列表，把语义边界时间映射到最近的 chunk 边界 idx (1-indexed)。
    候选边界 i：chunks[i-1] 之后切，时间近似 chunks[i-1].end。
    """
    n = len(chunks)
    candidates = [(i, float(chunks[i - 1]["end"])) for i in range(1, n)]
    if not candidates:
        return []
    gold = []
    for t in boundary_times:
        best_i = min(candidates, key=lambda c: abs(c[1] - t))[0]
        gold.append(best_i)
    return sorted(set(gold))


def prf(pred: list[int], gold: list[int], tolerance: int = 0) -> tuple[float, float, float]:
    if tolerance == 0:
        tp = len(set(pred) & set(gold))
    else:
        used = set()
        tp = 0
        for p in pred:
            for g in gold:
                if g in used:
                    continue
                if abs(p - g) <= tolerance:
                    tp += 1
                    used.add(g)
                    break
    p = tp / max(len(pred), 1)
    r = tp / max(len(gold), 1)
    f1 = 2 * p * r / max(p + r, 1e-9)
    return p, r, f1


def run_pipeline(cfg: dict, chunk_chars: int) -> tuple[Path, Path]:
    cmd = [PY, "src/pipeline.py", cfg["video"], *cfg["extra_args"],
           "--chunk-chars", str(chunk_chars),
           "--chapters", str(cfg["num_chapters"]), "--keyframes",
           "--mm-alpha", str(ALPHA), "--chunker", CHUNKER]
    subprocess.run(cmd, capture_output=True, check=False)
    audio_stem = Path(cfg["video"]).stem
    return (Path(f"data/outputs/{audio_stem}.large-v3.neural.summary.json"),
            Path(f"data/outputs/{audio_stem}.large-v3.neural.chapters.json"))


def main():
    print("=" * 80)
    print(f"chunk_chars sweep ablation: chunker={CHUNKER}, α={ALPHA}")
    print(f"sweep: {CHUNK_CHARS_SWEEP}")
    print("=" * 80)

    # 第 1 步：在 chunk_chars=400 下反查每个视频的"边界时间"
    print("\n--- Step 1: derive boundary times from chunk_chars=400 gold ---")
    for stem, cfg in GOLDS.items():
        times = derive_boundary_times(stem, cfg["chars_gold_at_400"])
        cfg["boundary_times"] = times
        time_strs = [f"{t / 60:.2f}min" for t in times]
        print(f"  {cfg['label']}: gold@400={cfg['chars_gold_at_400']} -> times={time_strs}")

    # 第 2 步：sweep
    rows = []
    for stem, cfg in GOLDS.items():
        print(f"\n========== {cfg['label']} ==========")
        print(f"  {'cc':>5}  {'n_chunks':>9} {'auto_gold':<18} {'pred':<18} "
              f"{'F1':>5} {'F1@1':>5}")
        print("  " + "-" * 70)
        for cc in CHUNK_CHARS_SWEEP:
            summary_path, chapters_path = run_pipeline(cfg, cc)
            if not summary_path.exists() or not chapters_path.exists():
                print(f"  {cc:>5}  [ERROR] 文件缺失")
                continue
            chunks = json.loads(summary_path.read_text(encoding="utf-8"))
            data = json.loads(chapters_path.read_text(encoding="utf-8"))
            auto_gold = map_times_to_gold(chunks, cfg["boundary_times"])
            pred = [b + 1 for b in data["ablation"]["multimodal_boundaries"]]
            p, r, f1 = prf(pred, auto_gold, tolerance=0)
            p1, r1, f11 = prf(pred, auto_gold, tolerance=1)
            print(f"  {cc:>5}  {len(chunks):>9} {str(auto_gold):<18} "
                  f"{str(pred):<18} {f1:>5.2f} {f11:>5.2f}")
            rows.append({"video": stem, "chunk_chars": cc, "n_chunks": len(chunks),
                         "auto_gold": auto_gold, "pred": pred, "K": cfg["num_chapters"],
                         "P": p, "R": r, "F1": f1,
                         "P@1": p1, "R@1": r1, "F1@1": f11,
                         "domain": cfg["domain"]})

    out_path = Path("data/outputs/eval_chunk_chars_sweep.json")
    out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"\n>>> 数据保存到 {out_path}")

    # 汇总
    print("\n" + "=" * 60)
    print("=== 跨视频汇总 ===")
    print("=" * 60)
    for label, sub in [("PPT/screen", [r for r in rows if r["domain"] == "ppt"]),
                        ("实拍", [r for r in rows if r["domain"] == "live"]),
                        ("全部", rows)]:
        n_videos = len(sub) // len(CHUNK_CHARS_SWEEP)
        print(f"\n{label}（n={n_videos} 视频）")
        print(f"  {'cc':>5}  {'n_chunks_avg':>13} {'F1':>5} {'F1@1':>5}")
        for cc in CHUNK_CHARS_SWEEP:
            s = [r for r in sub if r["chunk_chars"] == cc]
            if not s:
                continue
            avg = lambda k: sum(r[k] for r in s) / len(s)
            print(f"  {cc:>5}  {avg('n_chunks'):>13.1f} "
                  f"{avg('F1'):>5.2f} {avg('F1@1'):>5.2f}")


if __name__ == "__main__":
    main()
