"""跑 refine_chapter_titles N 次，统计采样波动 + 幻觉稳定性。

用法:
    python scripts/_dryrun_chapter_titles_n.py <BV> [N=5]
"""
import sys, os, json, glob, collections

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from segment_llm import refine_chapter_titles  # noqa: E402


def find_outputs(bv: str):
    pat = f"data/outputs/{bv}.*.chapters.json"
    cand = sorted(glob.glob(pat),
                  key=lambda p: ("vl" not in p, len(p)))
    chap = cand[0]
    summ = chap.replace(".chapters.json", ".summary.json")
    return chap, summ


def load_meta_category(bv: str) -> str:
    p = f"web/public/notes/{bv}/meta.json"
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8")).get("category", "teaching")
    return "teaching"


def main():
    bv = sys.argv[1]
    N = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    chap_p, summ_p = find_outputs(bv)
    chap_doc = json.load(open(chap_p, encoding="utf-8"))
    summary = json.load(open(summ_p, encoding="utf-8"))
    chapters = chap_doc["chapters"]
    outline = {"chapters": [{"chunks": ch.get("chunks") or ch.get("indices"),
                             "_split_pair_id": ch.get("_split_pair_id")}
                            for ch in chapters]}
    category = load_meta_category(bv)
    lang = chap_doc.get("lang") or chap_doc.get("ablation", {}).get("lang", "zh")

    print(f"[{bv}] N={N}  category={category}  lang={lang}", flush=True)
    print(f"  old titles:")
    for i, ch in enumerate(chapters):
        print(f"    Ch{i+1}: {ch.get('title')}")

    results = []
    counters = [collections.Counter() for _ in chapters]
    for run in range(N):
        print(f"\n=== run {run+1}/{N} ===", flush=True)
        ts = refine_chapter_titles(outline, summary,
                                   lang=lang, category=category)
        if ts is None:
            print("  parse failed", flush=True)
            continue
        results.append(ts)
        for i, t in enumerate(ts):
            counters[i][t] += 1
            print(f"  Ch{i+1}: {t}")

    print(f"\n=== 稳定性汇总（{len(results)} 次有效） ===")
    for i, c in enumerate(counters):
        old = chapters[i].get("title")
        if not c:
            print(f"  Ch{i+1} (old={old}): no data")
            continue
        most = c.most_common()
        top, n_top = most[0]
        ratio = n_top / max(1, len(results))
        flag = "STABLE" if ratio >= 0.8 else "VARIES"
        print(f"  Ch{i+1} (old={old}): {flag} top={top!r} ({n_top}/{len(results)})")
        if len(most) > 1:
            for t, n in most[1:]:
                print(f"        alt: {t!r} ({n})")

    out_p = f"data/_dryrun_titles_n_{bv}.json"
    json.dump({"bv": bv, "N": N, "lang": lang, "category": category,
               "old": [ch.get("title") for ch in chapters],
               "runs": results,
               "counters": [dict(c) for c in counters]},
              open(out_p, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\n[written] {out_p}")


if __name__ == "__main__":
    main()
