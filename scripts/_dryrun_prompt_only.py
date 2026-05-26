"""只构造 refine_chapter_titles 的 user_prompt，不调 LLM。

用于诊断 chapter title 幻觉根因：导出 LLM 实际看到的 system+user prompt
全文，确认 snippet 里是否有诱导词、哪些 clause 被激活。

用法:
    python scripts/_dryrun_prompt_only.py <BV>
"""
import sys, os, json, glob, re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# 不 import refine_chapter_titles（会触发 transformers 加载），直接复刻 prompt 构造
from segment_llm import (
    _mask_kws_by_prob, _calibrate_headline_words,
    TITLE_CHAPTER_SYSTEM, TITLE_CHAPTER_VLOG_SYSTEM,
    _system_with_lang,
)


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


def build_prompt(chapters, chunks, lang, category):
    """复刻 refine_chapter_titles 的 prompt 构造逻辑，只产文本不调模型"""
    K = len(chapters)
    lines = []
    any_drop = False
    n_dup_chs = sum(
        1 for ch in chapters
        if len(ch.get("chunks") or []) >= 2
        and len({(chunks[i].get("headline") or "").strip()
                 for i in ch["chunks"] if i < len(chunks)}) <= 1
    )
    any_dup_headlines = n_dup_chs >= 1
    for ci, ch in enumerate(chapters):
        lines.append(f"[第 {ci+1} 章]")
        for idx in ch["chunks"]:
            c = chunks[idx]
            hl = c.get("headline") or c.get("text", "")[:30]
            kws = _mask_kws_by_prob(c.get("keywords") or [], c)
            text = c.get("text", "") or ""
            kws_str = " / ".join(str(k) for k in kws[:5]) if kws else "(无)"
            cal = _calibrate_headline_words(hl, kws, text)
            line = f"  - 段标题: {hl}  | 高频词: {kws_str}"
            if cal["drop"]:
                any_drop = True
                line += f"  | ⚠️ 已识别 ASR 错字 (禁用): {', '.join(cal['drop'])}"
            lines.append(line)
            snippet = (c.get("summary") or "").strip() or text[:120].strip()
            if snippet:
                snippet = snippet[:120].replace("\n", " ")
                lines.append(f"    内容: {snippet}")
    body = "\n".join(lines)

    drop_clause = (
        "\n⚠️ 标注了「已识别 ASR 错字」的词是 Python 校准过的，**绝对禁止**\n"
        "进入任何章/片段标题。若该段所有关键名词都被标禁，则该段不能单独主导\n"
        "命名，必须借同章其他段或共同高频词抽象。\n"
        if any_drop else "")

    pair_map = {}
    for ci, ch in enumerate(chapters):
        pid = ch.get("_split_pair_id")
        if pid:
            pair_map.setdefault(pid, []).append(ci + 1)
    sibling_clause = ""
    if pair_map:
        sibling_lines = []
        for pid, sib_chs in pair_map.items():
            if len(sib_chs) >= 2:
                sib_str = " / ".join(f"第 {x} 章" for x in sib_chs)
                sibling_lines.append(f"  - {sib_str}")
        if sibling_lines:
            sibling_clause = (
                "\n⚠️ **姊妹章差异命名硬约束**...\n"
                + "\n".join(sibling_lines) + "\n")

    dup_headline_clause = (
        "\n⚠️ **同标题段内容差异命名硬约束**：本批输入里有 "
        f"{n_dup_chs} 章内所有段标题完全相同（chunker 对同主题后半段塌成同一\n"
        "headline）。这些章节**绝对不能**用\"段标题\"作为章标题词根——必须从\n"
        "**「内容」行（ASR 摘要）**抽出本章独有的子机制 / 步骤 / 对象 /\n"
        "实例对象，再拼章标题。共享前缀（如多章都以\"服务程序X\"/\"中断X\"开头）\n"
        "是失败模式，每章必须用不重叠的核心名词锚定。\n"
        if any_dup_headlines else "")

    prefix_clause = (
        "\n⚠️ **共享前缀禁令**：K 个章标题里**禁止 ≥3 个**共享同一个 ≥2 字前缀\n"
        "（如不允许 ch3=\"服务程序详解\" + ch4=\"服务程序执行\" + ch5=\"服务程序恢复\"）。\n"
        "若同主题被切成多章，必须用各章「内容」行里的独有概念（如 PC 保存 / \n"
        "向量地址 / 多重屏蔽 / 微秒例题）锚定，避免前缀雷同。\n")

    user_prompt = (f"共 {K} 章/片段，请按顺序命名。\n"
                   f"{drop_clause}{sibling_clause}{dup_headline_clause}{prefix_clause}\n"
                   f"{body}\n\n"
                   f"输出 JSON 数组（必须 {K} 个元素）：")

    sys_prompt = (TITLE_CHAPTER_VLOG_SYSTEM if category in ("vlog", "talk")
                  else TITLE_CHAPTER_SYSTEM)
    sys_prompt = _system_with_lang(sys_prompt, lang, "title")

    return sys_prompt, user_prompt, {
        "K": K, "n_dup_chs": n_dup_chs, "any_dup_headlines": any_dup_headlines,
        "any_drop": any_drop, "n_sibling_pairs": len(pair_map),
    }


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
    outline_chapters = [
        {"chunks": ch.get("chunks") or ch.get("indices"),
         "_split_pair_id": ch.get("_split_pair_id")}
        for ch in chapters
    ]
    category = load_meta_category(bv)
    lang = chap_doc.get("lang") or chap_doc.get("ablation", {}).get("lang", "zh")

    sys_p, user_p, meta = build_prompt(outline_chapters, summary, lang, category)
    out_p = f"data/_dryrun_prompt_{bv}.txt"
    with open(out_p, "w", encoding="utf-8") as f:
        f.write(f"[meta] {meta}\n[category={category} lang={lang}]\n\n")
        f.write("========== SYSTEM PROMPT ==========\n")
        f.write(sys_p + "\n\n")
        f.write("========== USER PROMPT ==========\n")
        f.write(user_p + "\n\n")
        f.write("========== Hallucination probe ==========\n")
        for tok in ("四维", "万维网", "网页", "HTML", "事实", "建立", "框架"):
            f.write(f"  sys  '{tok}' x {sys_p.count(tok)}    user '{tok}' x {user_p.count(tok)}\n")
    print(f"[meta] {meta}")
    print(f"[written] {out_p}")
    for tok in ("四维", "万维网", "网页", "HTML", "事实", "建立", "框架"):
        print(f"  sys '{tok}' x {sys_p.count(tok)} | user '{tok}' x {user_p.count(tok)}")


if __name__ == "__main__":
    main()
