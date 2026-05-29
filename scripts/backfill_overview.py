"""给 web/public/notes/{id}/chapters.json 顶层补「全文总结」overview。

基于已有的章 title + abstract 调 generate_doc_overview 生成 summary + takeaways，
再 translate_bilingual 补另一种语言，写回 chapters.json 顶层 overview 对象。
不重跑 ASR / segmentation。

跑法：
  .venv/Scripts/python.exe scripts/backfill_overview.py --only BV1BE411D7ii_p68_p0
  .venv/Scripts/python.exe scripts/backfill_overview.py            # 全部缺 overview 的
  .venv/Scripts/python.exe scripts/backfill_overview.py --force    # 已有的也重生
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTES_DIR = ROOT / "web" / "public" / "notes"
sys.path.insert(0, str(ROOT / "src"))


def _detect_doc_lang(strings: list[str]) -> str:
    """中文字符占比 > 15% 视为 zh，否则 en（与 translate_notes 同启发式）。"""
    joined = "".join(s for s in strings if s)[:500]
    if not joined:
        return "zh"
    cn = sum(1 for ch in joined if "一" <= ch <= "鿿")
    return "zh" if cn / max(len(joined), 1) > 0.15 else "en"


def backfill_note(note_id: str, force: bool = False) -> bool:
    note_dir = NOTES_DIR / note_id
    chapters_p = note_dir / "chapters.json"
    if not chapters_p.exists():
        print(f"  skip {note_id}: no chapters.json", file=sys.stderr)
        return False
    data = json.loads(chapters_p.read_text(encoding="utf-8"))
    chapters = data.get("chapters") or []
    if not chapters:
        print(f"  skip {note_id}: empty chapters", file=sys.stderr)
        return False
    if (not force and isinstance(data.get("overview"), dict)
            and data["overview"].get("summary")):
        print(f"  skip {note_id}: already has overview (use --force)")
        return True
    title = ""
    meta_p = note_dir / "meta.json"
    if meta_p.exists():
        try:
            title = (json.loads(meta_p.read_text(encoding="utf-8")) or {}).get("title", "")
        except Exception:
            pass
    src_lang = _detect_doc_lang([c.get("title", "") for c in chapters])
    tgt_lang = "en" if src_lang == "zh" else "zh"
    print(f"\n=== {note_id} (src={src_lang}, {len(chapters)} chapters) ===")
    from segment_llm import generate_doc_overview, translate_bilingual
    ov = generate_doc_overview(chapters, video_title=title, lang=src_lang)
    if not ov:
        print(f"  FAIL {note_id}: generate_doc_overview 返回 None", file=sys.stderr)
        return False
    summary, takeaways = ov["summary"], ov["takeaways"]
    overview = {
        "summary": summary,
        f"summary_{src_lang}": summary,
        "takeaways": takeaways,
        f"takeaways_{src_lang}": takeaways,
    }
    # 另一种语言（前端 lang toggle 用）
    t_sum = translate_bilingual([summary], src_lang, tgt_lang)
    if t_sum and len(t_sum) == 1:
        overview[f"summary_{tgt_lang}"] = t_sum[0]
    t_tk = translate_bilingual(takeaways, src_lang, tgt_lang)
    if t_tk and len(t_tk) == len(takeaways):
        overview[f"takeaways_{tgt_lang}"] = t_tk
    data["overview"] = overview
    chapters_p.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    print(f"  written: summary {len(summary)} 字, {len(takeaways)} takeaways, "
          f"{tgt_lang}={'yes' if overview.get(f'summary_{tgt_lang}') else 'NO'}")
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--only", nargs="*", default=None,
                   help="只补指定 note_id（web/public/notes/ 下目录名）")
    p.add_argument("--force", action="store_true", help="已有 overview 的也重生")
    args = p.parse_args()
    ids = (args.only if args.only
           else sorted(d.name for d in NOTES_DIR.iterdir() if d.is_dir()))
    print(f"target: {len(ids)} notes")
    n_ok = n_fail = 0
    for nid in ids:
        try:
            if backfill_note(nid, force=args.force):
                n_ok += 1
            else:
                n_fail += 1
        except Exception as e:
            print(f"  FAIL {nid}: {e}", file=sys.stderr)
            n_fail += 1
    print(f"\n=== done: {n_ok} ok, {n_fail} skipped/failed ===")


if __name__ == "__main__":
    main()
