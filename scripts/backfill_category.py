"""扫 web/public/notes/*/，给每个笔记 meta.json 回填 category 字段。

不重跑 ASR/segment，只读 summary.json 拼 transcript 喂分类器。

用法：
  python scripts/backfill_category.py                  # 全量
  python scripts/backfill_category.py --only os python # 指定
  python scripts/backfill_category.py --force          # 覆盖已有 category
  python scripts/backfill_category.py --dry            # 只打印不写
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 让 src/ 模块可被 import
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from classify_category import classify_category  # noqa: E402

NOTES_DIR = ROOT / "web" / "public" / "notes"


def _load_transcript(summary_path: Path, max_chars: int = 5000) -> str:
    """从 summary.json 拼出 ASR 全文（截前 max_chars 字，分类够用）。"""
    try:
        data = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    parts = []
    n = 0
    for c in data:
        t = c.get("text") or c.get("text_zh") or c.get("text_en") or ""
        if not t:
            continue
        parts.append(t)
        n += len(t)
        if n >= max_chars:
            break
    return " ".join(parts)[:max_chars]


def _duration(summary_path: Path) -> float | None:
    try:
        data = json.loads(summary_path.read_text(encoding="utf-8"))
        if data:
            return float(data[-1].get("end") or 0)
    except Exception:
        pass
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--only", nargs="*", default=None, help="只处理指定 note id")
    p.add_argument("--force", action="store_true", help="覆盖已有 category 字段")
    p.add_argument("--dry", action="store_true", help="只打印不写")
    args = p.parse_args()

    if not NOTES_DIR.exists():
        print(f"NOTES_DIR not found: {NOTES_DIR}", file=sys.stderr)
        sys.exit(1)

    targets = sorted(d for d in NOTES_DIR.iterdir() if d.is_dir())
    if args.only:
        only_set = set(args.only)
        targets = [d for d in targets if d.name in only_set]

    print(f"扫描 {len(targets)} 个笔记目录\n")
    summary_lines: list[str] = []

    for d in targets:
        meta_path = d / "meta.json"
        summary_path = d / "summary.json"
        if not meta_path.exists():
            print(f"  [skip] {d.name}: 无 meta.json")
            continue
        if not summary_path.exists():
            print(f"  [skip] {d.name}: 无 summary.json")
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [err] {d.name}: meta.json parse 失败 {e}")
            continue

        if meta.get("category") and not args.force:
            print(f"  [keep] {d.name}: 已有 category={meta['category']}")
            continue

        transcript = _load_transcript(summary_path)
        dur = _duration(summary_path) or meta.get("duration")
        r = classify_category(meta, transcript=transcript, duration_sec=dur)

        cat = r["category"]
        conf = r["confidence"]
        title = (meta.get("title") or d.name)[:50]
        print(f"  [{cat:8s} {conf:6s}] {d.name:30s}  {title}")
        for line in r["reasons"]:
            print(f"      · {line}")
        summary_lines.append(f"{cat:8s} {d.name:30s}  {title}")

        if not args.dry:
            meta["category"] = cat
            meta["category_confidence"] = conf
            meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8")

    print("\n========== 分类汇总 ==========")
    for line in summary_lines:
        print(line)


if __name__ == "__main__":
    main()
