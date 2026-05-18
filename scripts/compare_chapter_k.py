"""对比新旧 num_chapters 默认公式在 10 视频上的输出。"""
from __future__ import annotations

import glob
import json
import math
from pathlib import Path


def main():
    print(f'{"video":<32} {"n":>3} {"min":>6} {"oldK":>5} {"newK":>5}')
    for f in sorted(glob.glob("data/outputs/*texttile.summary.json")):
        data = json.loads(Path(f).read_text(encoding="utf-8"))
        n = len(data)
        dur_min = (data[-1]["end"] - data[0]["start"]) / 60
        old_k = max(2, min(6, n // 3))
        new_k = max(2, min(6, math.ceil(dur_min / 6)))
        name = Path(f).name.split(".")[0]
        print(f"{name:<32} {n:>3} {dur_min:>6.1f} {old_k:>5} {new_k:>5}")


if __name__ == "__main__":
    main()
