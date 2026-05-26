"""轻量化 apply：只重跑 refine_chapter_titles + 同步 title_zh/title_en 到 web。

用于 J7 这种"只动章标题，不重做 ASR/seg/abstract/recap"的小修。

跑法：
  .venv/Scripts/python.exe scripts/_apply_chapter_titles.py BV1BE411D7ii_p68_p0
  .venv/Scripts/python.exe scripts/_apply_chapter_titles.py BV1BE411D7ii_p68_p0 BV1xxx_p0

每个 id 串行处理（释放 LLM 再加载下一个，避免 VRAM 累积）。

效果：
  1. data/outputs/{stem}.chapters.json  -> title 字段更新
  2. web/public/notes/{id}/chapters.json -> title / title_zh / title_en 同步
  不动 abstract / recap / quiz / indices / chunks。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUTPUTS = ROOT / "data" / "outputs"
NOTES = ROOT / "web" / "public" / "notes"


def find_chapters_path(bv: str) -> tuple[Path, Path]:
    pat = str(OUTPUTS / f"{bv}.*.chapters.json")
    cand = glob.glob(pat)
    if not cand:
        raise FileNotFoundError(f"no chapters.json for {bv} (pattern: {pat})")
    cand.sort(key=lambda p: ("vl" not in p, len(p)))
    chap = Path(cand[0])
    summ = chap.with_name(chap.name.replace(".chapters.json", ".summary.json"))
    if not summ.exists():
        raise FileNotFoundError(f"summary not found: {summ}")
    return chap, summ


def load_category(bv: str) -> str:
    p = NOTES / bv / "meta.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8")).get("category", "teaching")
    return "teaching"


def apply_one(bv: str, dry: bool = False, force: bool = False) -> bool:
    from segment_llm import refine_chapter_titles, translate_bilingual

    chap_p, summ_p = find_chapters_path(bv)
    chap_doc = json.loads(chap_p.read_text(encoding="utf-8"))
    summary = json.loads(summ_p.read_text(encoding="utf-8"))
    chapters = chap_doc["chapters"]
    outline = {"chapters": [{"chunks": ch.get("chunks") or ch.get("indices")}
                            for ch in chapters]}

    category = load_category(bv)
    lang = chap_doc.get("lang") or chap_doc.get("ablation", {}).get("lang", "zh")
    print(f"[{bv}]  category={category}  lang={lang}  {len(chapters)} chapters")
    old_titles = [ch.get("title") for ch in chapters]
    for i, t in enumerate(old_titles):
        print(f"  old Ch{i+1}: {t}")

    new_titles = refine_chapter_titles(outline, summary,
                                       lang=lang, category=category)
    if not new_titles or len(new_titles) != len(chapters):
        print(f"  [fail] refine returned {new_titles!r}")
        return False
    print("  --- new ---")
    n_changed = 0
    for i, (old, new) in enumerate(zip(old_titles, new_titles)):
        mark = "  <-- CHANGED" if old != new else " (unchanged)"
        print(f"  new Ch{i+1}: {new}{mark}")
        if old != new:
            n_changed += 1

    if n_changed == 0 and not force:
        print(f"  [skip] all titles unchanged ({bv})")
        return True

    if dry:
        print(f"  [dry] {n_changed} changed — skipped writeback")
        return True

    # 1) 写回 data/outputs/{stem}.chapters.json
    for ch, nt in zip(chapters, new_titles):
        ch["title"] = nt
    chap_doc["chapters"] = chapters
    chap_p.write_text(json.dumps(chap_doc, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(f"  [ok] wrote {chap_p.name}")

    # 2) 翻译新 title 到目标语言
    tgt = "en" if lang == "zh" else "zh"
    translated = translate_bilingual(new_titles, lang, tgt)
    if not translated or len(translated) != len(new_titles):
        print(f"  [warn] translate failed ({translated!r}); web title_en/_zh 保留旧值")
        translated = None

    # zh->en 时偶发漏译留下 CJK 字符（e.g. "Interrupt handling流程 and ..."），
    # 单条重译；最多 2 次仍残留则保留 LLM 输出
    def _has_cjk(s: str) -> bool:
        return any("一" <= ch <= "鿿" for ch in s)
    if translated is not None and tgt == "en":
        for i, (src, en) in enumerate(zip(new_titles, translated)):
            for attempt in range(2):
                if not _has_cjk(en):
                    break
                print(f"  [retry] Ch{i+1} CJK residual in en: {en!r} (try {attempt+1})")
                retry = translate_bilingual([src], lang, tgt)
                if retry and len(retry) == 1:
                    en = retry[0]
                    translated[i] = en

    # 3) 同步到 web/public/notes/{id}/chapters.json
    web_p = NOTES / bv / "chapters.json"
    if not web_p.exists():
        print(f"  [warn] web chapters.json missing: {web_p}")
        return True
    web_doc = json.loads(web_p.read_text(encoding="utf-8"))
    web_chs = web_doc["chapters"]
    if len(web_chs) != len(new_titles):
        print(f"  [warn] web chapters count mismatch "
              f"({len(web_chs)} vs {len(new_titles)}), 跳过 web 同步")
        return True
    for i, (ch, nt) in enumerate(zip(web_chs, new_titles)):
        ch["title"] = nt
        ch[f"title_{lang}"] = nt
        if translated is not None:
            ch[f"title_{tgt}"] = translated[i]
    web_doc["chapters"] = web_chs
    web_p.write_text(json.dumps(web_doc, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    print(f"  [ok] synced {web_p}")
    return True


def free_llm():
    try:
        import torch, gc
        import segment_llm
        segment_llm._MODEL = None
        segment_llm._TOKENIZER = None
        gc.collect()
        torch.cuda.empty_cache()
    except Exception:
        pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument("bvs", nargs="+", help="一个或多个 web note id (e.g. BV1xxx_p0)")
    p.add_argument("--dry", action="store_true",
                   help="只打印对比，不写回任何文件")
    p.add_argument("--force", action="store_true",
                   help="即使全部 unchanged 也走翻译+写回")
    args = p.parse_args()

    n_ok = 0
    for bv in args.bvs:
        try:
            if apply_one(bv, dry=args.dry, force=args.force):
                n_ok += 1
        except Exception as e:
            print(f"  FAIL {bv}: {e}")
        free_llm()

    print(f"\n[DONE] {n_ok}/{len(args.bvs)} ok")


if __name__ == "__main__":
    main()
