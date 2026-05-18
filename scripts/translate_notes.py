"""给 web/public/notes/{id}/{chapters,summary}.json 补双语字段。

不重跑 ASR / segmentation，只调一次 Qwen translate_bilingual 翻译每个文档里的
chapter title / abstract / chunk headline，写回 _zh / _en 后缀字段。

跑法：
  .venv/Scripts/python.exe scripts/translate_notes.py            # 全 13 个笔记
  .venv/Scripts/python.exe scripts/translate_notes.py --only os python  # 指定
  .venv/Scripts/python.exe scripts/translate_notes.py --force    # 已翻过的也重翻
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
    """启发式检测文本主要语言：中文字符占比 > 15% 视为 zh，否则 en。"""
    joined = "".join(s for s in strings if s)[:500]
    if not joined:
        return "zh"
    cn = sum(1 for ch in joined if "一" <= ch <= "鿿")
    return "zh" if cn / max(len(joined), 1) > 0.15 else "en"


def _translate_field_inplace(items: list[dict], field: str,
                              src_lang: str, tgt_lang: str,
                              translate_fn, batch: int = 0) -> bool:
    """对 items[*][field] 批量翻译，写 items[*][field+"_"+tgt_lang]。
    源字段也存为 _{src_lang}（幂等：第二次跑时就有 _zh/_en 双字段）。

    batch>0 时分批跑：chunk.text 这种长字段一次喂 36 段会超 LLM context window，
    分批 4-8 个一组。
    """
    raw = [str(it.get(field, "") or "") for it in items]
    if not any(raw):
        return False
    if batch > 0 and len(items) > batch:
        translated: list[str] = []
        for s in range(0, len(items), batch):
            sub = raw[s:s + batch]
            sub_t = translate_fn(sub, src_lang, tgt_lang)
            if not sub_t or len(sub_t) != len(sub):
                print(f"  [{field}] batch {s}-{s+len(sub)} failed",
                      file=sys.stderr)
                return False
            translated.extend(sub_t)
    else:
        translated = translate_fn(raw, src_lang, tgt_lang)
        if not translated or len(translated) != len(items):
            print(f"  [{field}] translation failed", file=sys.stderr)
            return False
    for it, t in zip(items, translated):
        it[f"{field}_{src_lang}"] = it.get(field, "")
        it[f"{field}_{tgt_lang}"] = t
    return True


def _translate_keywords_inplace(items: list[dict],
                                  src_lang: str, tgt_lang: str,
                                  translate_fn) -> bool:
    """对每个 chunk 的 keywords (list[str]) 翻译，写 keywords_{src/tgt}_lang 字段。
    所有 chunk 的 keywords 拍平成一个 list 一次翻完，按原长度切回，效率高。"""
    flat: list[str] = []
    bounds: list[tuple[int, int]] = []
    cursor = 0
    for it in items:
        kws = it.get("keywords") or []
        bounds.append((cursor, cursor + len(kws)))
        flat.extend(kws)
        cursor += len(kws)
    if not flat:
        return False
    translated = translate_fn(flat, src_lang, tgt_lang)
    if not translated or len(translated) != len(flat):
        print(f"  [keywords] translation failed (got {len(translated) if translated else 0}/{len(flat)})",
              file=sys.stderr)
        return False
    for it, (lo, hi) in zip(items, bounds):
        it[f"keywords_{src_lang}"] = it.get("keywords", [])
        it[f"keywords_{tgt_lang}"] = translated[lo:hi]
    return True


def translate_note(note_id: str, force: bool = False) -> bool:
    note_dir = NOTES_DIR / note_id
    chapters_p = note_dir / "chapters.json"
    summary_p = note_dir / "summary.json"
    if not chapters_p.exists() or not summary_p.exists():
        print(f"  skip {note_id}: missing chapters/summary", file=sys.stderr)
        return False
    chapters_data = json.loads(chapters_p.read_text(encoding="utf-8"))
    chapters = chapters_data.get("chapters") or []
    summary = json.loads(summary_p.read_text(encoding="utf-8"))
    # 已翻译过且未 force 则跳（判全字段都翻，title/text/summary/keywords 都得有 _en）
    if not force and chapters and summary:
        has_all = all([
            "title_en" in chapters[0],
            "text_en" in summary[0],
            "summary_en" in summary[0] if "summary" in summary[0] else True,
            "keywords_en" in summary[0],
        ])
        if has_all:
            print(f"  skip {note_id}: already fully bilingual (use --force to overwrite)")
            return True
    # 检测源语言（用所有 chapter title 拼起来判定）
    src_lang = _detect_doc_lang([c.get("title", "") for c in chapters])
    tgt_lang = "en" if src_lang == "zh" else "zh"
    print(f"\n=== {note_id} (src={src_lang}, tgt={tgt_lang}, "
          f"{len(chapters)} chapters, {len(summary)} chunks) ===")
    from segment_llm import translate_bilingual
    ok_t = _translate_field_inplace(chapters, "title", src_lang, tgt_lang, translate_bilingual)
    ok_a = _translate_field_inplace(chapters, "abstract", src_lang, tgt_lang, translate_bilingual)
    ok_h = _translate_field_inplace(summary, "headline", src_lang, tgt_lang, translate_bilingual)
    # chunk-level：summary (jieba 抽取式短文) + text (ASR 原文长文) + keywords
    ok_s = _translate_field_inplace(summary, "summary", src_lang, tgt_lang,
                                      translate_bilingual, batch=8)
    ok_x = _translate_field_inplace(summary, "text", src_lang, tgt_lang,
                                      translate_bilingual, batch=4)
    ok_k = _translate_keywords_inplace(summary, src_lang, tgt_lang, translate_bilingual)
    # 写回（保留原 ablation 等字段）
    if ok_t or ok_a:
        chapters_data["chapters"] = chapters
        chapters_p.write_text(json.dumps(chapters_data, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    if ok_h or ok_s or ok_x or ok_k:
        summary_p.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    return ok_t or ok_a or ok_h or ok_s or ok_x or ok_k


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--only", nargs="*", default=None,
                   help="只翻指定 note_id（用 web/public/notes/ 下目录名）")
    p.add_argument("--force", action="store_true",
                   help="已翻译过的也重翻")
    args = p.parse_args()
    if args.only:
        ids = args.only
    else:
        ids = sorted([d.name for d in NOTES_DIR.iterdir() if d.is_dir()])
    print(f"target: {len(ids)} notes")
    n_ok, n_fail = 0, 0
    for nid in ids:
        try:
            if translate_note(nid, force=args.force):
                n_ok += 1
            else:
                n_fail += 1
        except Exception as e:
            print(f"  FAIL {nid}: {e}", file=sys.stderr)
            n_fail += 1
    print(f"\n=== done: {n_ok} ok, {n_fail} skipped/failed ===")


if __name__ == "__main__":
    main()
