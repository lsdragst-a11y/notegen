"""Dry-run 章标题 prompt 回归脚本

用法：
    python scripts/_dryrun_chapter_titles.py <BV id>
    e.g. python scripts/_dryrun_chapter_titles.py BV1EBdcBrEea_p0

从已有 chapters.json + summary.json 读 outline/chunks，调当前代码
里的 refine_chapter_titles，打印新标题 vs 旧标题对比。

不写盘、不改 chapters.json；只验证新 prompt 在已有 outline 上的章标题输出。
"""
import sys, os, json, glob

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from segment_llm import refine_chapter_titles  # noqa: E402


def find_outputs(bv: str):
    pat = f"data/outputs/{bv}.*.chapters.json"
    cand = glob.glob(pat)
    if not cand:
        raise SystemExit(f"no chapters.json for {bv} (pattern: {pat})")
    cand.sort(key=lambda p: ("vl" not in p, len(p)))
    chap = cand[0]
    summ = chap.replace(".chapters.json", ".summary.json")
    if not os.path.exists(summ):
        raise SystemExit(f"summary not found: {summ}")
    return chap, summ


def load_meta_category(bv: str) -> str:
    p = f"web/public/notes/{bv}/meta.json"
    if os.path.exists(p):
        d = json.load(open(p, encoding="utf-8"))
        return d.get("category", "teaching")
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
    chapters = chap_doc["chapters"]
    outline = {"chapters": [{"chunks": ch.get("chunks") or ch.get("indices")}
                            for ch in chapters]}

    category = load_meta_category(bv)
    lang = chap_doc.get("lang") or chap_doc.get("ablation", {}).get("lang", "zh")
    print(f"[category={category}  lang={lang}]")
    print()
    print("=== 旧标题（已有 chapters.json） ===")
    for i, ch in enumerate(chapters):
        print(f"  Ch{i+1}: {ch.get('title')}")
    print()
    print("=== chunks headline + keywords ===")
    for ci, ch in enumerate(chapters):
        idxs = ch.get("chunks") or ch.get("indices") or []
        print(f"  [Ch{ci+1} {ch.get('title')}]")
        for i in idxs:
            c = summary[i]
            hl = c.get("headline", "")
            kws = c.get("keywords", [])[:6]
            print(f"    [{i}] hl='{hl}'  kw={kws}")
    print()
    print("=== 跑 refine_chapter_titles (新 prompt) ===")
    new_titles = refine_chapter_titles(outline, summary,
                                       lang=lang, category=category)
    print()
    print("=== 新旧对比 ===")
    if new_titles is None or len(new_titles) != len(chapters):
        print(f"  refine 返回异常: {new_titles}")
        return
    for i, (ch, nt) in enumerate(zip(chapters, new_titles)):
        old = ch.get("title")
        mark = " (UNCHANGED)" if old == nt else "  <-- CHANGED"
        print(f"  Ch{i+1}: {old!r}  ->  {nt!r}{mark}")


if __name__ == "__main__":
    main()
