"""8 视频 × texttile × chunk_chars=800 × alpha sweep。

闭合 chunker × cc 联合 ablation：现在已有
- (chars, cc=400) × alpha sweep（eval_segmentation.json）
- (texttile, cc=400) × alpha sweep（eval_segmentation.json）
- (chars, cc=800) × α=0.0 单点（eval_chunk_chars_sweep.json）

补 (texttile, cc=800) × alpha sweep，让 chunker × cc 主操作点对比成立。

Gold 用 boundary_times 自动映射（与 chunk_chars 解耦）。
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PY = r"C:\Users\19145\miniconda3\envs\notegen\python.exe"
ALPHAS = [0.0, 0.2, 0.3, 0.5, 0.7, 1.0]
CHUNK_CHARS = 800
CHUNKER = "texttile"

# 复用 sweep 脚本的 GOLDS（chars_gold_at_400 → 反查出 boundary_times）
GOLDS = {
    "BV19E411D78Q_p38.f30280": {"video": "data/raw/BV19E411D78Q_p38.f30280.m4a",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural"],
        "num_chapters": 5, "label": "计网（PPT, 30min）", "domain": "ppt",
        "chars_gold_at_400": [7, 14, 18, 22]},
    "BV1SddcBFESs_p0": {"video": "data/raw/BV1SddcBFESs_p0.mp4",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural",
                       "--term", "主绘画=主会话"],
        "num_chapters": 3, "label": "ClaudeCode（PPT, 11min）", "domain": "ppt",
        "chars_gold_at_400": [5, 10]},
    "BV1G85V6cE1g_p0": {"video": "data/raw/BV1G85V6cE1g_p0.mp4",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural"],
        "num_chapters": 2, "label": "懂王（实拍, 7min）", "domain": "live",
        "chars_gold_at_400": [4]},
    "BV1W8AGzwEFW_p0": {"video": "data/raw/BV1W8AGzwEFW_p0.mp4",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural"],
        "num_chapters": 5, "label": "外卖 Vlog（实拍, 17min）", "domain": "live",
        "chars_gold_at_400": [2, 4, 7, 9]},
    "BV1x25P6tEKe_p0": {"video": "data/raw/BV1x25P6tEKe_p0.mp4",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural"],
        "num_chapters": 3, "label": "iOS（科普, 10min）", "domain": "ppt",
        "chars_gold_at_400": [2, 5]},
    "BV1XY546vE1o_p0": {"video": "data/raw/BV1XY546vE1o_p0.mp4",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural"],
        "num_chapters": 4, "label": "影视飓风（多镜头, 14min）", "domain": "live",
        "chars_gold_at_400": [4, 5, 7]},
    "BV1cwdzBDEL3_p0": {"video": "data/raw/BV1cwdzBDEL3_p0.mp4",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural"],
        "num_chapters": 5, "label": "日本 Vlog（实拍, 15min）", "domain": "live",
        "chars_gold_at_400": [1, 5, 9, 13]},
    "BV1ygo9BeEvV_p0": {"video": "data/raw/BV1ygo9BeEvV_p0.mp4",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural"],
        "num_chapters": 3, "label": "多 Agent（编程, 11min）", "domain": "ppt",
        "chars_gold_at_400": [1, 5]},
    # === 2026-05-14 第二轮扩 benchmark ===
    "BV1YE411D7nH_p37_p0": {"video": "data/raw/BV1YE411D7nH_p37_p0.mp4",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural"],
        "num_chapters": 3, "label": "王道OS 哲学家（408 PPT, 15min）", "domain": "ppt",
        "chars_gold_at_400": [5, 11]},
    "BV1L24y1i7v3_p0": {"video": "data/raw/BV1L24y1i7v3_p0.mp4",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural"],
        "num_chapters": 2, "label": "深度学习科普（AI, 5min）", "domain": "ppt",
        "chars_gold_at_400": [3]},
}


def derive_boundary_times(stem: str, gold_idx: list[int]) -> list[float]:
    """从已存在的 chars @ cc=400 summary.json 反查边界时间。
    注意：当前 summary.json 可能不是 cc=400 状态（sweep 跑完后是 cc=1000）。
    所以我们需要先在 cc=400 + chars 下重跑一次，或直接从已存的 eval_segmentation
    路径复用——eval_segmentation.json 不存 chunk start/end。最稳是临时 rerun。
    简化：直接相信 chars_gold_at_400 + 视频总时长，按等比例估计边界时间。
    """
    # 退而求其次：用比例估计——chars cc=400 下章节边界 chunk idx i 对应大约的时间
    # 但这不可靠。我们直接 rerun cc=400 chars 拿 chunks。
    raise NotImplementedError


def rerun_at_cc400_chars(cfg: dict) -> list[dict]:
    """在 chunk_chars=400 + chars 下重跑一次拿 chunks。"""
    cmd = [PY, "src/pipeline.py", cfg["video"], *cfg["extra_args"],
           "--chunk-chars", "400",
           "--chapters", str(cfg["num_chapters"]), "--keyframes",
           "--mm-alpha", "0.0", "--chunker", "chars"]
    subprocess.run(cmd, capture_output=True, check=False)
    audio_stem = Path(cfg["video"]).stem
    p = Path(f"data/outputs/{audio_stem}.large-v3.neural.summary.json")
    return json.loads(p.read_text(encoding="utf-8"))


def boundary_times_from_chunks(chunks: list[dict], gold_idx: list[int]) -> list[float]:
    return [float(chunks[i - 1]["end"]) for i in gold_idx]


def map_times_to_gold(chunks: list[dict], times: list[float]) -> list[int]:
    n = len(chunks)
    cands = [(i, float(chunks[i - 1]["end"])) for i in range(1, n)]
    if not cands:
        return []
    out = []
    for t in times:
        best_i = min(cands, key=lambda c: abs(c[1] - t))[0]
        out.append(best_i)
    return sorted(set(out))


def prf(pred: list[int], gold: list[int], tol: int = 0) -> tuple[float, float, float]:
    if tol == 0:
        tp = len(set(pred) & set(gold))
    else:
        used = set()
        tp = 0
        for p in pred:
            for g in gold:
                if g in used:
                    continue
                if abs(p - g) <= tol:
                    tp += 1
                    used.add(g)
                    break
    p = tp / max(len(pred), 1)
    r = tp / max(len(gold), 1)
    f1 = 2 * p * r / max(p + r, 1e-9)
    return p, r, f1


def run_pipeline(cfg: dict, alpha: float) -> tuple[Path, Path]:
    cmd = [PY, "src/pipeline.py", cfg["video"], *cfg["extra_args"],
           "--chunk-chars", str(CHUNK_CHARS),
           "--chapters", str(cfg["num_chapters"]), "--keyframes",
           "--mm-alpha", str(alpha), "--chunker", CHUNKER]
    subprocess.run(cmd, capture_output=True, check=False)
    audio_stem = Path(cfg["video"]).stem
    return (Path(f"data/outputs/{audio_stem}.large-v3.neural.texttile.summary.json"),
            Path(f"data/outputs/{audio_stem}.large-v3.neural.texttile.chapters.json"))


def main():
    print(f"=== chunker={CHUNKER} × chunk_chars={CHUNK_CHARS} × alpha sweep ===\n")

    # Step 1: 重跑每个视频 cc=400 chars 拿 chunks → boundary_times
    print("--- Step 1: derive boundary times (rerun chars @ cc=400) ---")
    for stem, cfg in GOLDS.items():
        chunks = rerun_at_cc400_chars(cfg)
        times = boundary_times_from_chunks(chunks, cfg["chars_gold_at_400"])
        cfg["boundary_times"] = times
        print(f"  {cfg['label']}: {[f'{t/60:.2f}min' for t in times]}")

    # Step 2: texttile @ cc=800 全 alpha sweep
    rows = []
    for stem, cfg in GOLDS.items():
        print(f"\n========== {cfg['label']} ==========")
        print(f"  {'α':>4}  {'auto_gold':<14} {'pred':<14} "
              f"{'F1':>5} {'F1@1':>5}")
        print("  " + "-" * 50)
        for a in ALPHAS:
            sum_path, ch_path = run_pipeline(cfg, a)
            if not (sum_path.exists() and ch_path.exists()):
                continue
            chunks = json.loads(sum_path.read_text(encoding="utf-8"))
            data = json.loads(ch_path.read_text(encoding="utf-8"))
            auto_gold = map_times_to_gold(chunks, cfg["boundary_times"])
            pred = [b + 1 for b in data["ablation"]["multimodal_boundaries"]]
            p, r, f1 = prf(pred, auto_gold, 0)
            p1, r1, f11 = prf(pred, auto_gold, 1)
            print(f"  {a:>4.1f}  {str(auto_gold):<14} {str(pred):<14} "
                  f"{f1:>5.2f} {f11:>5.2f}")
            rows.append({"video": stem, "chunker": CHUNKER,
                         "chunk_chars": CHUNK_CHARS, "alpha": a,
                         "n_chunks": len(chunks),
                         "auto_gold": auto_gold, "pred": pred,
                         "P": p, "R": r, "F1": f1,
                         "P@1": p1, "R@1": r1, "F1@1": f11,
                         "domain": cfg["domain"]})

    out_path = Path("data/outputs/eval_texttile_cc800.json")
    out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"\n>>> 数据保存到 {out_path}")

    print("\n=== 跨视频汇总 (texttile @ cc=800) ===")
    for label, sub in [("PPT/screen", [r for r in rows if r["domain"] == "ppt"]),
                        ("实拍", [r for r in rows if r["domain"] == "live"]),
                        ("全部", rows)]:
        n_videos = len(sub) // len(ALPHAS) if sub else 0
        print(f"\n{label}（n={n_videos}）")
        print(f"  {'α':>4}  {'F1':>5} {'F1@1':>5}")
        for a in ALPHAS:
            s = [r for r in sub if r["alpha"] == a]
            if not s:
                continue
            avg = lambda k: sum(r[k] for r in s) / len(s)
            print(f"  {a:>4.1f}  {avg('F1'):>5.2f} {avg('F1@1'):>5.2f}")


if __name__ == "__main__":
    main()
