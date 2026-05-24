"""扫 data/raw/*.meta.json 给缺 category 的回填；同步 web/public/notes/<bv>/meta.json。

backfill_category.py 只读 web/public/notes/，遗漏未 publish 的视频，且未把
data/raw/ 的 meta 一并修。本脚本补：

  - 主存：data/raw/<bv>.meta.json（pipeline 写入位置）
  - 副本：web/public/notes/<bv>/meta.json（若已 publish）

用法：
  python scripts/backfill_category_raw.py            # 全量
  python scripts/backfill_category_raw.py --dry      # 只打印不写
  python scripts/backfill_category_raw.py --force    # 覆盖已有 category
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from classify_category import classify_category  # noqa: E402

RAW_DIR = ROOT / "data" / "raw"
OUTPUTS_DIR = ROOT / "data" / "outputs"
NOTES_DIR = ROOT / "web" / "public" / "notes"


def _find_summary(bv: str) -> Path | None:
    """挑最新的 *.summary.json 作为 transcript 来源"""
    cands = sorted(
        OUTPUTS_DIR.glob(f"{bv}.large-v3.neural.texttile*.summary.json"),
        key=lambda p: -p.stat().st_mtime)
    return cands[0] if cands else None


def _load_transcript(summary_path: Path, max_chars: int = 5000) -> str:
    try:
        data = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    parts, n = [], 0
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
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry", action="store_true")
    args = p.parse_args()

    metas = sorted(RAW_DIR.glob("*.meta.json"))
    print(f"扫描 data/raw 下 {len(metas)} 个 meta.json")
    print()

    counts = {"teaching": 0, "popsci": 0, "vlog": 0, "talk": 0,
              "skip-no-summary": 0, "skip-keep": 0}

    for meta_path in metas:
        bv = meta_path.stem.replace(".meta", "")
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [err] {bv}: parse fail {e}")
            continue

        if meta.get("category") and not args.force:
            counts["skip-keep"] += 1
            continue

        summary_path = _find_summary(bv)
        if not summary_path:
            print(f"  [skip] {bv}: 无 summary.json (跳过)")
            counts["skip-no-summary"] += 1
            continue

        transcript = _load_transcript(summary_path)
        dur = _duration(summary_path) or meta.get("duration")
        r = classify_category(meta, transcript=transcript, duration_sec=dur)

        cat = r["category"]
        conf = r["confidence"]
        title = (meta.get("title") or bv)[:50]
        print(f"  [{cat:8s} {conf:6s}] {bv:30s}  {title}")
        counts[cat] = counts.get(cat, 0) + 1

        if args.dry:
            continue

        meta["category"] = cat
        meta["category_confidence"] = conf
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        # 同步 web 副本
        web_meta = NOTES_DIR / bv / "meta.json"
        if web_meta.exists():
            try:
                wm = json.loads(web_meta.read_text(encoding="utf-8"))
                wm["category"] = cat
                wm["category_confidence"] = conf
                web_meta.write_text(
                    json.dumps(wm, ensure_ascii=False, indent=2),
                    encoding="utf-8")
            except Exception as e:
                print(f"      [warn] web meta sync fail: {e}")

    print()
    print("========== 分类汇总 ==========")
    for k, v in counts.items():
        print(f"  {k:20s}: {v}")


if __name__ == "__main__":
    main()
