"""章节切分评估：chunker × alpha 双 ablation，8 视频 benchmark。

对每个视频，跑 chunker ∈ {chars, texttile} × alpha ∈ {0.0, 0.2, 0.3, 0.5, 0.7, 1.0}，
强制章节数 = num_chapters，对比预测边界与 gold 边界。
- 严格匹配：预测边界必须 == gold 边界
- 容差匹配（@1）：预测边界落在 gold 边界 ±1 段内算 TP

所有视频统一用 chunk_chars=400（更细粒度，让短视频也能切到合适 chunks 数评估）。
gold 边界按"chunk 序号 (1-indexed)"标注；不同 chunker 下 chunks 数量不同，
所以维护两套 gold（chars_gold / texttile_gold），分别评估各自 chunker 下的表现。
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
CHUNKERS = ["chars", "texttile"]
CHUNK_CHARS = 400

GOLDS = {
    # === 原 4 视频（在更细 chunk_chars=400 下重新标） ===
    "BV19E411D78Q_p38.f30280": {
        "video": "data/raw/BV19E411D78Q_p38.f30280.m4a",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural"],
        "num_chapters": 5,
        "label": "计网（PPT 教学, 30min）",
        "domain": "ppt",
        "chars_gold": [7, 14, 18, 22],
        "texttile_gold": [7, 14, 17, 20],
    },
    "BV1SddcBFESs_p0": {
        "video": "data/raw/BV1SddcBFESs_p0.mp4",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural",
                       "--term", "主绘画=主会话"],
        "num_chapters": 3,
        "label": "ClaudeCode（PPT 教学, 11min）",
        "domain": "ppt",
        "chars_gold": [5, 10],
        "texttile_gold": [5, 8],
    },
    "BV1G85V6cE1g_p0": {
        "video": "data/raw/BV1G85V6cE1g_p0.mp4",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural"],
        "num_chapters": 2,
        "label": "懂王评论（实拍解说, 7min）",
        "domain": "live",
        "chars_gold": [4],
        "texttile_gold": [3],
    },
    "BV1W8AGzwEFW_p0": {
        "video": "data/raw/BV1W8AGzwEFW_p0.mp4",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural"],
        "num_chapters": 5,
        "label": "外卖 Vlog（实拍, 17min）",
        "domain": "live",
        "chars_gold": [2, 4, 7, 9],
        "texttile_gold": [1, 2, 6, 7],
    },
    # === 新增 4 视频 ===
    "BV1x25P6tEKe_p0": {
        "video": "data/raw/BV1x25P6tEKe_p0.mp4",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural"],
        "num_chapters": 3,
        "label": "iOS 评测（数码科普, 10min）",
        "domain": "ppt",  # 屏幕展示主导
        "chars_gold": [2, 5],
        "texttile_gold": [2, 4],
    },
    "BV1XY546vE1o_p0": {
        "video": "data/raw/BV1XY546vE1o_p0.mp4",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural"],
        "num_chapters": 4,
        "label": "影视飓风×刘谦（多镜头, 14min）",
        "domain": "live",  # 专业拍摄多镜头
        "chars_gold": [4, 5, 7],
        "texttile_gold": [4, 5, 6],
    },
    "BV1cwdzBDEL3_p0": {
        "video": "data/raw/BV1cwdzBDEL3_p0.mp4",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural"],
        "num_chapters": 5,
        "label": "日本小镇 Vlog（实拍, 15min）",
        "domain": "live",
        "chars_gold": [1, 5, 9, 13],
        "texttile_gold": [1, 4, 8, 10],
    },
    "BV1ygo9BeEvV_p0": {
        "video": "data/raw/BV1ygo9BeEvV_p0.mp4",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural"],
        "num_chapters": 3,
        "label": "多 Agent 可视化（屏幕录制, 11min）",
        "domain": "ppt",  # 屏幕录制
        "chars_gold": [1, 5],
        "texttile_gold": [1, 4],
    },
    # === 2026-05-14 第二轮扩 benchmark：补 408/AI 科普两个学习类样本 ===
    "BV1YE411D7nH_p37_p0": {
        "video": "data/raw/BV1YE411D7nH_p37_p0.mp4",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural"],
        "num_chapters": 3,
        "label": "王道操作系统 哲学家进餐（408 PPT, 15min）",
        "domain": "ppt",
        # chars cc=400 12 chunks: chunk5 起=方案讨论(5:24); chunk11=总结(12:42)
        "chars_gold": [5, 11],
        # texttile cc=400 11 chunks: 同时间点映射 chunk5(5:02)/chunk10(12:35)
        "texttile_gold": [5, 10],
    },
    "BV1L24y1i7v3_p0": {
        "video": "data/raw/BV1L24y1i7v3_p0.mp4",
        "extra_args": ["--local", "--model", "large-v3", "--summarizer", "neural"],
        "num_chapters": 2,
        "label": "5分钟看懂深度学习（AI 科普, 5min）",
        "domain": "ppt",  # 屏幕图文为主
        # chars cc=400 4 chunks: chunk3=02:44 从概念转入百度产品
        "chars_gold": [3],
        # texttile cc=400 3 chunks: chunk2=02:44 同切点
        "texttile_gold": [2],
    },
}


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


def run_pipeline(cfg: dict, chunker: str, alpha: float) -> Path:
    cmd = [PY, "src/pipeline.py", cfg["video"], *cfg["extra_args"],
           "--chunk-chars", str(CHUNK_CHARS),
           "--chapters", str(cfg["num_chapters"]), "--keyframes",
           "--mm-alpha", str(alpha), "--chunker", chunker]
    subprocess.run(cmd, capture_output=True, check=False)
    audio_stem = Path(cfg["video"]).stem
    suffix = "" if chunker == "chars" else f".{chunker}"
    return Path(f"data/outputs/{audio_stem}.large-v3.neural{suffix}.chapters.json")


def main():
    rows = []
    for stem, cfg in GOLDS.items():
        print(f"\n========== {cfg['label']} ==========")
        for chunker in CHUNKERS:
            gold = cfg[f"{chunker}_gold"]
            print(f"\n  --- chunker={chunker} (gold={gold}, K={cfg['num_chapters']}) ---")
            print(f"  {'α':>4}  {'边界(预测)':<24} "
                  f"{'P':>5} {'R':>5} {'F1':>5}  | "
                  f"{'P@1':>5} {'R@1':>5} {'F1@1':>5}")
            print("  " + "-" * 70)
            for a in ALPHAS:
                ch_path = run_pipeline(cfg, chunker, a)
                if not ch_path.exists():
                    print(f"  {a:>4.1f}  [ERROR] {ch_path} 缺失")
                    continue
                data = json.load(open(ch_path, encoding="utf-8"))
                pred = [b + 1 for b in data["ablation"]["multimodal_boundaries"]]
                p, r, f1 = prf(pred, gold, tolerance=0)
                p1, r1, f11 = prf(pred, gold, tolerance=1)
                pred_str = str(pred)
                print(f"  {a:>4.1f}  {pred_str:<24} "
                      f"{p:>5.2f} {r:>5.2f} {f1:>5.2f}  | "
                      f"{p1:>5.2f} {r1:>5.2f} {f11:>5.2f}")
                rows.append({"video": stem, "chunker": chunker, "alpha": a,
                             "pred": pred, "gold": gold,
                             "K": cfg["num_chapters"],
                             "P": p, "R": r, "F1": f1,
                             "P@1": p1, "R@1": r1, "F1@1": f11,
                             "domain": cfg["domain"],
                             "label": cfg["label"]})

    out_path = Path("data/outputs/eval_segmentation.json")
    out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"\n>>> 评估数据已保存到 {out_path}")

    def print_avg(label: str, subset: list[dict]):
        if not subset:
            return
        n_videos = len(subset) // (len(ALPHAS) * len(CHUNKERS))
        print(f"\n========== {label}（n={n_videos} 视频）==========")
        for chunker in CHUNKERS:
            print(f"\n  chunker={chunker}")
            print(f"  {'α':>4}  {'P':>5} {'R':>5} {'F1':>5}  | "
                  f"{'P@1':>5} {'R@1':>5} {'F1@1':>5}")
            for a in ALPHAS:
                sub = [r for r in subset if r["alpha"] == a and r["chunker"] == chunker]
                if not sub:
                    continue
                avg = lambda k: sum(r[k] for r in sub) / len(sub)
                print(f"  {a:>4.1f}  "
                      f"{avg('P'):>5.2f} {avg('R'):>5.2f} {avg('F1'):>5.2f}  | "
                      f"{avg('P@1'):>5.2f} {avg('R@1'):>5.2f} {avg('F1@1'):>5.2f}")

    print_avg("PPT/屏幕展示视频", [r for r in rows if r["domain"] == "ppt"])
    print_avg("实拍视频", [r for r in rows if r["domain"] == "live"])
    print_avg("全部", rows)


if __name__ == "__main__":
    main()
