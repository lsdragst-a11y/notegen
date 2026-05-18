"""复用已有的 *.summary.json 和 *.chapters.json，重新生成 md。
不重跑 ASR / Pegasus / CLIP，只调 to_markdown 验证学习类元素。

用法：python scripts/regen_md.py <stem>
例：python scripts/regen_md.py BV1SddcBFESs_p0.large-v3.neural.texttile
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from summarize import to_markdown  # noqa: E402

OUTPUT_DIR = Path("data/outputs")
META_DIR = Path("data/raw")


def regen(stem: str, learning_mode: bool = True) -> Path:
    summary_path = OUTPUT_DIR / f"{stem}.summary.json"
    chapters_path = OUTPUT_DIR / f"{stem}.chapters.json"
    if not summary_path.exists():
        raise FileNotFoundError(summary_path)

    summaries = json.loads(summary_path.read_text(encoding="utf-8"))
    chapter_list = None
    if chapters_path.exists():
        payload = json.loads(chapters_path.read_text(encoding="utf-8"))
        chapter_list = payload.get("chapters") if isinstance(payload, dict) else payload

    # md 标题：从 meta 拿真实标题（stem 去掉 .large-v3.neural.* 后缀就是 video stem）
    md_title = stem
    video_stem = stem.split(".")[0]
    meta_path = META_DIR / f"{video_stem}.meta.json"
    if meta_path.exists():
        try:
            md_title = json.loads(meta_path.read_text(encoding="utf-8")).get("title", stem)
        except Exception:
            pass

    # keyframe 路径前缀：如果同名 .keyframes 目录存在
    kf_dir = OUTPUT_DIR / f"{stem}.keyframes"
    kf_rel_prefix = f"{kf_dir.name}/" if kf_dir.exists() else ""

    md = to_markdown(summaries, title=md_title, chapters=chapter_list,
                     keyframe_rel_prefix=kf_rel_prefix,
                     learning_mode=learning_mode)
    out_path = OUTPUT_DIR / f"{stem}.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"[OK] regenerated: {out_path}")
    print(f"     learning_mode={learning_mode}, chapters={len(chapter_list) if chapter_list else 0}, "
          f"summaries={len(summaries)}")
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    regen(sys.argv[1])
