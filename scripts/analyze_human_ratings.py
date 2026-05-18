"""分析人工打分 vs 自动指标的关联。

用户给 30 个 headline 打了 5 分制评分，本脚本：
1. 算 chars vs texttile 平均分对比
2. 算各自动指标（关键词覆盖 / 长度合规 / 含 trailing 词）与主观分的相关性
3. 列出高分/低分代表，找失败模式
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import jieba.analyse  # noqa: E402

# 用户 2026-05-14 给的 30 个评分
RATINGS = [3, 3, 5, 3, 2, 4, 5, 4, 4, 5, 5, 4, 4, 2, 2, 2, 1, 3, 1, 3,
           2, 1, 3, 1, 5, 4, 5, 5, 5, 4]


def length_ok(h: str) -> bool:
    return 8 <= len(h) <= 25


def keyword_coverage(h: str, chunk_text: str, k: int = 3) -> float:
    kws = jieba.analyse.extract_tags(chunk_text, topK=k)
    if not kws:
        return 0.0
    return sum(1 for kw in kws if kw in h) / len(kws)


def correlation(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx2 = sum((x - mx) ** 2 for x in xs)
    sy2 = sum((y - my) ** 2 for y in ys)
    if sx2 == 0 or sy2 == 0:
        return 0.0
    return num / ((sx2 ** 0.5) * (sy2 ** 0.5))


def main():
    sample = json.loads(Path("data/outputs/headline_rating_sample.json")
                        .read_text(encoding="utf-8"))
    assert len(sample) == len(RATINGS), f"{len(sample)} vs {len(RATINGS)}"

    # 给每条加 rating + 自动指标
    rows = []
    for r, item in zip(RATINGS, sample):
        h = item["headline"]
        ctx = item["context"]
        rows.append({
            **item,
            "rating": r,
            "len": len(h),
            "len_ok": length_ok(h),
            "coverage": keyword_coverage(h, ctx),
        })

    # 1. chars vs texttile 平均分
    print("=" * 60)
    print("=== 人工评分：chars vs texttile ===")
    print("=" * 60)
    for chunker in ["chars", "texttile"]:
        s = [r for r in rows if r["chunker"] == chunker]
        avg = sum(r["rating"] for r in s) / len(s)
        ok_rate = sum(1 for r in s if r["rating"] >= 4) / len(s)
        bad_rate = sum(1 for r in s if r["rating"] <= 2) / len(s)
        print(f"  {chunker:<9} n={len(s)}  均分={avg:.2f}  "
              f"≥4 优秀%={ok_rate * 100:.0f}%  ≤2 失败%={bad_rate * 100:.0f}%")

    # 2. 各域人工评分
    print("\n=== 按 domain（PPT/screen vs 实拍）===")
    domain_map = {
        "计网": "ppt", "ClaudeCode": "ppt", "iOS": "ppt", "多Agent": "ppt",
        "懂王": "live", "外卖": "live", "影视飓风": "live", "日本Vlog": "live",
    }
    for r in rows:
        r["domain"] = domain_map.get(r["video"], "?")
    for domain in ["ppt", "live"]:
        s = [r for r in rows if r["domain"] == domain]
        avg = sum(r["rating"] for r in s) / len(s)
        print(f"  {domain:<6}  n={len(s):>2}  均分={avg:.2f}")

    # 3. 自动指标 vs 人工分相关性
    print("\n=== 自动指标 ↔ 人工分 相关性 (Pearson) ===")
    ratings_f = [float(r["rating"]) for r in rows]
    for key, vals_fn in [
        ("len_ok (1=合规)", lambda r: 1.0 if r["len_ok"] else 0.0),
        ("len (字符数)",   lambda r: float(r["len"])),
        ("coverage (0-1)", lambda r: r["coverage"]),
    ]:
        vals = [vals_fn(r) for r in rows]
        corr = correlation(vals, ratings_f)
        print(f"  {key:<20s}  r = {corr:+.3f}")

    # 4. 失败案例
    print("\n=== 失败案例 (rating ≤ 2) ===")
    fails = [r for r in rows if r["rating"] <= 2]
    for r in fails:
        print(f"  [{r['rating']}] {r['video']}/{r['chunker']:<8s}  "
              f"headline=\"{r['headline'][:40]}\"  "
              f"cov={r['coverage']:.2f}")

    # 5. 高分案例
    print("\n=== 高分案例 (rating = 5) ===")
    excellents = [r for r in rows if r["rating"] == 5]
    for r in excellents:
        print(f"  [{r['rating']}] {r['video']}/{r['chunker']:<8s}  "
              f"headline=\"{r['headline'][:40]}\"  "
              f"cov={r['coverage']:.2f}")

    # 6. domain × chunker
    print("\n=== domain × chunker 矩阵 (均分) ===")
    print(f"  {'':<10s} {'chars':>7s} {'texttile':>9s}")
    for domain in ["ppt", "live"]:
        line = f"  {domain:<10s}"
        for chunker in ["chars", "texttile"]:
            s = [r for r in rows if r["domain"] == domain and r["chunker"] == chunker]
            avg = sum(r["rating"] for r in s) / len(s) if s else 0
            line += f"  {avg:>5.2f} ({len(s):>2}) "
        print(line)

    # 保存带 rating 的完整数据
    out = Path("data/outputs/headline_rating_analysis.json")
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"\n>>> 分析数据保存到 {out}")


if __name__ == "__main__":
    main()
