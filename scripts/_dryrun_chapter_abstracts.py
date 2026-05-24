"""Dry-run 章 abstract 校准回归脚本

用法：python scripts/_dryrun_chapter_abstracts.py <BV id>

从已有 chapters.json + summary.json 复原 chapters[].chunks 结构（chunks 数据
原本只存索引，需要 inline 注入 headline/keywords/text/summary 才能跑
generate_chapter_abstracts）。打印新 abstract 与旧 abstract 对比。
"""
import sys, os, json, glob

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from segment_llm import generate_chapter_abstracts  # noqa: E402


def find_outputs(bv: str):
    pat = f"data/outputs/{bv}.*.chapters.json"
    cand = glob.glob(pat)
    if not cand:
        raise SystemExit(f"no chapters.json for {bv}")
    cand.sort(key=lambda p: ("vl" not in p, len(p)))
    chap = cand[0]
    summ = chap.replace(".chapters.json", ".summary.json")
    return chap, summ


def load_meta_category(bv: str) -> str:
    p = f"web/public/notes/{bv}/meta.json"
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8")).get("category", "teaching")
    return "teaching"


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    bv = sys.argv[1]
    chap_p, summ_p = find_outputs(bv)
    print(f"[chapters] {chap_p}")
    print(f"[summary]  {summ_p}")
    chap_doc = json.load(open(chap_p, encoding="utf-8"))
    summary = json.load(open(summ_p, encoding="utf-8"))
    chapters_raw = chap_doc["chapters"]

    # inline 注入 chunks: 把 indices/chunks 字段里的索引展开为完整 chunk dict
    chapters_for_llm = []
    for ch in chapters_raw:
        idxs = ch.get("chunks") or ch.get("indices") or []
        chunks_inline = []
        for i in idxs:
            c = summary[i]
            chunks_inline.append({
                "headline": c.get("headline", ""),
                "keywords": c.get("keywords", []),
                "text": c.get("text", ""),
                "summary": c.get("summary", ""),
            })
        chapters_for_llm.append({
            "title": ch.get("title", ""),
            "chunks": chunks_inline,
        })

    category = load_meta_category(bv)
    lang = chap_doc.get("lang") or chap_doc.get("ablation", {}).get("lang", "zh")
    print(f"[category={category}  lang={lang}]\n")

    print("=== 旧 abstract（已有 chapters.json） ===")
    for i, ch in enumerate(chapters_raw):
        print(f"  Ch{i+1} {ch.get('title')!r}:")
        print(f"    {ch.get('abstract', '(无)')[:120]}")
    print()

    print("=== 跑 generate_chapter_abstracts (新 prompt 含 Python 校准) ===")
    new_abs = generate_chapter_abstracts(chapters_for_llm,
                                         lang=lang, category=category)
    print()

    print("=== 新旧对比 ===")
    if new_abs is None:
        print("  generate 返回 None")
        return
    for i, (ch, na) in enumerate(zip(chapters_raw, new_abs)):
        old = ch.get("abstract", "")
        print(f"  Ch{i+1} {ch.get('title')!r}:")
        print(f"    旧: {old[:120]}")
        print(f"    新: {na[:120]}")
        # 简单标记是否含烟台/电源等已知 ASR 错字
        for w in ("烟台", "电源"):
            if w in old and w not in na:
                print(f"    [OK] '{w}' 已剔除")
            elif w in old and w in na:
                print(f"    [WARN] '{w}' 仍在新 abstract")


if __name__ == "__main__":
    main()
