"""Post-process: 修历史 chapters.json 章标题/abstract/recap 里的 ASR 同音字渗透。

J4 fallback 路径（n>15 长视频）下章标题用 chunker keyword，chunker keyword
可能含 ASR 错字（"中段"="中断"被听错），LLM segment 复用时 sticky 渗透到
user-facing 章标题。L1 ASR 字典扩展只能修未来跑批，L2 工具修已有 commit。

工具用 _ASR_TITLE_FIXES（{正确词: [错字变体]} map），逐字段扫 title /
abstract / recap / quiz + _zh/_en 双语镜像。仅替换章标题/短文本字段，
避免长 ASR 正文里"中段"合法用法被误伤。

用法：
    python scripts/_postfix_asr_titles.py                    # 扫所有
    python scripts/_postfix_asr_titles.py path1 path2 ...    # 指定文件
"""
import sys, json, os, glob, re


# {正确词: [ASR 错字变体]} — 章标题/短文本场景下命中即直接替换。
# 这里只放"在通用中文里几乎不出现的组合" + "短文本里替换风险低的"。
# 长 ASR 正文用 _DOMAIN_CORRECTIONS 的 substring 版本（带上下文）。
_ASR_TITLE_FIXES: dict[str, list[str]] = {
    # 计组 中断系统 (BV1BE411D7ii p68)
    "中断": ["中段"],         # 章标题/abstract/recap 里"中段"几乎都是错字
    "中断源": ["中断元", "中段元", "中段源"],
    # 计网 (已有 _DOMAIN_CORRECTIONS["network"] 但 J4 fallback 章标题层兜底)
    "数据帧": ["数据针"],
    "首部": ["手部"],
    "路由": ["路游", "路有", "路约", "路後"],
    "权值": ["全值"],
    "邻接": ["临接"],
    "洪泛": ["红犯"],
    "拥塞": ["拥测", "拥色", "拥瑟"],
    # OS (王道 OS 系列)
    "管程": ["广程", "光程"],
    "互斥": ["互析"],
    # 通用繁体（_GLOBAL_CORRECTIONS 已 cover 字符级，这里 cover 章标题里
    # 偶发的多字繁体词）
}


_FIELDS_STRING = ("title", "abstract",
                  "title_zh", "title_en",
                  "abstract_zh", "abstract_en")
_FIELDS_MULTILINE = ("recap", "recap_en")


def _fix_text(s: str) -> tuple[str, int]:
    """Return (修复后字符串, 替换次数)."""
    n = 0
    for right, wrongs in _ASR_TITLE_FIXES.items():
        for w in wrongs:
            if w in s:
                cnt = s.count(w)
                s = s.replace(w, right)
                n += cnt
    return s, n


def fix_chapter(ch: dict) -> int:
    total = 0
    for f in _FIELDS_STRING:
        v = ch.get(f)
        if isinstance(v, str):
            new_v, n = _fix_text(v)
            if n:
                ch[f] = new_v
                total += n
    for f in _FIELDS_MULTILINE:
        v = ch.get(f)
        if isinstance(v, str):
            new_v, n = _fix_text(v)
            if n:
                ch[f] = new_v
                total += n
    # quiz q/explanation/options
    quiz = ch.get("quiz") or {}
    for q in quiz.get("questions") or []:
        for f in ("q", "explanation"):
            v = q.get(f)
            if isinstance(v, str):
                new_v, n = _fix_text(v)
                if n:
                    q[f] = new_v
                    total += n
        opts = q.get("options")
        if isinstance(opts, list):
            new_opts = []
            changed = False
            for o in opts:
                if isinstance(o, str):
                    new_o, n = _fix_text(o)
                    new_opts.append(new_o)
                    if n:
                        total += n
                        changed = True
                else:
                    new_opts.append(o)
            if changed:
                q["options"] = new_opts
    return total


def fix_file(path: str) -> int:
    doc = json.load(open(path, encoding="utf-8"))
    if not isinstance(doc, dict):
        return 0
    total = 0
    for ch in doc.get("chapters") or []:
        total += fix_chapter(ch)
    if total:
        json.dump(doc, open(path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print(f"  fixed {total:3d}: {path}")
    return total


def main():
    paths = sys.argv[1:]
    if not paths:
        paths = (sorted(glob.glob("web/public/notes/*/chapters.json")) +
                 sorted(glob.glob("data/outputs/*.chapters.json")))
    n_files, n_total = 0, 0
    for p in paths:
        try:
            n = fix_file(p)
            if n:
                n_files += 1
                n_total += n
        except Exception as e:
            print(f"  ERROR {p}: {e}")
    print(f"total: {n_total} replacements in {n_files}/{len(paths)} files")


if __name__ == "__main__":
    main()
