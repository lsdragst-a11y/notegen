"""验证 trim_topic_outliers 在 9 个失败 chunks 上的行为。

对每个原失败案例：打印原 chunk 文本 + 截尾结果 + 哪些段被截了。
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from summarize_neural import trim_topic_outliers  # noqa: E402

# 从 sample_headlines + ratings 取 ≤2 分的案例
FAILS = [
    ("BV1SddcBFESs_p0", "chars",    2, "claude code 自动进入计划模式"),
    ("BV1W8AGzwEFW_p0", "chars",    4, "点不到的东西重庆人吃taco啊"),
    ("BV1W8AGzwEFW_p0", "texttile", 1, "上海啊外卖局啊我们各自点了这个是享受外卖"),
    ("BV1W8AGzwEFW_p0", "texttile", 5, "我吃不了我吃过肯定老师分了第二个"),
    ("BV1x25P6tEKe_p0", "chars",    1, "我们轻我们向滑滑"),
    ("BV1x25P6tEKe_p0", "texttile", 1, "我们轻我们向滑滑"),
    ("BV1XY546vE1o_p0", "chars",    5, "我这样显得我超级想拖但我真的不是拖"),
    ("BV1XY546vE1o_p0", "chars",    2, "你真的不需要按脚吗(组图)"),
    ("BV1XY546vE1o_p0", "texttile", 4, "刘谦《我的世界》"),
]


def main():
    for stem, chunker, idx, old_headline in FAILS:
        suffix = "" if chunker == "chars" else f".{chunker}"
        p = Path(f"data/outputs/{stem}.large-v3.neural{suffix}.summary.json")
        chunks = json.loads(p.read_text(encoding="utf-8"))
        if idx > len(chunks):
            print(f"[skip] {stem}/{chunker} #{idx} - chunks 只 {len(chunks)} 个")
            continue
        c = chunks[idx - 1]
        text = c["text"]
        trimmed = trim_topic_outliers(text)
        n_orig = len([s for s in text.split("\n") if s.strip()])
        n_trim = len([s for s in trimmed.split("\n") if s.strip()])
        cut_n = n_orig - n_trim
        print(f"\n=== {stem}/{chunker} chunk#{idx} ===")
        print(f"  旧 headline: {old_headline}")
        print(f"  原 segments: {n_orig}，截掉 {cut_n} 个孤儿尾段")
        if cut_n > 0:
            cut_segs = text.split("\n")[-cut_n:]
            for s in cut_segs:
                print(f"    × 截掉: {s.strip()[:80]}")
            print(f"  剩余末尾 3 段:")
            for s in trimmed.split("\n")[-3:]:
                print(f"    ✓ 保留: {s.strip()[:80]}")
        else:
            print(f"  (未截掉，原内容已聚焦)")


if __name__ == "__main__":
    main()
