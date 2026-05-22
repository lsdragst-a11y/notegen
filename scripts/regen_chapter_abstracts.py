"""重跑指定视频的 chapter abstract（不重做 ASR / 章节切分）。

用于 vlog/talk 类切换到"本段..."prompt 后回填已生成产物。

用法：
  python scripts/regen_chapter_abstracts.py <stem> [<stem> ...] [--category vlog]

例：
  python scripts/regen_chapter_abstracts.py BV1paLF6LEKN_p0.large-v3.neural.texttile.mm.vl \
                                            BV19SRSBeE6F_p0.large-v3.neural.texttile.mm.vl \
                                            --category vlog

每跑完一个会释放 Qwen 模型再加载下一个（避免长驻 VRAM 撞机）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from segment_llm import generate_chapter_abstracts  # noqa: E402

OUTPUT_DIR = ROOT / "data" / "outputs"
META_DIR = ROOT / "data" / "raw"


def regen_one(stem: str, category: str) -> None:
    chapters_path = OUTPUT_DIR / f"{stem}.chapters.json"
    summary_path = OUTPUT_DIR / f"{stem}.summary.json"
    if not chapters_path.exists():
        print(f"[skip] {stem}: chapters.json 不存在")
        return

    payload = json.loads(chapters_path.read_text(encoding="utf-8"))
    chapters = payload.get("chapters") if isinstance(payload, dict) else payload
    if not chapters:
        print(f"[skip] {stem}: chapters 为空")
        return

    summaries = json.loads(summary_path.read_text(encoding="utf-8"))
    # 把 chunks 字段填回章节（LLM 需要 headlines）
    for ch in chapters:
        idxs = ch.get("indices") or []
        ch["chunks"] = [summaries[i] for i in idxs if 0 <= i < len(summaries)]

    print(f"[regen] {stem}  category={category}  {len(chapters)} chapters")
    abstracts = generate_chapter_abstracts(chapters, lang="zh", category=category)
    if not abstracts or len(abstracts) != len(chapters):
        print(f"[fail] {stem}: 生成失败或数量不对（got {len(abstracts) if abstracts else 0}）")
        return

    for ch, ab in zip(chapters, abstracts):
        ch["abstract"] = ab
        # chunks 字段是临时拼上去的，写回前去掉避免 chapters.json 膨胀
        ch.pop("chunks", None)
        print(f"  L1 -> {ab[:80]}")

    # 写回 chapters.json（保留 outline meta 等其它字段）
    if isinstance(payload, dict):
        payload["chapters"] = chapters
        chapters_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        chapters_path.write_text(
            json.dumps(chapters, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok]   写回 {chapters_path.name}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("stems", nargs="+", help="一个或多个 stem")
    p.add_argument("--category", default="vlog",
                   choices=("teaching", "popsci", "vlog", "talk"))
    args = p.parse_args()

    import segment_llm

    def _free_llm():
        """释放 Qwen 模型让下一个干净加载（避免 VRAM 累积）。"""
        try:
            import torch, gc
            segment_llm._MODEL = None
            segment_llm._TOKENIZER = None
            gc.collect()
            torch.cuda.empty_cache()
        except Exception:
            pass

    for stem in args.stems:
        regen_one(stem, args.category)
        _free_llm()

    print("\n[DONE] 别忘了跑 scripts/regen_md.py 让 md 用新 abstract")


if __name__ == "__main__":
    main()
