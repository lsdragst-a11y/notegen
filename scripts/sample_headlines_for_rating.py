"""从 8 视频 × 2 chunker 的 headlines 里 stratified 抽 30 个让用户打分。

5 分制：
  5 = 精准、能让人快速理解该段讲什么
  4 = 主旨抓到但有小瑕疵（如多余/缺失次要信息）
  3 = 抓到部分主旨，但偏离/笼统
  2 = 主旨严重偏离，但跟内容相关
  1 = 完全错或胡言乱语

对每个 headline 提供 chunk 文本头 60 字作为上下文。
"""
from __future__ import annotations

import io
import json
import random
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

random.seed(42)

VIDEOS = [
    ("BV19E411D78Q_p38.f30280", "计网"),
    ("BV1SddcBFESs_p0",          "ClaudeCode"),
    ("BV1G85V6cE1g_p0",          "懂王"),
    ("BV1W8AGzwEFW_p0",          "外卖"),
    ("BV1x25P6tEKe_p0",          "iOS"),
    ("BV1XY546vE1o_p0",          "影视飓风"),
    ("BV1cwdzBDEL3_p0",          "日本Vlog"),
    ("BV1ygo9BeEvV_p0",          "多Agent"),
]


def load_summary(stem: str, chunker: str) -> list[dict]:
    suffix = "" if chunker == "chars" else f".{chunker}"
    p = Path(f"data/outputs/{stem}.large-v3.neural{suffix}.summary.json")
    return json.loads(p.read_text(encoding="utf-8"))


def main():
    # 收集所有 (video, chunker, chunk_idx, headline, context) 四元组
    pool: list[dict] = []
    for stem, vname in VIDEOS:
        for chunker in ["chars", "texttile"]:
            try:
                chunks = load_summary(stem, chunker)
            except Exception:
                continue
            for i, c in enumerate(chunks):
                pool.append({
                    "video": vname, "chunker": chunker, "chunk_idx": i + 1,
                    "headline": c.get("headline", ""),
                    "context": c.get("text", "").replace("\n", " ")[:80],
                })

    # Stratified：每 video × chunker cell 取 ~2 个，让分布均衡
    by_cell: dict[tuple[str, str], list[dict]] = {}
    for r in pool:
        by_cell.setdefault((r["video"], r["chunker"]), []).append(r)

    sampled: list[dict] = []
    for cell, rows in by_cell.items():
        k = min(2, len(rows))
        sampled.extend(random.sample(rows, k))

    # 不足 30 就从剩余随机补
    remaining = [r for r in pool if r not in sampled]
    if len(sampled) < 30:
        sampled.extend(random.sample(remaining, min(30 - len(sampled), len(remaining))))
    sampled = sampled[:30]

    # 输出打分模板
    print("=" * 100)
    print("Headline 打分模板：5=精准 / 4=小瑕疵 / 3=部分主旨/笼统 / 2=偏离但相关 / 1=完全错")
    print("逐条看完后回复一串 30 个数字（空格或逗号分隔）")
    print("=" * 100)
    print()

    template_records = []
    for i, r in enumerate(sampled, 1):
        print(f"[{i:2d}] 视频={r['video']:<10s} chunker={r['chunker']:<8s} chunk#{r['chunk_idx']}")
        print(f"     headline: {r['headline']}")
        print(f"     上下文  : {r['context']}…")
        print()
        template_records.append(r)

    out_path = Path("data/outputs/headline_rating_sample.json")
    out_path.write_text(json.dumps(template_records, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f">>> 抽样表保存到 {out_path}")


if __name__ == "__main__":
    main()
