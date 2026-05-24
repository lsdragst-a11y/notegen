"""Dry-run 章末自测题 LLM 生成

用法：python scripts/_dryrun_chapter_quizzes.py <BV id>
"""
import sys, os, json, glob

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from segment_llm import generate_chapter_quizzes  # noqa: E402
from summarize import _format_chapter_quiz  # noqa: E402


def find_outputs(bv: str):
    cand = sorted(glob.glob(f"data/outputs/{bv}.*.chapters.json"),
                  key=lambda p: ("vl" not in p, len(p)))
    if not cand:
        raise SystemExit(f"no chapters.json for {bv}")
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

    print("=== 章 list ===")
    for i, ch in enumerate(chap_doc["chapters"]):
        print(f"  Ch{i+1} {ch.get('title')!r}")
    print()

    print("=== 跑 generate_chapter_quizzes ===")
    quizzes = generate_chapter_quizzes(chapters_for_llm, lang=lang)
    print()
    if quizzes is None:
        print("FAILED to parse")
        return

    for i, (ch, qz) in enumerate(zip(chap_doc["chapters"], quizzes)):
        print(f"\n=== Ch{i+1} {ch.get('title')!r} ===")
        qs = qz.get("questions", [])
        print(f"  ({len(qs)} questions)")
        for qi, q in enumerate(qs, 1):
            t = q.get("type")
            if t == "mc":
                opts = q.get("options", [])
                ai = q.get("answer_idx", -1)
                print(f"\n  Q{qi} (mc): {q.get('q')}")
                for oi, opt in enumerate(opts):
                    mark = " ✓" if oi == ai else ""
                    print(f"    {'ABCD'[oi]}. {opt}{mark}")
                print(f"    解析: {q.get('explanation','')}")
            elif t == "tf":
                ans = q.get("answer")
                print(f"\n  Q{qi} (tf): {q.get('q')}")
                print(f"    答案: {'对' if ans else '错'}")
                print(f"    解析: {q.get('explanation','')}")
        # markdown 渲染预览
        print("\n  ---- md 渲染 ----")
        for line in _format_chapter_quiz(qz)[:15]:
            print(f"  {line}")


if __name__ == "__main__":
    main()
