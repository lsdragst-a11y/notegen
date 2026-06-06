"""扫全 corpus，找双语 toggle 英文侧（任意 *_en 字段）里残留的中文字符。

根因：Qwen 翻译偶发漏译单词（如 abstract_en「the生产工艺 of...」、
summary_en「Ethernet工作组」），且 --term 定向重跑只 patch 章级 title_en/abstract_en，
overview 块与 takeaways_en 这类**列表项**会被漏检 → 中文卡在英文句子里直接上 web。

判据：递归遍历 chapters.json，凡 key 以 `_en` 结尾的字符串（含 `_en` 列表里的元素）
含 CJK 字符即报。只报告不改文件。

跑法：
  .venv/Scripts/python.exe scripts/scan_en_leak.py
  .venv/Scripts/python.exe scripts/scan_en_leak.py --data    # 连 data/outputs 源一起扫
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import re
import sys

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

CJK = re.compile(r"[一-鿿]")


def walk(obj, key: str = "", path: str = ""):
    """yield (path, value) for every string under an `_en` context.

    列表项继承父级 key，故 takeaways_en[i] 这种也能命中。
    """
    if isinstance(obj, str):
        if key.endswith("_en") and CJK.search(obj):
            yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, k, f"{path}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, key, f"{path}[{i}]")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", action="store_true",
                    help="也扫 data/outputs/*.chapters.json 源文件")
    args = ap.parse_args()

    files = sorted(glob.glob("web/public/notes/*/chapters.json"))
    if args.data:
        files += sorted(glob.glob("data/outputs/*.chapters.json"))

    total = 0
    bad_notes = 0
    for f in files:
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception as e:
            print(f"[parse-fail] {f}: {e}")
            continue
        hits = list(walk(d))
        if hits:
            bad_notes += 1
            total += len(hits)
            print(f"[!] {f}  ({len(hits)} 处)")
            for p, v in hits:
                runs = re.findall(r"[一-鿿]+", v)
                print(f"    {p}  CJK={runs}")
                print(f"      {v[:120]}")

    print(f"\n扫描 {len(files)} 文件，英文侧中文残留 {total} 处 / {bad_notes} 文件")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
