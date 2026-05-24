"""Dry-run 章末复习要点 LLM 生成测试

用法：python scripts/_dryrun_chapter_recaps.py <BV id>
"""
import sys, os, json, glob

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from segment_llm import generate_chapter_recaps  # noqa: E402


def find_outputs(bv: str):
    pat = f"data/outputs/{bv}.*.chapters.json"
    cand = glob.glob(pat)
    if not cand:
        raise SystemExit(f"no chapters.json for {bv}")
    cand.sort(key=lambda p: ("vl" not in p, len(p)))
    return cand[0], cand[0].replace(".chapters.json", ".summary.json")


def load_category(bv: str) -> str:
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
    chap_doc = json.load(open(chap_p, encoding="utf-8"))
    summary = json.load(open(summ_p, encoding="utf-8"))
    cat = load_category(bv)
    lang = chap_doc.get("lang") or chap_doc.get("ablation", {}).get("lang", "zh")
    print(f"[category={cat}  lang={lang}]\n")

    chapters_for_llm = []
    for ch in chap_doc["chapters"]:
        idxs = ch.get("chunks") or ch.get("indices") or []
        chunks_inline = [{
            "headline": summary[i].get("headline", ""),
            "keywords": summary[i].get("keywords", []),
            "text": summary[i].get("text", ""),
            "summary": summary[i].get("summary", ""),
        } for i in idxs]
        chapters_for_llm.append({"title": ch.get("title", ""),
                                  "chunks": chunks_inline})

    if cat in ("vlog", "talk"):
        print(f"warning: category={cat}，按设计 recap 不生成；强制跑测试")

    print("=== 章标题与既有 abstract ===")
    for i, ch in enumerate(chap_doc["chapters"]):
        print(f"  Ch{i+1} {ch.get('title')!r}")
        print(f"    abstract: {(ch.get('abstract','') or '')[:80]}")
    print()

    print("=== 跑 generate_chapter_recaps ===")
    recaps = generate_chapter_recaps(chapters_for_llm, lang=lang)
    print()
    if recaps is None:
        print("FAILED")
        return
    print("=== 各章 recap ===")
    for i, (ch, r) in enumerate(zip(chap_doc["chapters"], recaps)):
        print(f"  Ch{i+1} {ch.get('title')!r}:")
        for ln in r.split("\n"):
            print(f"    {ln}")
        print()


if __name__ == "__main__":
    main()
