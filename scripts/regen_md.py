"""复用已有的 *.summary.json 和 *.chapters.json，重新生成 md。
不重跑 ASR / Pegasus / CLIP，只调 to_markdown 验证学习类元素。

用法：python scripts/regen_md.py <stem> [--category teaching|popsci|vlog|talk]
例：  python scripts/regen_md.py BV1SddcBFESs_p0.large-v3.neural.texttile
      python scripts/regen_md.py BV1paLF6LEKN_p0.large-v3.neural.texttile.mm.vl --category vlog

不带 --category 时，从 raw/<video_stem>.meta.json 读 category 字段；都没有
就 fallback teaching（与 to_markdown 默认一致）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from summarize import to_markdown  # noqa: E402

OUTPUT_DIR = Path("data/outputs")
META_DIR = Path("data/raw")


def regen(stem: str, learning_mode: bool = True,
          category_override: str | None = None) -> Path:
    summary_path = OUTPUT_DIR / f"{stem}.summary.json"
    chapters_path = OUTPUT_DIR / f"{stem}.chapters.json"
    if not summary_path.exists():
        raise FileNotFoundError(summary_path)

    summaries = json.loads(summary_path.read_text(encoding="utf-8"))
    chapter_list = None
    if chapters_path.exists():
        payload = json.loads(chapters_path.read_text(encoding="utf-8"))
        chapter_list = payload.get("chapters") if isinstance(payload, dict) else payload

    # md 标题 + category：从 meta 拿真实标题
    md_title = stem
    category = "teaching"
    video_stem = stem.split(".")[0]
    meta_path = META_DIR / f"{video_stem}.meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            md_title = meta.get("title", stem)
            if meta.get("category"):
                category = meta["category"]
        except Exception:
            pass
    if category_override:
        category = category_override

    # keyframe 路径前缀：如果同名 .keyframes 目录存在
    kf_dir = OUTPUT_DIR / f"{stem}.keyframes"
    kf_rel_prefix = f"{kf_dir.name}/" if kf_dir.exists() else ""

    md = to_markdown(summaries, title=md_title, chapters=chapter_list,
                     keyframe_rel_prefix=kf_rel_prefix,
                     learning_mode=learning_mode,
                     category=category)
    out_path = OUTPUT_DIR / f"{stem}.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"[OK] regenerated: {out_path}")
    print(f"     category={category}, learning_mode={learning_mode}, "
          f"chapters={len(chapter_list) if chapter_list else 0}, "
          f"summaries={len(summaries)}")
    return out_path


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("stem", help="如 BV1paLF6LEKN_p0.large-v3.neural.texttile.mm.vl")
    p.add_argument("--category", choices=("teaching", "popsci", "vlog", "talk"),
                   help="覆盖 meta.json 的 category（用于实验/手动校正）")
    p.add_argument("--no-learning-mode", dest="learning_mode",
                   action="store_false", default=True)
    args = p.parse_args()
    regen(args.stem, learning_mode=args.learning_mode,
          category_override=args.category)
