"""对比 chunk cleaning 启用前后所有 30 个抽样 headline 的变化。"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# 用户 2026-05-14 给的原 30 个评分
RATINGS = [3, 3, 5, 3, 2, 4, 5, 4, 4, 5, 5, 4, 4, 2, 2, 2, 1, 3, 1, 3,
           2, 1, 3, 1, 5, 4, 5, 5, 5, 4]


def load_summary(stem_b: str, chunker: str) -> list[dict]:
    suffix = "" if chunker == "chars" else f".{chunker}"
    p = Path(f"data/outputs/{stem_b}.large-v3.neural{suffix}.summary.json")
    return json.loads(p.read_text(encoding="utf-8"))


def stem_from_video(video: str) -> str:
    return {
        "计网": "BV19E411D78Q_p38.f30280",
        "ClaudeCode": "BV1SddcBFESs_p0",
        "懂王": "BV1G85V6cE1g_p0",
        "外卖": "BV1W8AGzwEFW_p0",
        "iOS": "BV1x25P6tEKe_p0",
        "影视飓风": "BV1XY546vE1o_p0",
        "日本Vlog": "BV1cwdzBDEL3_p0",
        "多Agent": "BV1ygo9BeEvV_p0",
    }[video]


def main():
    sample = json.loads(Path("data/outputs/headline_rating_sample.json")
                        .read_text(encoding="utf-8"))

    changed = 0
    unchanged = 0
    print("=" * 110)
    print(f"{'#':>3}  {'视频/chunker':<22} {'rating':>3}  "
          f"{'旧 headline':<35} {'新 headline':<35} 变化")
    print("=" * 110)
    for i, (r, item) in enumerate(zip(RATINGS, sample), 1):
        stem = stem_from_video(item["video"])
        chunks = load_summary(stem, item["chunker"])
        new_h = chunks[item["chunk_idx"] - 1].get("headline", "")
        old_h = item["headline"]
        flag = "  变" if new_h != old_h else "  ="
        if new_h != old_h:
            changed += 1
        else:
            unchanged += 1
        print(f"{i:>3}  {item['video']:<10}/{item['chunker']:<8} {r:>3}  "
              f"{old_h[:33]:<35} {new_h[:33]:<35} {flag}")

    print(f"\n总变化: {changed}/30，{unchanged}/30 未变")

    # 失败案例（旧 rating ≤ 2）单独看
    print("\n=== 失败案例 (rating ≤ 2) 前后对比 ===")
    for i, (r, item) in enumerate(zip(RATINGS, sample), 1):
        if r > 2:
            continue
        stem = stem_from_video(item["video"])
        chunks = load_summary(stem, item["chunker"])
        new_h = chunks[item["chunk_idx"] - 1].get("headline", "")
        old_h = item["headline"]
        flag = "变化" if new_h != old_h else "未变"
        print(f"  [{r}] {item['video']}/{item['chunker']:<8} #{item['chunk_idx']}")
        print(f"      旧: {old_h}")
        print(f"      新: {new_h}  [{flag}]")


if __name__ == "__main__":
    main()
