"""Headline 质量自动评估，跨 8 视频 × 2 chunker。

4 项指标（不需要 reference）：
1. 长度合理性：8 ≤ len ≤ 25 字（Pegasus 训练目标范围；过短=信息不够，过长=没压缩）
2. 关键词覆盖：headline 是否含 chunk 文本的 top-3 jieba 关键词（衡量主旨抓取）
3. 跨 headline 冗余：相邻 headline 关键词 Jaccard 相似度（高=boilerplate 漂移）
4. 悬空连接词率：headline 末尾是否带"也就是要 / 这个 / 因为"等 trailing 词

输入：data/outputs/<stem>.large-v3.neural[.texttile].summary.json
输出：data/outputs/eval_headlines.json + 控制台跨视频/chunker 汇总
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import jieba.analyse  # noqa: E402

VIDEOS = [
    ("BV19E411D78Q_p38.f30280", "计网（PPT, 30min）", "ppt"),
    ("BV1SddcBFESs_p0",          "ClaudeCode（PPT, 11min）", "ppt"),
    ("BV1G85V6cE1g_p0",          "懂王（实拍, 7min）", "live"),
    ("BV1W8AGzwEFW_p0",          "外卖 Vlog（实拍, 17min）", "live"),
    ("BV1x25P6tEKe_p0",          "iOS（科普, 10min）", "ppt"),
    ("BV1XY546vE1o_p0",          "影视飓风（多镜头, 14min）", "live"),
    ("BV1cwdzBDEL3_p0",          "日本 Vlog（实拍, 15min）", "live"),
    ("BV1ygo9BeEvV_p0",          "多 Agent（编程, 11min）", "ppt"),
    # 2026-05-14 第二轮扩 benchmark
    ("BV1YE411D7nH_p37_p0",      "王道OS 哲学家（408 PPT, 15min）", "ppt"),
    ("BV1L24y1i7v3_p0",          "深度学习科普（AI, 5min）", "ppt"),
]

# 第 11 条 post_clean_headline 的 TRAILING_DROP 列表，加上常见口语连接词
TRAILING_BAD = [
    "也就是要", "比如说", "也就是", "什么的", "因为", "等等",
    "就是说", "这个", "那个", "也就", "那么", "然后",
    "对吧", "什么", "怎么",
]


def length_ok(h: str) -> bool:
    return 8 <= len(h) <= 25


def keyword_coverage(h: str, chunk_text: str, k: int = 3) -> float:
    kws = jieba.analyse.extract_tags(chunk_text, topK=k)
    if not kws:
        return 0.0
    return sum(1 for kw in kws if kw in h) / len(kws)


def trailing_bad(h: str) -> str | None:
    """返回触发的 trailing 词，没有返回 None。"""
    for w in sorted(TRAILING_BAD, key=lambda x: -len(x)):
        if h.endswith(w):
            return w
    return None


def adjacent_jaccard(headlines: list[str], topk: int = 5) -> list[float]:
    """相邻 headlines 的 keyword Jaccard——衡量冗余。高=boilerplate 漂移。"""
    if len(headlines) < 2:
        return []
    keysets = [set(jieba.analyse.extract_tags(h, topK=topk)) for h in headlines]
    out = []
    for i in range(len(keysets) - 1):
        a, b = keysets[i], keysets[i + 1]
        if not a and not b:
            out.append(0.0)
        else:
            out.append(len(a & b) / max(len(a | b), 1))
    return out


def load_summary(stem: str, chunker: str) -> list[dict]:
    suffix = "" if chunker == "chars" else f".{chunker}"
    path = Path(f"data/outputs/{stem}.large-v3.neural{suffix}.summary.json")
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def eval_video(stem: str, label: str, domain: str, chunker: str) -> dict:
    chunks = load_summary(stem, chunker)
    headlines = [c.get("headline", "").strip() for c in chunks]
    n = len(headlines)
    if n == 0:
        return {}

    # 1. 长度
    lengths = [len(h) for h in headlines]
    len_ok_rate = sum(1 for h in headlines if length_ok(h)) / n

    # 2. 关键词覆盖
    covs = [keyword_coverage(h, c["text"]) for h, c in zip(headlines, chunks)]
    cov_mean = sum(covs) / n

    # 3. 相邻冗余
    jac = adjacent_jaccard(headlines)
    jac_mean = sum(jac) / len(jac) if jac else 0.0
    jac_max = max(jac) if jac else 0.0

    # 4. 悬空连接词
    bads = [trailing_bad(h) for h in headlines]
    bad_count = sum(1 for b in bads if b is not None)
    bad_rate = bad_count / n

    return {
        "video": stem, "label": label, "domain": domain, "chunker": chunker,
        "n_headlines": n,
        "len_mean": sum(lengths) / n, "len_min": min(lengths), "len_max": max(lengths),
        "len_ok_rate": len_ok_rate,
        "coverage_mean": cov_mean,
        "redundancy_mean": jac_mean, "redundancy_max": jac_max,
        "trailing_bad_rate": bad_rate, "trailing_bad_count": bad_count,
        "headlines": headlines,
        "bad_examples": [(h, b) for h, b in zip(headlines, bads) if b],
    }


def main():
    rows = []
    print("=" * 90)
    print(f"{'视频':<28} {'chunker':<9} {'n':>3} "
          f"{'len 均/区间':<14} {'len_ok%':>7} "
          f"{'cov%':>5} {'红余%':>5} {'红余max%':>7} {'尾词%':>5}")
    print("=" * 90)
    for stem, label, domain in VIDEOS:
        for chunker in ["chars", "texttile"]:
            r = eval_video(stem, label, domain, chunker)
            if not r:
                continue
            rows.append(r)
            print(f"{label:<28} {chunker:<9} {r['n_headlines']:>3} "
                  f"{r['len_mean']:>5.1f}/{r['len_min']:>2}-{r['len_max']:>2}    "
                  f"{r['len_ok_rate'] * 100:>6.0f}% "
                  f"{r['coverage_mean'] * 100:>4.0f}% "
                  f"{r['redundancy_mean'] * 100:>4.0f}% "
                  f"{r['redundancy_max'] * 100:>6.0f}% "
                  f"{r['trailing_bad_rate'] * 100:>4.0f}%")

    # 汇总
    print("\n" + "=" * 60)
    print("=== 跨视频汇总 ===")
    print("=" * 60)
    for label, sub in [("PPT/screen", [r for r in rows if r["domain"] == "ppt"]),
                        ("实拍",       [r for r in rows if r["domain"] == "live"]),
                        ("全部",       rows)]:
        print(f"\n{label}（n={len({r['video'] for r in sub})} 视频）")
        print(f"  {'chunker':<9} {'len_ok%':>7} {'cov%':>5} {'红余%':>5} {'尾词%':>5}")
        for chunker in ["chars", "texttile"]:
            s = [r for r in sub if r["chunker"] == chunker]
            if not s:
                continue
            avg = lambda k: sum(r[k] for r in s) / len(s)
            print(f"  {chunker:<9} {avg('len_ok_rate') * 100:>6.0f}% "
                  f"{avg('coverage_mean') * 100:>4.0f}% "
                  f"{avg('redundancy_mean') * 100:>4.0f}% "
                  f"{avg('trailing_bad_rate') * 100:>4.0f}%")

    # 失败案例 — trailing bad headlines
    print("\n" + "=" * 60)
    print("=== 悬空连接词样例 (chunker × video) ===")
    print("=" * 60)
    for r in rows:
        if r["bad_examples"]:
            print(f"\n{r['label']} / {r['chunker']}:")
            for h, b in r["bad_examples"][:3]:
                print(f"  尾词\"{b}\" → {h}")

    out_path = Path("data/outputs/eval_headlines.json")
    # 保存时去掉 headlines/bad_examples 避免文件过大
    slim = [{k: v for k, v in r.items() if k not in ("headlines", "bad_examples")}
            for r in rows]
    out_path.write_text(json.dumps(slim, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"\n>>> 数据保存到 {out_path}")


if __name__ == "__main__":
    main()
