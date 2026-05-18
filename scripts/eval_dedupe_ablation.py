"""dedupe on/off 的轻量 ablation。

复用现有 ASR cache，跳过 Pegasus / CLIP / multimodal fusion，
只跑 (optional dedupe) → chunker → keywords → detect_boundaries (alpha=0 纯文本)
→ P/R/F1/F1@1。

设计目的：量化本 session 加的 dedupe LCP 改动对 segmentation 的净收益，
看哪些视频受益、哪些回归。比 eval_segmentation.py 快 ~100×。
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from asr import dedupe_consecutive_segments  # noqa: E402
from summarize import chunk_by_chars, chunk_by_texttile, keywords_for  # noqa: E402
from segment import detect_boundaries  # noqa: E402

# 复用 eval_segmentation.py 的 gold（部分）
from eval_segmentation import GOLDS  # noqa: E402

CHUNK_CHARS_OPTS = [400, 800]
CHUNKERS = ["chars", "texttile"]


def asr_path_for(stem: str) -> Path | None:
    """从 video stem 推断 ASR cache 路径。"""
    direct = Path(f"data/outputs/{stem}.large-v3.asr.json")
    if direct.exists():
        return direct
    # 计网 p38 用 .f30280 后缀
    for variant in [f"{stem}", f"{stem}.f30280"]:
        p = Path(f"data/outputs/{variant}.large-v3.asr.json")
        if p.exists():
            return p
    return None


def prf(pred: list[int], gold: list[int],
        tolerance: int = 0) -> tuple[float, float, float]:
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


def run_one(segs: list[dict], chunker: str, cc: int, K: int):
    if chunker == "chars":
        chunks = chunk_by_chars(segs, chunk_chars=cc)
    else:
        chunks = chunk_by_texttile(segs, target_chunk_chars=cc)
    for c in chunks:
        c["keywords"] = keywords_for(c["text"])
    bounds_idx = detect_boundaries(chunks, num_chapters=K)
    return chunks, [b + 1 for b in bounds_idx]


def main():
    rows = []
    for stem, cfg in GOLDS.items():
        ap = asr_path_for(stem)
        if ap is None:
            print(f"[{stem}] ASR cache 缺失，跳过")
            continue
        asr = json.loads(ap.read_text(encoding="utf-8"))
        K = cfg["num_chapters"]

        for cc in CHUNK_CHARS_OPTS:
            for chunker in CHUNKERS:
                gold = cfg.get(f"{chunker}_gold", [])
                # cc=800 时 gold 不一定适用（gold 是按 cc=400 chunks 标的）
                # 暂时复用，输出时分开报告
                for dd_label, segs in [
                    ("off", asr["segments"]),
                    ("on",
                     dedupe_consecutive_segments(asr)[0]["segments"]),
                ]:
                    chunks, pred = run_one(segs, chunker, cc, K)
                    p, r, f1 = prf(pred, gold, 0)
                    p1, r1, f11 = prf(pred, gold, 1)
                    rows.append({
                        "video": stem, "chunker": chunker, "cc": cc,
                        "dedupe": dd_label, "K": K, "n_chunks": len(chunks),
                        "pred": pred, "gold": gold,
                        "F1": f1, "F1@1": f11, "P@1": p1, "R@1": r1,
                        "domain": cfg["domain"],
                    })

    out_path = Path("data/outputs/eval_dedupe_ablation.json")
    out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"\n>>> {len(rows)} rows -> {out_path}")

    # 主表 1：cc=800 主操作点上 dedupe on vs off 全 10 视频均值
    print("\n========== 主表：dedupe on vs off (alpha=0 纯文本) ==========")
    for cc in CHUNK_CHARS_OPTS:
        for chunker in CHUNKERS:
            print(f"\n  chunker={chunker} cc={cc}")
            print(f"  {'subset':<8} {'n':>3} {'F1(off)':>8} {'F1(on)':>8} "
                  f"{'ΔF1':>6}   {'F1@1(off)':>10} {'F1@1(on)':>10} {'ΔF1@1':>7}")
            for subset_name, filter_fn in [
                ("ppt", lambda r: r["domain"] == "ppt"),
                ("live", lambda r: r["domain"] == "live"),
                ("all", lambda r: True),
            ]:
                off = [r for r in rows if r["chunker"] == chunker
                       and r["cc"] == cc and r["dedupe"] == "off"
                       and filter_fn(r)]
                on = [r for r in rows if r["chunker"] == chunker
                      and r["cc"] == cc and r["dedupe"] == "on"
                      and filter_fn(r)]
                if not off:
                    continue
                n = len(off)
                f1_off = sum(r["F1"] for r in off) / n
                f1_on = sum(r["F1"] for r in on) / n
                f11_off = sum(r["F1@1"] for r in off) / n
                f11_on = sum(r["F1@1"] for r in on) / n
                print(f"  {subset_name:<8} {n:>3} "
                      f"{f1_off:>8.3f} {f1_on:>8.3f} {f1_on - f1_off:>+6.3f}   "
                      f"{f11_off:>10.3f} {f11_on:>10.3f} {f11_on - f11_off:>+7.3f}")

    # 主表 2：dedupe 对各 affected video 影响明细
    print("\n========== 受 dedupe 影响的视频（cc=800 texttile）==========")
    affected = []
    for stem in GOLDS:
        on = next((r for r in rows if r["video"] == stem
                   and r["chunker"] == "texttile" and r["cc"] == 800
                   and r["dedupe"] == "on"), None)
        off = next((r for r in rows if r["video"] == stem
                    and r["chunker"] == "texttile" and r["cc"] == 800
                    and r["dedupe"] == "off"), None)
        if on and off and on["pred"] != off["pred"]:
            affected.append((stem, off, on))
    if affected:
        for stem, off, on in affected:
            print(f"  {stem}:")
            print(f"    off: pred={off['pred']} F1={off['F1']:.2f} F1@1={off['F1@1']:.2f}")
            print(f"    on : pred={on['pred']} F1={on['F1']:.2f} F1@1={on['F1@1']:.2f}")
    else:
        print("  (no affected videos at cc=800 texttile)")


if __name__ == "__main__":
    main()
