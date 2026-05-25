"""Post-process: strip user-facing `[?]` 字面 from existing chapters.json.

J5 修复部署前生成的笔记（abstract/recap/title/quiz）里可能有 LLM 把 `[?]`
mask 字面复制到输出的污染。该脚本扫描 web/public/notes/*/chapters.json
+ data/outputs/*.chapters.json，原地清理。

用法：
    python scripts/_postfix_qmask.py                       # 扫所有
    python scripts/_postfix_qmask.py path1.json path2.json # 指定文件
"""
import sys, json, os, glob

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from segment_llm import _strip_qmask  # noqa: E402


_FIELDS = ("title", "abstract", "recap",
           "title_zh", "title_en", "abstract_zh", "abstract_en", "recap_en")


def fix_chapter(ch):
    changed = False
    for field in _FIELDS:
        v = ch.get(field)
        if isinstance(v, str) and "[?]" in v:
            new_v = _strip_qmask(v)
            if new_v != v:
                ch[field] = new_v
                changed = True
    quiz = ch.get("quiz") or {}
    for q in quiz.get("questions") or []:
        for f in ("q", "explanation"):
            if isinstance(q.get(f), str) and "[?]" in q[f]:
                q[f] = _strip_qmask(q[f])
                changed = True
        opts = q.get("options")
        if isinstance(opts, list):
            new_opts = [_strip_qmask(o) if isinstance(o, str) and "[?]" in o else o
                        for o in opts]
            if new_opts != opts:
                q["options"] = new_opts
                changed = True
    return changed


def fix_file(path):
    doc = json.load(open(path, encoding="utf-8"))
    if not isinstance(doc, dict):
        return False
    any_changed = False
    for ch in doc.get("chapters") or []:
        if fix_chapter(ch):
            any_changed = True
    if any_changed:
        json.dump(doc, open(path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print(f"  fixed: {path}")
    return any_changed


def main():
    paths = sys.argv[1:]
    if not paths:
        paths = (sorted(glob.glob("web/public/notes/*/chapters.json")) +
                 sorted(glob.glob("data/outputs/*.chapters.json")))
    n_fixed = 0
    for p in paths:
        try:
            if fix_file(p):
                n_fixed += 1
        except Exception as e:
            print(f"  ERROR {p}: {e}")
    print(f"total fixed: {n_fixed}/{len(paths)}")


if __name__ == "__main__":
    main()
