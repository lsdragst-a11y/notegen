"""用 Qwen2.5-7B-Instruct-AWQ 做层级化章节切分。

输入：现有 chunk 列表（{start, end, text/headline, keywords}）—— 用 TextTiling
出来的"原子段"作为 LLM 的最小单位，让 LLM 只决定怎么组合 + 命名而不用造时间戳。

输出：层级章节树
[
  {"title": "...", "start": s, "end": e, "indices": [0,1,2],
   "children": [{"title": "...", "start", "end", "indices": [0,1]}, ...]},
  ...
]

设计要点：
- 模型 4-bit AWQ 量化，~5GB VRAM；进程内 lazy load + 全局 singleton
- 与 faster-whisper 同 GPU：调用前清 _MODEL + torch.cuda.empty_cache()
- JSON 严格模式：generation_config 设 temperature=0.3，prompt 喂"严格 JSON"约束
- 解析失败时 fallback 返回 flat 章节（每个 chunk = 1 章），不 break pipeline
"""
from __future__ import annotations

import gc
import json
import os
import re
from typing import Optional


_MODEL = None
_TOKENIZER = None

_DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct-AWQ"


def _format_time(s: float) -> str:
    s = int(s)
    return f"{s // 60:02d}:{s % 60:02d}"


def load_model(model_id: str = _DEFAULT_MODEL):
    """懒加载 Qwen2.5-7B-Instruct-AWQ。返回 (model, tokenizer)。
    第一次加载约 30-60s + 4-5GB VRAM。"""
    global _MODEL, _TOKENIZER
    if _MODEL is not None:
        return _MODEL, _TOKENIZER

    # 释放前置模型占的 VRAM：Whisper（asr._MODEL）/ Pegasus（summarize_neural._CACHE）/
    # ChineseCLIP（keyframe._CACHE）。12GB VRAM 上 Qwen 5GB 必须等它们让位才不 OOM
    def _clear_mod(mod_name: str, attr_name: str):
        try:
            mod = __import__(mod_name)
        except Exception:
            return
        cur = getattr(mod, attr_name, None)
        if cur is None:
            return
        if isinstance(cur, dict):
            cur.clear()
        else:
            setattr(mod, attr_name, None)
    _clear_mod("asr", "_MODEL")
    _clear_mod("summarize_neural", "_CACHE")
    _clear_mod("keyframe", "_CACHE")
    try:
        import torch
        gc.collect()
        torch.cuda.empty_cache()
        if torch.cuda.is_available():
            free_gb = torch.cuda.mem_get_info()[0] / 1024**3
            print(f"      [llm] VRAM free after cleanup: {free_gb:.1f} GB", flush=True)
    except Exception:
        pass

    # 尝试本地 models/ 副本；不存在退回 HF 仓库 ID
    from pathlib import Path
    local = Path("models") / "Qwen2.5-7B-Instruct-AWQ"
    if local.exists():
        model_path = str(local)
        print(f"      [llm] load from local: {local}", flush=True)
    else:
        model_path = model_id
        print(f"      [llm] load from HF: {model_id}（首次会下载 ~5GB）", flush=True)

    # autoawq 0.2.6 跟 transformers 4.57 多处 import 不兼容（autoawq 0.2.9 需要
    # triton 在 Windows 上没 wheel），所以打 shim 让 awq lib 能 import 通过：
    #   - shard_checkpoint：transformers 4.46+ 删了，autoawq 量化路径用，推理用不到
    #   - PytorchGELUTanh：transformers 4.57 改了模块组织
    #   - datasets：calib_data.py 触发 pyarrow native segfault（不需要校准就用 stub）
    # 这些 shim 只为让 import 链不炸，实际推理走 transformers native AWQ + autoawq_kernels
    import sys as _sys
    import types as _types
    if "datasets" not in _sys.modules:
        _ds_stub = _types.ModuleType("datasets")
        _ds_stub.load_dataset = lambda *a, **k: None
        _sys.modules["datasets"] = _ds_stub
    import transformers.modeling_utils as _mu
    if not hasattr(_mu, "shard_checkpoint"):
        _mu.shard_checkpoint = lambda *a, **k: None
    import transformers.activations as _ta
    import torch.nn as _nn
    for _sym in ("PytorchGELUTanh", "NewGELUActivation", "GELUActivation"):
        if not hasattr(_ta, _sym):
            setattr(_ta, _sym, _nn.GELU)

    from transformers import AutoModelForCausalLM, AutoTokenizer
    import torch
    _TOKENIZER = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    _MODEL = AutoModelForCausalLM.from_pretrained(
        model_path,
        torch_dtype=torch.float16,
        device_map="cuda:0",
        trust_remote_code=True,
    )
    _MODEL.eval()
    print(f"      [llm] model loaded", flush=True)
    return _MODEL, _TOKENIZER


def _build_chunk_summary(chunks: list[dict], headlines: Optional[list[str]] = None) -> str:
    """生成喂给 LLM 的 chunk 清单文本。每个 chunk 两行：
      [N  mm:ss - mm:ss] headline · kw1, kw2, kw3
       原文摘录: 前 80 字
    给 LLM 更多语境，避免它只看 headline 关键词就误判（例如"网络适配器"
    在某些段实际指无线网卡，在另一些段指通用网卡）
    """
    lines = []
    for i, c in enumerate(chunks):
        start = _format_time(c.get("start", 0))
        end = _format_time(c.get("end", 0))
        hl = (headlines[i] if headlines and i < len(headlines)
              else c.get("headline") or c.get("text", "")[:30])
        kws = c.get("keywords") or []
        kw_part = " · " + ", ".join(kws[:5]) if kws else ""
        # 取首尾各 100 字：开头反映本段主题切入，结尾若有过渡句反映边界信号
        full = (c.get("text") or "").replace("\n", " ").strip()
        head = full[:100]
        tail = full[-100:] if len(full) > 200 else ""
        lines.append(f"[Chunk {i:02d}  {start}-{end}]  {hl}{kw_part}")
        if head:
            lines.append(f"  开头: {head}")
        if tail:
            lines.append(f"  结尾: {tail}")
    return "\n".join(lines)


# lang=en 时追加在 system prompt 末尾的强语言约束。中文 prompt + 中文 few-shot
# 容易让 Qwen 跟随中文输出（即使 headlines 是英文，abstract 任务实测 100% 出中文）。
# 加这个 override 后 Qwen 在英文输入时输出英文 title/abstract。
_LANG_EN_OVERRIDES = {
    "segment": """

# ====== LANGUAGE OVERRIDE: ENGLISH ======
**The chunk headlines/keywords are in ENGLISH.** Therefore in your output JSON:
- Every `title` MUST be in English (3-7 word noun phrase, no trailing punctuation)
- DO NOT translate, DO NOT output Chinese characters in any title field
- If you find yourself writing 中文 in a title, that is a critical error — restart

The Chinese examples in the system prompt above show the STRUCTURE only —
keep the same compact multi-chapter JSON shape, just translate every title
to English. For n_chunks >= 12 you should output 5-10 chapters covering ALL
chunk_idx from 0 to n-1. DO NOT stop after 2-3 chapters.""",
    "title": """

# ====== LANGUAGE OVERRIDE: ENGLISH ======
**Input headlines are in ENGLISH.** Output every chapter title in English (3-7 word noun phrase).
DO NOT translate to Chinese. DO NOT write 中文 in any element of the JSON array.

Concrete English example:
Input:
[Chapter 1]
  - What an AI Agent Is
  - Agent vs Automation
[Chapter 2]
  - Choosing an LLM Provider
  - API Key Setup

Output:
["AI Agent Fundamentals", "LLM Provider and API Setup"]""",
    "abstract": """

# ====== LANGUAGE OVERRIDE: ENGLISH ======
**Input headlines/titles are in ENGLISH.** Output every abstract in English.

CRITICAL RULES for English mode:
- Each abstract: 15-50 words, starts with "This chapter ..." / "This section ..." (NOT "本章")
- DO NOT output any Chinese character. If you start with 本章, restart immediately.
- Mention 1-2 concrete technical points from the chapter (concept/algorithm/method names)
- Cover all parallel sub-topics if the chapter has them (e.g. "store-and-forward AND cut-through")

Concrete English example:
Input:
[Chapter 1: AI Agent Fundamentals]
  - What an AI Agent Is
  - Agent vs Automation
[Chapter 2: LLM Provider and API Setup]
  - Choosing an LLM Provider
  - API Key Setup

Output:
["This chapter defines an AI agent as an autonomous system that reasons, plans, and acts, and distinguishes it from rule-based automations.", "This chapter walks through choosing an LLM provider and configuring an API key for the agent."]""",
    "headlines": """

# ====== LANGUAGE OVERRIDE: ENGLISH ======
**Chunk text is in ENGLISH.** Output every headline in English (3-8 word noun phrase, no end punctuation).
DO NOT translate to Chinese. DO NOT output any Chinese character.

Concrete English example:
Input:
[Chunk 00] keywords: agent, automation, weather
  Opening: AI agents are one of the most exciting areas of AI...
Output: ["AI Agent vs Automation Definition"]""",
    "refine_headlines": """

# ====== LANGUAGE OVERRIDE: ENGLISH ======
**Input text is in ENGLISH.** Output every refined headline in English (3-8 word noun phrase).
DO NOT translate. DO NOT output Chinese characters.""",
}


def _system_with_lang(base_prompt: str, lang: str, task: str) -> str:
    """lang=en 时给 system prompt 追加英文强约束 + 英文示例，其它语言保持原 prompt。"""
    if lang == "en" and task in _LANG_EN_OVERRIDES:
        return base_prompt + _LANG_EN_OVERRIDES[task]
    return base_prompt


SYSTEM_PROMPT = """你是教学视频结构化助手。给定一个教学视频按时间顺序的"原子段"\
（每段有索引、时间范围、headline、关键词），把它们组织成符合教学逻辑的层级化章节大纲。

**⚠️ 输出语言匹配输入 headlines**：headlines 是英文则章标题用英文，中文则用中文。\
**不要翻译**——保持原语言一致。

## 硬约束（违反必拒绝，自检通不过就重新切）

1. **顶层数量 ∈ [3, 6]**——视频再单一也能找出"引入 / 主体 1 / 主体 2 / 收尾"等多个主轴
2. **单个顶层覆盖的 chunks 数 ≤ 5**——超 5 就拆，要么内部分子章节，要么再切个顶层
3. 顶层按时间顺序覆盖 [0, n) 全部 chunk_idx，不漏不重不交叉；children 同样
4. 标题 6-12 字中文 或 3-7 词英文 名词短语，去口语词 / 疑问句 / 句末标点
5. **章标题必须从本章内 chunks 的 headlines 抽象**——只能用本章 chunks 实际涉及的概念，
   **绝对禁止**借用前后邻章的 headline 名词。如果本章内 chunks 跨多个并列主题，标题
   用 "X 与 Y" 形式覆盖本章内的主题；不要把邻章主题写进本章标题。

## 切分思路

顶层应反映**教学逻辑的主轴**而非时间分块：
- 分类对比（A vs B、有线 vs 无线、内核态 vs 用户态）
- 抽象层次（概念 → 实现 → 硬件 → 应用）
- 流程步骤（步骤 1 → 2 → 3）

**特殊处理**：
- 视频开头 1-2 段 "概念引入 / 背景介绍" 独立成第一个顶层
- 硬件/实现层（网卡、CSMA-CD、双绞线、串并行转换等）独立顶层
- 数据链路细节（MAC 帧、广播域、交换机）独立顶层
- 看每段"开头/结尾"原文找主题切换信号（"接下来看 X"、"另一个话题是 Y"、"我们再看 Z"）

## 完整示例 A（综述类，11 段，跨主题）

输入摘要：局域网引入(0,1) + 以太网/双绞线/CSMA-CD(2-6) + 无线网(7) + 网卡硬件(8-10)

```json
{
  "chapters": [
    {"title": "局域网概念引入", "chunks": [0, 1]},
    {"title": "有线以太网体系", "chunks": [2, 3, 4, 5, 6], "children": [
      {"title": "双绞线物理介质", "chunks": [2, 3]},
      {"title": "CSMA-CD 与帧格式", "chunks": [4, 5, 6]}
    ]},
    {"title": "无线局域网", "chunks": [7]},
    {"title": "网络适配器硬件", "chunks": [8, 9, 10]}
  ]
}
```

## 完整示例 B（专题深入，11 段，主题集中但层次分明）

输入摘要：IEEE 802.3 引入(0) + 物理介质(1,2,3) + 全双工(4) + MAC 帧(5,6) + 交换机/广播域(7,8,9) + 物理层标准(10)

```json
{
  "chapters": [
    {"title": "IEEE 802.3 标准引入", "chunks": [0]},
    {"title": "物理介质连接", "chunks": [1, 2, 3]},
    {"title": "全双工通信", "chunks": [4]},
    {"title": "MAC 帧结构", "chunks": [5, 6]},
    {"title": "交换机与广播域", "chunks": [7, 8, 9]},
    {"title": "以太网物理层标准", "chunks": [10]}
  ]
}
```

## 反例（**绝对不要**）

```json
{"chapters": [
  {"title": "IEEE 802.3 引入", "chunks": [0]},
  {"title": "传输介质与通信模式", "chunks": [1,2,3,4,5,6,7,8,9,10]}
]}
```
← 第 2 个顶层 10 chunks，违反"≤ 5"硬约束。即使加 children 也不行——拆成多个顶层。

## 自检清单（输出前 mentally verify）

1. 顶层数量在 [3, 6] ✓
2. **没有任何顶层 chunks 数 > 5** ✓（这条最容易踩）
3. 所有 chunk_idx 覆盖 [0, n) 一次，无重 / 无漏 ✓
4. 标题是名词短语，不是动词句 / 疑问句 ✓
5. **每个章标题的关键词必须在本章 chunks 的 headlines 里出现过**——若标题里出现某词，
   而本章 chunks 的 headlines 都没提，那是窜章了，必须改 ✓

只输出 JSON，不要 markdown fence、不要解释、不要前言。"""


def _extract_json(text: str) -> Optional[dict]:
    """从 LLM 输出里抽出 JSON 部分。容忍 ```json ... ``` 包裹或前后文。"""
    # 优先 fenced code
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    # 否则 first { ... last }
    else:
        l = text.find("{")
        r = text.rfind("}")
        if l < 0 or r <= l:
            return None
        text = text[l:r + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _promote_oversized(outline: dict, max_chunks_per_top: int = 5) -> dict:
    """后处理：如果某顶层 chunks > max_chunks_per_top 且有 children，把 children
    全部提升为顶层（drop 该 parent）。模型经常把"专题视频"塞成 1 个 catch-all 顶层
    + 多个细分 children，实际上 children 才是合理的顶层结构。"""
    out_chapters = []
    for ch in outline.get("chapters", []):
        chunks = ch.get("chunks", [])
        children = ch.get("children") or []
        if len(chunks) > max_chunks_per_top and children:
            # 把 children 提升为独立顶层（删掉 parent 包装）
            for sub in children:
                out_chapters.append({
                    "title": sub["title"],
                    "chunks": sub["chunks"],
                    # 提升后不再有 children 嵌套（保持 2 层而非 3 层）
                })
        else:
            out_chapters.append(ch)
    return {"chapters": out_chapters}


def _repair_oversize(parsed: dict, chunks: list[dict],
                      max_chunks_per_top: int = 5) -> dict:
    """把 chunks > max 的 catch-all 顶层程序化拆成 ≤ max 的子段。
    用 chunks 间 keyword Jaccard 距离找内部最大跳变拆点；keyword 信息不全时
    均分兜底。新增子段命名 "{orig title} (Pt N)"。

    Motivation: Qwen 在英文 30+ chunks 视频上有 catch-all bias（[[project-english-video-support]]
    经验），prompt 工程无法根治；retry-with-feedback 也常不收敛。`_promote_oversized`
    只能救"有 children"的 case，没 children 的 catch-all 需要这个程序化兜底。
    """
    new_chapters = []
    for ch in parsed.get("chapters", []):
        chs = sorted(set(c for c in (ch.get("chunks") or []) if isinstance(c, int)))
        children = ch.get("children") or []
        if len(chs) <= max_chunks_per_top or children:
            new_chapters.append(ch)
            continue
        title = ch.get("title", "") or "Section"
        n_parts = (len(chs) + max_chunks_per_top - 1) // max_chunks_per_top  # ceil
        # 间隙 i 对应 chs[i] -> chs[i+1] 的语义距离（1 - Jaccard）
        gaps: list[tuple[int, float]] = []
        for i in range(len(chs) - 1):
            ai, bi = chs[i], chs[i + 1]
            if ai >= len(chunks) or bi >= len(chunks):
                gaps.append((i, 0.5))
                continue
            ka = set(chunks[ai].get("keywords") or [])
            kb = set(chunks[bi].get("keywords") or [])
            jac = len(ka & kb) / len(ka | kb) if (ka and kb) else 0.0
            gaps.append((i, 1.0 - jac))
        # 取 top n_parts-1 个最大间隙做拆点（间隙序号 = 拆点在 chs[i] 后）
        split_after = sorted([g[0] for g in sorted(gaps, key=lambda x: -x[1])[:n_parts - 1]])
        parts: list[list[int]] = []
        start = 0
        for sa in split_after:
            parts.append(chs[start:sa + 1])
            start = sa + 1
        parts.append(chs[start:])
        # 校验：拆完仍有 > max 的部分（语义拆点不均），fallback 均分
        if any(len(p) > max_chunks_per_top for p in parts):
            parts = [chs[i:i + max_chunks_per_top]
                     for i in range(0, len(chs), max_chunks_per_top)]
        for pi, p in enumerate(parts, 1):
            new_chapters.append({
                "title": f"{title} (Pt {pi})" if len(parts) > 1 else title,
                "chunks": p,
            })
        print(f"      [repair-oversize] '{title}' {len(chs)} chunks -> "
              f"{len(parts)} parts {[len(p) for p in parts]}", flush=True)
    return {"chapters": new_chapters}


def _repair_missing_chunks(parsed: dict, n_chunks: int) -> Optional[dict]:
    """把漏的 chunk_idx 加到时间最近的顶层（左邻优先）。

    Never abort：找不到归属的 missing 单独成新章（chapters 全为空时），
    保证所有 chunks 都被覆盖。这样后续 `_repair_oversize` 可以接力拆超 5 顶层。
    旧版遇到一个找不到归属的 missing 就 `return None` 让整个 repair chain 退出，
    BV1S6kQBNEJq 实测在 LLM 输出被截 chapters 部分残缺时触发 → fallback TextTiling。
    """
    chapters = parsed.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        chapters = []
        parsed["chapters"] = chapters
    seen: set[int] = set()
    for ch in chapters:
        for c in ch.get("chunks", []) or []:
            if isinstance(c, int):
                seen.add(c)
    missing = sorted(set(range(n_chunks)) - seen)
    if not missing:
        return parsed
    # 收集没归属的 missing —— 后面合并成新章节，按时间相邻成块
    orphans: list[int] = []
    for m in missing:
        best_ci, best_dist = None, float("inf")
        for ci, ch in enumerate(chapters):
            chs = [c for c in (ch.get("chunks") or []) if isinstance(c, int)]
            if not chs:
                continue
            left = [c for c in chs if c < m]
            right = [c for c in chs if c > m]
            if left:
                dist = (m - max(left)) - 0.1  # 左邻略优先（继续上一章话题）
            elif right:
                dist = min(right) - m
            else:
                dist = float("inf")
            if dist < best_dist:
                best_dist = dist
                best_ci = ci
        if best_ci is None:
            orphans.append(m)
            continue
        chapters[best_ci]["chunks"] = sorted(set(
            (chapters[best_ci].get("chunks") or []) + [m]))
    # 把 orphans 切成连续段，每段成一个新顶层（title 留 placeholder，
    # 由后续 refine_chapter_titles 重写）
    if orphans:
        cur_run: list[int] = []
        for m in orphans:
            if cur_run and m == cur_run[-1] + 1:
                cur_run.append(m)
            else:
                if cur_run:
                    chapters.append({"title": "Orphan Section", "chunks": cur_run})
                cur_run = [m]
        if cur_run:
            chapters.append({"title": "Orphan Section", "chunks": cur_run})
        print(f"      [repair-missing] {len(orphans)} chunks 无归属，"
              f"新建 {sum(1 for c in chapters if c.get('title') == 'Orphan Section')} "
              f"个 placeholder 顶层", flush=True)
        # 按起始 chunk 重新排序顶层（保证时间顺序）
        chapters.sort(key=lambda c: min(
            (x for x in (c.get("chunks") or []) if isinstance(x, int)),
            default=10**9))
        parsed["chapters"] = chapters
    return parsed


def _diagnose_outline(parsed: dict, n_chunks: int) -> Optional[str]:
    """validation 失败时给 LLM 的人类可读 feedback。通过返回 None。"""
    if not isinstance(parsed, dict) or "chapters" not in parsed:
        return "顶层 JSON 缺少 'chapters' 字段"
    chapters = parsed.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        return "'chapters' 字段为空数组或类型错误"
    seen: list[int] = []
    for ci, ch in enumerate(chapters):
        if not isinstance(ch, dict):
            return f"第 {ci+1} 章不是 JSON 对象"
        if "chunks" not in ch:
            return f"第 {ci+1} 章缺少 chunks 字段"
        chs = ch.get("chunks", [])
        if not isinstance(chs, list) or not all(isinstance(x, int) for x in chs):
            return f"第 {ci+1} 章 chunks 必须是整数数组"
        out_of_range = [x for x in chs if x < 0 or x >= n_chunks]
        if out_of_range:
            return f"第 {ci+1} 章 chunks 含越界索引 {out_of_range}（合法范围 0~{n_chunks-1}）"
        chs_set = sorted(set(chs))
        seen.extend(chs_set)
        # >5 + no children 的硬性检查
        children = ch.get("children")
        has_children = isinstance(children, list) and len(children) > 0
        if len(chs_set) > 5 and not has_children:
            return (f"第 {ci+1} 章 '{ch.get('title','')}' 覆盖 {len(chs_set)} 个 chunks "
                    f"超过 5 个上限，必须拆为多个顶层（推荐每顶层 1-4 chunks）")
    # 重叠 / 缺失检查
    duplicates = sorted(set([x for x in seen if seen.count(x) > 1]))
    if duplicates:
        return f"chunk_idx {duplicates} 出现在多个顶层（不允许跨章重叠）"
    missing = sorted(set(range(n_chunks)) - set(seen))
    if missing:
        return f"缺少 chunk_idx {missing}（必须覆盖 0~{n_chunks-1} 全部，不能漏）"
    if n_chunks >= 4 and len(chapters) < 3:
        return f"只切了 {len(chapters)} 个顶层（n_chunks={n_chunks} 应至少 3 个顶层）"
    return None


def _validate_outline(outline: dict, n_chunks: int) -> Optional[dict]:
    """校验 LLM 输出：chunks 必须覆盖 [0, n_chunks) 全部，按顺序，无重叠。
    通过返回规整后的 outline；不通过返回 None。
    """
    if not isinstance(outline, dict) or "chapters" not in outline:
        return None
    chapters = outline.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        return None
    seen: list[int] = []
    out_chapters = []
    for ch in chapters:
        if not isinstance(ch, dict) or "title" not in ch or "chunks" not in ch:
            return None
        chs = ch["chunks"]
        if not isinstance(chs, list) or not all(isinstance(x, int) for x in chs):
            return None
        chs = sorted(set(chs))
        if not chs or any(x < 0 or x >= n_chunks for x in chs):
            return None
        seen.extend(chs)
        ch_out = {"title": str(ch["title"]).strip(), "chunks": chs}
        # 校验 children
        children = ch.get("children")
        if isinstance(children, list) and children:
            child_seen: list[int] = []
            out_children = []
            for sub in children:
                if not isinstance(sub, dict) or "title" not in sub or "chunks" not in sub:
                    continue
                sc = sub["chunks"]
                if not isinstance(sc, list):
                    continue
                sc = sorted(set(x for x in sc if isinstance(x, int) and x in chs))
                if not sc:
                    continue
                child_seen.extend(sc)
                out_children.append({"title": str(sub["title"]).strip(), "chunks": sc})
            # children chunks 必须不重叠且覆盖父 chunks 全部
            if sorted(child_seen) == chs:
                ch_out["children"] = out_children
        out_chapters.append(ch_out)
    # 顶层 chunks 必须正好是 [0, n_chunks) 的有序划分
    if sorted(seen) != list(range(n_chunks)):
        return None
    # 硬约束：promote 后仍有 >5 chunks 顶层且无 children → 视为 catch-all 失败，
    # caller 应 fallback 到 TextTiling（继续输出反而骗用户）
    for ch in out_chapters:
        if len(ch["chunks"]) > 5 and not ch.get("children"):
            return None
    # 顶层数量软下限：n_chunks≥4 时至少 3 个顶层（避免 LLM 只切 1-2 个）
    if n_chunks >= 4 and len(out_chapters) < 3:
        return None
    return {"chapters": out_chapters}


def _format_visual_cues(visual_sims: Optional[list], n: int) -> str:
    """把相邻 chunk 的视觉相似度格式化成 LLM 可读的章节边界提示块。
    visual_sims[i] = chunk i 与 chunk i+1 的 CLIP cosine 相似度，长度 = n-1。
    None 元素表示该位置抽帧失败，跳过不喂。"""
    if not visual_sims or all(s is None for s in visual_sims):
        return ""
    lines = []
    for i, sim in enumerate(visual_sims):
        if sim is None:
            continue
        # 经验阈值：高 sim=同 slide / 同镜头延续；低 sim=切换信号
        if sim >= 0.85:
            tag = " (画面高度相似，无切换)"
        elif sim < 0.6:
            tag = " (画面显著切换，可能是章节切点)"
        else:
            tag = ""
        lines.append(f"  chunk {i} -> {i+1}: 视觉相似度 {sim:.2f}{tag}")
    if not lines:
        return ""
    return ("\n[相邻段视觉相似度 (CLIP, 1.0=同画面, 0.0=完全不同)]"
            "\n用作切分提示而非主信号——文本主题切换是主依据，视觉跳变只是 tie-breaker。\n"
            + "\n".join(lines) + "\n")


def _format_visual_captions(visual_captions: Optional[list[Optional[str]]], n: int) -> str:
    """把每个 chunk 的 VLM caption 格式化成 LLM 可读的画面描述块。
    visual_captions[i] = chunk i 的关键帧 1 句描述，长度 = n（与 chunks 对齐）。
    None 元素 = 抽帧或 caption 失败，跳过不显示。

    比 _format_visual_cues 的浮点 sim 信息密度高 10x：LLM 直接"读懂"画面讲什么，
    可结合文本主题做精准切分决策（PPT 标题变化 / 实拍场景切换 / 演示工具变化 等）。
    """
    if not visual_captions or all(c is None or not c for c in visual_captions):
        return ""
    lines = []
    for i, cap in enumerate(visual_captions):
        if not cap:
            continue
        lines.append(f"  chunk {i}: {cap}")
    if not lines:
        return ""
    return ("\n[每段关键帧画面描述 (VLM 生成)]"
            "\n用作切分参考——文本主题与画面描述一起判断；相邻段画面主题切换"
            "（PPT 标题变 / 镜头切实拍 / 演示工具变）通常对应章节边界。\n"
            + "\n".join(lines) + "\n")


def segment_hierarchical(chunks: list[dict],
                          headlines: Optional[list[str]] = None,
                          model_id: str = _DEFAULT_MODEL,
                          max_new_tokens: Optional[int] = None,
                          max_retries: int = 2,
                          visual_sims: Optional[list[float]] = None,
                          visual_captions: Optional[list[Optional[str]]] = None,
                          lang: str = "zh",
                          ) -> Optional[dict]:
    """对 chunks（按时间排好序）调 LLM 生成层级化章节大纲。
    成功返回 {"chapters": [{"title", "start", "end", "indices", "children"?}, ...]}
    所有 retry 失败返回 None（caller 应 fallback 到 flat chunker / TextTiling）。

    Retry 机制：首次失败时把具体错误（缺 chunk / catch-all / 超界）回灌给 LLM，让它
    在 multi-turn 上下文里自我修正。

    visual_sims (可选): 相邻 chunk 的 CLIP 视觉相似度列表（长度 n-1）。提供时
    inject 到 prompt 作为多模态切分提示——画面跳变 ≠ 章节切换的预设由 PPT 域
    "同节内翻 slide" 的特性决定，所以仅作 tie-breaker（注释在 prompt 中明示）。
    """
    if not chunks:
        return None
    n = len(chunks)
    if max_new_tokens is None:
        # 长视频章节多 + 英文 prompt 加严约束让 Qwen 输出更冗长（多行嵌套 JSON 每章
        # ~30-50 tokens）。30+ chunks 切 8-10 章时 1024 不够。给 max(1024, 80*n)。
        max_new_tokens = max(1024, 80 * n)
    chunk_text = _build_chunk_summary(chunks, headlines)
    # 视觉 cue 块：优先用 VLM captions（信息密度高），缺时退到浮点 sim
    if visual_captions and any(c for c in visual_captions):
        visual_block = _format_visual_captions(visual_captions, n)
    else:
        visual_block = _format_visual_cues(visual_sims, n)
    user_prompt = (
        f"教学视频共 {n} 个原子段（chunk_idx 0~{n-1}）：\n\n"
        f"{chunk_text}\n"
        f"{visual_block}\n"
        "请按要求输出层级化大纲 JSON。"
    )
    model, tok = load_model(model_id)
    base_messages = [
        {"role": "system", "content": _system_with_lang(SYSTEM_PROMPT, lang, "segment")},
        {"role": "user", "content": user_prompt},
    ]
    import torch
    last_raw: Optional[str] = None
    last_err: Optional[str] = None
    parsed: Optional[dict] = None
    ok = False
    # 元数据：供 pipeline 写入 ablation，论文附录 B 表用
    meta: dict = {
        "attempts_used": 0,        # 实际跑了几次 attempt（不算 repair）
        "pass_via": None,          # "attempt_1/2/3" or "repair"
        "repair_used": [],         # 实际执行的 repair 步骤
        "fail_reasons": [],        # 每次 attempt 失败原因（短）
    }
    for attempt in range(max_retries + 1):
        if attempt == 0:
            messages = base_messages
            temp = 0.15
        else:
            messages = base_messages + [
                {"role": "assistant", "content": last_raw or ""},
                {"role": "user", "content":
                    f"上次输出违反硬约束：{last_err}\n\n"
                    f"请**重新输出完整的 JSON**（不要 partial 不要 diff），严格遵守所有硬约束："
                    f"顶层数 ∈ [3,6]、单顶层 chunks ≤ 5、覆盖 0~{n-1} 全部 chunk_idx 无漏无重。"},
            ]
            # 重试温度更低更确定性
            temp = max(0.05, 0.15 - 0.05 * attempt)
        text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tok(text, return_tensors="pt").to(model.device)
        print(f"      [llm] attempt {attempt+1}/{max_retries+1} generate "
              f"(input {inputs['input_ids'].shape[1]} tokens, temp={temp}) ...", flush=True)
        with torch.no_grad():
            out = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=True,
                temperature=temp,
                top_p=0.85,
                pad_token_id=tok.eos_token_id,
            )
        gen_ids = out[0][inputs["input_ids"].shape[1]:]
        raw = tok.decode(gen_ids, skip_special_tokens=True).strip()
        print(f"      [llm] raw output ({len(raw)} chars): {raw[:160]}...", flush=True)
        last_raw = raw
        meta["attempts_used"] = attempt + 1
        parsed = _extract_json(raw)
        if parsed is None:
            last_err = "无法从输出中 parse 出有效 JSON 对象"
            meta["fail_reasons"].append("parse_fail")
            print(f"      [llm] attempt {attempt+1} failed: {last_err}", flush=True)
            continue
        # 后处理：把"过粗顶层（>5 chunks + 有 children）"的 children 提升为顶层
        before_promote_chs = [len(c.get("chunks") or []) for c in parsed.get("chapters", [])]
        parsed = _promote_oversized(parsed, max_chunks_per_top=5)
        after_promote_chs = [len(c.get("chunks") or []) for c in parsed.get("chapters", [])]
        if before_promote_chs != after_promote_chs and "promote_oversized" not in meta["repair_used"]:
            meta["repair_used"].append("promote_oversized")
        err = _diagnose_outline(parsed, n)
        if err is None:
            ok = True
            last_err = None
            meta["pass_via"] = f"attempt_{attempt+1}"
            print(f"      [llm] attempt {attempt+1} [OK] validation passed", flush=True)
            break
        last_err = err
        # 抓 err 的短类型（"oversize" / "missing" / "duplicate" / "too_few"）
        if "超过 5 个上限" in err:
            meta["fail_reasons"].append("oversize")
        elif "缺少 chunk_idx" in err:
            meta["fail_reasons"].append("missing")
        elif "出现在多个顶层" in err:
            meta["fail_reasons"].append("duplicate")
        elif "至少 3 个顶层" in err:
            meta["fail_reasons"].append("too_few_chapters")
        else:
            meta["fail_reasons"].append("other")
        print(f"      [llm] attempt {attempt+1} failed: {err}", flush=True)
    if not ok and parsed is not None:
        # 最后一次努力：程序化修复
        # Step 1：把漏的 chunk 并入时间最近顶层（_repair_missing_chunks）
        # Step 2：把 catch-all 顶层（>5 chunks 无 children）按 keyword Jaccard
        #         距离拆成 ≤5 子段（_repair_oversize）—— 救 Qwen 在长英文视频
        #         上的 catch-all bias
        repaired = _repair_missing_chunks(parsed, n)
        if repaired is not None:
            meta["repair_used"].append("repair_missing")
            repaired = _promote_oversized(repaired, max_chunks_per_top=5)
            before_oversize_chs = [len(c.get("chunks") or []) for c in repaired.get("chapters", [])]
            repaired = _repair_oversize(repaired, chunks, max_chunks_per_top=5)
            after_oversize_chs = [len(c.get("chunks") or []) for c in repaired.get("chapters", [])]
            if before_oversize_chs != after_oversize_chs:
                meta["repair_used"].append("repair_oversize")
            err = _diagnose_outline(repaired, n)
            if err is None:
                parsed = repaired
                ok = True
                meta["pass_via"] = "repair"
                print(f"      [llm] programmatic repair [OK]", flush=True)
            else:
                print(f"      [llm] repair attempted but still invalid: {err}", flush=True)
    if not ok or parsed is None:
        print(f"      [llm] all {max_retries+1} attempts + repair failed (last: {last_err})",
              flush=True)
        # 返回 _meta 让 caller 写到 ablation 里（虽然没出 chapters），便于事后
        # 在论文附录 B 表里准确显示 "LLM 跑了 N 次 attempt 失败 → fallback"
        return {"chapters": [], "_meta": meta}
    outline = _validate_outline(parsed, n)
    if outline is None:
        # 理论上 _diagnose 通过了 _validate 也该通过，兜底
        print(f"      [llm] outline validation failed after diagnose passed (bug?)", flush=True)
        return {"chapters": [], "_meta": meta}

    # B1: 二次调 LLM，按"只看本章 headlines"重写章标题，避开邻章串台问题
    refined_titles = refine_chapter_titles(outline, chunks, lang=lang)
    if refined_titles and len(refined_titles) == len(outline["chapters"]):
        for ch, new_title in zip(outline["chapters"], refined_titles):
            ch["title_v1"] = ch["title"]  # 留底，便于对照
            ch["title"] = new_title

    # 把 chunk_idx 转 start/end 时间戳
    for ch in outline["chapters"]:
        ch["indices"] = ch["chunks"]
        ch["start"] = chunks[ch["chunks"][0]]["start"]
        ch["end"] = chunks[ch["chunks"][-1]]["end"]
        for sub in ch.get("children", []):
            sub["indices"] = sub["chunks"]
            sub["start"] = chunks[sub["chunks"][0]]["start"]
            sub["end"] = chunks[sub["chunks"][-1]]["end"]
    outline["_meta"] = meta
    return outline


TITLE_CHAPTER_SYSTEM = """你是教学视频章节命名助手。给定若干章节，每章含若干\
连续段标题，为每章生成一个 6-14 字（中文）或 3-7 词（英文）的章标题。

**⚠️ 输出语言匹配输入**：段标题是英文则章标题用英文（如 "AI Agent Tooling"），\
段标题是中文则章标题用中文（如 "管程引入与基本特征"）。**不要翻译**。

约束：
1. **标题关键词必须在本章段标题里出现过**——绝对不要借用其他章的关键词
2. 名词短语，不带动词 / 疑问 / 句末标点
3. **强制并列检查**：若本章有 ≥2 个 chunks，检查段标题是否包含 ≥2 个并列子主题
   （如"定常子网划分" + "变长子网划分"，"直通交换" + "存储转发"）。命中并列时
   **标题必须用 "X 与 Y" / "X 和 Y" 包含全部并列主题，不允许只挑一个写**。
4. 单段成章时，标题可与该段标题相近但略上升抽象层

## 反例（不允许）

输入：[第 1 章: 段标题包括"直通交换方式"、"存储转发交换"]
错误输出："直通交换" ✗（漏存储转发）
正确输出："直通与存储转发" ✓

输入：[第 1 章: 段标题包括"定常子网划分原理"、"变长子网划分实例"、"IP地址资源分配"]
错误输出："变长子网划分与IP资源" ✗（漏定常子网划分）
正确输出："定常与变长子网划分" ✓（次主题 IP 资源进 abstract，不进标题）

## 输出格式（必须严格遵守）

**整个输出是 ONE JSON 数组**，长度等于输入章数。**不要**分成多个 `[...]` 数组。

示例（输入 3 章）：
输入：
[第 1 章]
  - 进程概念
  - 线程引入
[第 2 章]
  - 信号量定义
  - PV 操作
[第 3 章]
  - 死锁条件

输出：
["进程与线程基础", "信号量与PV操作", "死锁产生条件"]

注意：**所有标题在一个数组里**，逗号分隔，**不要**输出多个 `[...]`。"""


def refine_chapter_titles(outline: dict, chunks: list[dict],
                          model_id: str = _DEFAULT_MODEL,
                          max_new_tokens: int = 400,
                          lang: str = "zh") -> Optional[list[str]]:
    """二次调 LLM，仅基于每章内部 chunks 的 headlines 命名章标题。
    避开"一次切+命名"时邻章 headline 串台。成功返回与顶层等长的标题列表。"""
    chapters = outline.get("chapters", [])
    if not chapters:
        return None
    K = len(chapters)
    lines = []
    for ci, ch in enumerate(chapters):
        lines.append(f"[第 {ci+1} 章]")
        for idx in ch["chunks"]:
            hl = chunks[idx].get("headline") or chunks[idx].get("text", "")[:30]
            lines.append(f"  - {hl}")
    body = "\n".join(lines)
    user_prompt = (f"共 {K} 章，请按顺序为每章生成标题：\n\n{body}\n\n"
                   f"输出 JSON 数组（必须 {K} 个元素）：")
    model, tok = load_model(model_id)
    messages = [
        {"role": "system", "content": _system_with_lang(TITLE_CHAPTER_SYSTEM, lang, "title")},
        {"role": "user", "content": user_prompt},
    ]
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    import torch
    inputs = tok(text, return_tensors="pt").to(model.device)
    print(f"      [llm-chapter-title] generate for {K} chapters "
          f"(input {inputs['input_ids'].shape[1]} tokens) ...", flush=True)
    with torch.no_grad():
        out = model.generate(
            **inputs, max_new_tokens=max_new_tokens, do_sample=True,
            temperature=0.15, top_p=0.85, pad_token_id=tok.eos_token_id,
        )
    gen_ids = out[0][inputs["input_ids"].shape[1]:]
    raw = tok.decode(gen_ids, skip_special_tokens=True).strip()
    arr = _parse_titles_array(raw, K)
    if arr is None:
        print(f"      [llm-chapter-title] parse failed, raw: {raw[:250]}", flush=True)
        return None
    titles = [str(s).strip().strip('"').strip("'") for s in arr]
    print(f"      [llm-chapter-title] refined {K} chapter titles", flush=True)
    return titles


def _parse_titles_array(raw: str, K: int) -> Optional[list]:
    """容忍 LLM 的多种输出格式：
    1. 标准单个 JSON 数组 `["a", "b", "c"]`
    2. fenced code block `​```json\n[...]```​`
    3. 多个独立小数组连写 `["a"]\n["b"]\n["c"]` — 拍平合并
    """
    # 1. fenced code
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.DOTALL)
    if m:
        try:
            arr = json.loads(m.group(1))
            if isinstance(arr, list) and len(arr) == K:
                return arr
        except json.JSONDecodeError:
            pass
    # 2. first [ to last ] (standard greedy)
    l, r = raw.find("["), raw.rfind("]")
    if l >= 0 and r > l:
        try:
            arr = json.loads(raw[l:r + 1])
            if isinstance(arr, list) and len(arr) == K:
                return arr
        except json.JSONDecodeError:
            pass
    # 3a. 多候选数组：Qwen 偶尔输出 N 个完整 K-元素数组（"alternatives"），
    #     取第一个 — temp=0.15 时第一个最稳。p42 实测 PPP 三选一。
    # 3b. 否则拍平所有小数组（K 个 1-元素数组的退化情况）
    pieces = []
    for m in re.finditer(r"\[[^\[\]]*\]", raw):
        try:
            piece = json.loads(m.group(0))
            if isinstance(piece, list):
                pieces.append(piece)
        except json.JSONDecodeError:
            continue
    for p in pieces:
        if len(p) == K:
            return p
    flat = [x for p in pieces for x in p]
    if len(flat) == K:
        return flat
    # 4. 救命兜底：抓所有 `"..."` 双引号字符串，凑 K 个就接受
    # 触发场景：英文长 list（34 chunks）max_new_tokens 不够时 JSON 数组未闭合
    # （末尾停在 "Agent Bui...` 不收 `]`），上面 3 级都失败。此时已生成的 quoted
    # strings 大多数是合法 headline，宁可少 1-2 个用空串补也好过整批丢。
    quoted = re.findall(r'"([^"\n]+)"', raw)
    # 过滤明显 boilerplate：JSON 字段名 / markdown fence / 短于 2 字符
    quoted = [q for q in quoted if len(q) >= 2 and q not in
              {"title", "chunks", "chapters", "headline", "abstract", "json"}]
    if len(quoted) >= K:
        return quoted[:K]
    if len(quoted) >= max(2, K // 2):
        # 截断 case：用空串补齐到 K，caller 应单独标 [llm-fallback-truncated]
        return quoted + [""] * (K - len(quoted))
    return None


ASR_FIX_SYSTEM = """你是教学视频 ASR 转写错字校对助手。给定若干段视频文本（每段含\
关键词和原文），找出明显的**同音字 / 字形错误**并输出修正字典。

**⚠️ 输入可能是英文文本**——英文 ASR 也会有错字（如 "Claude→Cloud"），同样需要修正。
英文文本中的 fixes 用英文 wrong/right 对。

## 教学视频常见错字示例

- 计网域："双脚线"→"双绞线"、"真的结束字段"→"帧的结束字段"、"数据针"→"数据帧"、\
  "中端节点"→"终端节点"、"双角线"→"双绞线"
- **计网域陷阱：合法常用词被当 ASR 错字**：
  - "手部" → "首部"（IP 数据报/帧 的"首部"被听成"手部"——"手部"虽然在通用语境
    是合法人体部位词，但在计网视频里 100% 是 "首部" 的 ASR 错字）
  - "潜坠" → "前缀"（"网络前缀"被识成"网络潜坠"——"潜坠"几乎不是常用词）
- 操作系统域："呼吃信号量"→"互斥信号量"、"信号亮"→"信号量"、"PV 操作"→"PV操作"、
  "广程"→"管程"（OS 王道 p38 实测：whisper 把"管"听成"广"，35/501 段中招——
  "广程"在中文几乎不是常用词；同样"管成"也是"管程"错字）
- 通用："主绘画"→"主会话"（编程类）、"刘谦的我的世界"→"刘谦的《我的世界》"

## 判定要求

1. **必须根据关键词反映的本段域来判定**——关键词"网络/帧/MAC"，段内"双脚线"\
   高概率是"双绞线"误识
2. **特别注意"合法常用词陷阱"**：某些 ASR 错字本身是通用语境合法词（如"手部"、
   "潜坠"），但在特定域里几乎不会以本义出现。当关键词强烈指向某个域（如"IP 数据报/
   首部/字段"指向计网），而段内出现这类"看似合法但语义不通"的词时，应该改正。
3. **保留原意，不改写句子结构**——只替换错字 token
4. **宁可漏改不要乱改**——证据不足时不改
5. **不修正正确的字、人名、专有名词**
6. **不修正英文 / 数字 / 标点符号**（不要把"．"改成"？"这种纯标点修正）
7. **wrong 和 right 必须长度相近（差异 ≤ 2 字符）**——长度差大的是改写而非校字
8. **必须是中文字符级别的替换**——若 wrong 和 right 仅在标点上不同，跳过

## 输出格式

严格输出 JSON 数组，每段一对象（按 chunk 顺序），格式：
```json
[
  {"idx": 0, "fixes": [{"wrong": "双脚线", "right": "双绞线"}]},
  {"idx": 1, "fixes": []},
  ...
]
```

无错字的段 fixes=[]。**整个输出是 ONE JSON 数组**，不要分多段。不要 markdown / 解释。"""


def qwen_asr_fix(chunks: list[dict],
                 model_id: str = _DEFAULT_MODEL,
                 max_new_tokens: int = 600) -> dict[str, str]:
    """让 Qwen 基于 chunk-level 上下文找 ASR 同音字 / 字形错字。
    返回扁平 {wrong: right} 字典，可直接喂 `apply_term_corrections`。
    LLM 失败 / 无错字时返回空字典——caller 不需要特别处理。

    Why chunk-level：Qwen 看 800 字 chunk + 关键词上下文比 ASR 单 segment（< 50 字）
    视野大得多，能识别"双脚线"在网络域的隐式错字（substring map 救不了的 case，
    memory #21 标记的盲区）。
    """
    if not chunks:
        return {}
    n = len(chunks)
    lines = []
    for i, c in enumerate(chunks):
        kws = c.get("keywords") or []
        text = (c.get("text") or "").replace("\n", " ").strip()[:400]  # 400c chunk-level 上下文
        lines.append(f"[Chunk {i:02d}]")
        if kws:
            lines.append(f"  关键词: {', '.join(kws[:6])}")
        if text:
            lines.append(f"  原文: {text}")
    user_prompt = (f"共 {n} 段，请扫描每段找 ASR 错字（无错字段 fixes=[]）：\n\n" +
                   "\n".join(lines) +
                   f"\n\n输出 JSON 数组（必须 {n} 个对象，每个含 idx + fixes）：")
    model, tok = load_model(model_id)
    messages = [
        {"role": "system", "content": ASR_FIX_SYSTEM},
        {"role": "user", "content": user_prompt},
    ]
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    import torch
    inputs = tok(text, return_tensors="pt").to(model.device)
    print(f"      [llm-asr-fix] scan {n} chunks "
          f"(input {inputs['input_ids'].shape[1]} tokens) ...", flush=True)
    with torch.no_grad():
        out = model.generate(
            **inputs, max_new_tokens=max_new_tokens, do_sample=True,
            temperature=0.1, top_p=0.85, pad_token_id=tok.eos_token_id,
        )
    gen_ids = out[0][inputs["input_ids"].shape[1]:]
    raw = tok.decode(gen_ids, skip_special_tokens=True).strip()
    arr = _parse_asr_fix_array(raw)
    if not arr:
        print(f"      [llm-asr-fix] parse failed or empty, raw: {raw[:200]}", flush=True)
        return {}
    # Build full text corpus for hallucination filter（Qwen 编出 chunk 里不存在的
    # wrong 串时，apply_term_corrections 会 no-op，但更早过滤更清爽）
    full_text = " ".join((c.get("text") or "") for c in chunks)
    all_fixes: dict[str, str] = {}
    skipped = 0
    for entry in arr:
        if not isinstance(entry, dict):
            continue
        fixes = entry.get("fixes", [])
        if not isinstance(fixes, list):
            continue
        for f in fixes:
            if not isinstance(f, dict):
                continue
            w = (f.get("wrong") or "").strip()
            r_ = (f.get("right") or "").strip()
            if not (w and r_ and w != r_):
                continue
            if len(w) < 2:  # 短词易误伤合法子串
                skipped += 1
                continue
            # 长度变化 > 50% 极不可能是同音字（更像 hallucinate）
            short, long_ = min(len(w), len(r_)), max(len(w), len(r_))
            if long_ - short > short:
                skipped += 1
                continue
            # 去标点 / 空白后等价 → 纯标点修正，跳过（不是 ASR 错字校对的工作）
            _strip = lambda s: re.sub(r"[\s。．，,、？?！!；;：:\"\"''""()（）\[\]【】《》<>]", "", s)
            if _strip(w) == _strip(r_):
                skipped += 1
                continue
            # 防级联重复：wrong 是 right 的子串时（如 "全双"→"全双工"），第一遍替换
            # 会把 "全双工"（已正确的）继续匹配到 wrong "全双"，造成 "全双工工"。
            # 这类"短补全长"修正必须拒绝。
            if w in r_:
                skipped += 1
                continue
            # wrong 必须实际出现在某 chunk 里（不能 Qwen 凭空编）
            if w not in full_text:
                skipped += 1
                continue
            # 同一 wrong 取首次见的 right
            if w not in all_fixes:
                all_fixes[w] = r_
    if all_fixes:
        sample = list(all_fixes.items())[:3]
        print(f"      [llm-asr-fix] found {len(all_fixes)} corrections "
              f"(skipped {skipped} 误判): "
              f"{sample}{'...' if len(all_fixes) > 3 else ''}", flush=True)
    else:
        print(f"      [llm-asr-fix] no corrections needed "
              f"(skipped {skipped} 误判)", flush=True)
    return all_fixes


def _parse_asr_fix_array(raw: str) -> list:
    """容忍 LLM 输出的几种 ASR fix JSON 格式：
    1. 标准 `[{...}, {...}]`
    2. fenced code block 包裹的标准格式
    3. **缺外层 [...]** 的直连对象 `{...},\n{...},...`（Qwen 7B 偶发）
    """
    # 1. fenced
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.DOTALL)
    if m:
        try:
            arr = json.loads(m.group(1))
            if isinstance(arr, list):
                return arr
        except json.JSONDecodeError:
            pass
    # 2. first [ to last ]
    l, r = raw.find("["), raw.rfind("]")
    if l >= 0 and r > l:
        try:
            arr = json.loads(raw[l:r + 1])
            if isinstance(arr, list):
                return arr
        except json.JSONDecodeError:
            pass
    # 3. 缺外层数组：抓所有 top-level `{"idx": ..., "fixes": [...]}` 块拼起来
    # 注意 fixes 内部含嵌套对象，需要 balanced 匹配
    objs = []
    depth = 0
    start = -1
    for i, ch in enumerate(raw):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    o = json.loads(raw[start:i + 1])
                    if isinstance(o, dict) and "fixes" in o:
                        objs.append(o)
                except json.JSONDecodeError:
                    pass
                start = -1
    return objs


CHAPTER_ABSTRACT_SYSTEM = """你是教学视频章节概述助手。给定若干章节（每章含若干段标题），\
为每章生成 1-2 句话的章节概述。

**⚠️ 输出语言匹配输入**：段标题/章标题是英文则 abstract 用英文（"This chapter \
introduces..."），中文则用中文（"本章介绍..."）。**不要翻译**——保持原语言一致。

要求：
1. 每章输出 30-100 字（中文）或 15-50 词（英文）的陈述句 prose 概述
2. 用陈述句概括"本章讲了什么 + 重点"
3. **不要**列举式 "本章涵盖 X、Y、Z"，要 prose 风格的连贯句子
4. **必须包含本章 1-2 个具体技术点**（字段/概念/规则/算法名），不允许只写
   "本章详细介绍 X 的相关内容" 这种空泛表述
5. 概述里出现的关键词必须从本章段标题里抽，**不要借邻章关键词**
6. **并列主题必须全部点到**：若本章包含 2 个或以上并列子主题（如"直通交换"+
   "存储转发"，"定常子网"+"变长子网"），abstract 必须显式提到全部并列项
7. 单段成章时，可在该段标题基础上展开成 1 句话
8. **严格输出 K 个 abstract**（K = 章数）：每章对应一个 abstract，**不可合并**
   两章为一句，**不可省略**任何章。即使两章主题相邻，也必须各出一个 abstract。
9. 严格输出 JSON 数组，长度 = 章数，元素为字符串

## 反例（不允许）

段标题: ["PPP协议格式", "PPP帧结构", "字节填充"]
错误: "本章详细解析PPP协议的工作原理及其组成部分。" ✗（无具体技术点）
正确: "本章介绍PPP协议的帧格式与字段含义，重点讲解字节填充法实现透明传输的机制。" ✓

段标题: ["直通交换方式", "存储转发交换"]
错误: "本章介绍直通交换的工作方式。" ✗（漏存储转发）
正确: "本章对比直通交换与存储转发两种方式，指出前者延迟低但不做差错检测，后者反之。" ✓

## 输出格式（必须严格遵守）

**整个输出是 ONE JSON 数组**，**不要**分成多个 `[...]` 数组。

示例（输入 2 章）：
输入：
[第 1 章: 死锁概念]
  - 死锁定义
  - 死锁产生的四个必要条件
[第 2 章: 死锁处理策略]
  - 预防、避免、检测、解除
  - 银行家算法

输出：
["本章介绍死锁的基本定义，并讲解产生死锁所必需的四个条件——互斥、占有等待、不剥夺、循环等待。", "本章对比四种死锁处理策略——预防、避免、检测、解除——并深入分析银行家算法的工作机制。"]

不要 markdown / 解释 / 前言。"""


def generate_chapter_abstracts(chapters: list[dict],
                               model_id: str = _DEFAULT_MODEL,
                               max_new_tokens: Optional[int] = None,
                               lang: str = "zh") -> Optional[list[str]]:
    """批量生成章节级 abstractive 概述（1-2 句 prose）。
    chapters 需含 chunks 列表（每个 chunk 含 headline）。
    成功返回与 chapters 等长字符串列表；失败返回 None（caller 应 fallback summarize_chapter）。

    max_new_tokens 默认按 K 动态算（每 abstract ~150 tokens），防多章 K>=6 截断。"""
    if not chapters:
        return None
    K = len(chapters)
    if max_new_tokens is None:
        max_new_tokens = max(600, 180 * K)
    lines = []
    for ci, ch in enumerate(chapters):
        title = ch.get("title", "")
        lines.append(f"[第 {ci+1} 章" + (f": {title}" if title else "") + "]")
        for sub_c in ch.get("chunks", []):
            hl = (sub_c.get("headline") or "").strip()
            if hl:
                lines.append(f"  - {hl}")
    body = "\n".join(lines)
    user_prompt = (f"共 {K} 章，请按顺序为每章生成 1-2 句章节概述：\n\n{body}\n\n"
                   f"输出 JSON 数组（必须 {K} 个元素）：")
    model, tok = load_model(model_id)
    messages = [
        {"role": "system", "content": _system_with_lang(CHAPTER_ABSTRACT_SYSTEM, lang, "abstract")},
        {"role": "user", "content": user_prompt},
    ]
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    import torch
    inputs = tok(text, return_tensors="pt").to(model.device)
    print(f"      [llm-chapter-abstract] generate for {K} chapters "
          f"(input {inputs['input_ids'].shape[1]} tokens) ...", flush=True)
    with torch.no_grad():
        out = model.generate(
            **inputs, max_new_tokens=max_new_tokens, do_sample=True,
            temperature=0.2, top_p=0.9, pad_token_id=tok.eos_token_id,
        )
    gen_ids = out[0][inputs["input_ids"].shape[1]:]
    raw = tok.decode(gen_ids, skip_special_tokens=True).strip()
    arr = _parse_titles_array(raw, K)
    if arr is None:
        print(f"      [llm-chapter-abstract] parse failed, raw: {raw[:250]}", flush=True)
        return None
    abstracts = [str(s).strip().strip('"').strip("'") for s in arr]
    print(f"      [llm-chapter-abstract] generated {K} chapter abstracts", flush=True)
    return abstracts


GENERATE_HEADLINES_SYSTEM = """你是教学视频笔记的标题生成助手。给定若干段视频内容\
（每段有原文摘录），为每段生成简洁的小标题。

**⚠️ 输出语言匹配输入**：chunk 原文是英文则 headline 用英文（如 "RAG Integration"），\
chunk 原文是中文则 headline 用中文（如 "管程引入原因"）。**不要翻译**——保持\
原语言一致。

要求：
1. 每段输出 6-15 字（中文）或 3-8 词（英文）名词短语标题
2. 反映该段实际教学内容（基于原文判定）
3. 去掉口语词（中文："我们/是/了/那/这个/接下来/然后" / 英文："we/the/are/so/now"）
4. 修正 ASR 同音字错误（如"双脚线"→"双绞线"、"真的结束"→"帧的结束字段"等）
5. 不带句末标点（不要 ? ! 。等）
6. 严格输出 JSON 数组，**长度必须等于输入段数**，按顺序对应
7. 不要任何 markdown 标记、解释或前言"""


def generate_headlines(chunks: list[dict],
                      model_id: str = _DEFAULT_MODEL,
                      max_new_tokens: Optional[int] = None,
                      lang: str = "zh") -> Optional[list[str]]:
    """直接从 chunk 原文生成 headline（无 Pegasus 初版作输入）。
    用于 `--llm-chapters` 模式跳过 Pegasus 后的 headline 来源。
    成功返回与 chunks 等长的字符串列表；失败返回 None。

    max_new_tokens 默认按 chunks 数量动态算（每 headline ~50 tokens + 安全余量），
    防英文 Claude 27 chunks 那种长视频被 800 上限截断。"""
    if not chunks:
        return None
    n = len(chunks)
    if max_new_tokens is None:
        # 英文 headline 比中文 token 更多（每个英文词 ~1.5 BPE token vs 每个汉字 1 token），
        # 加 quotes/comma/newline，整 list 容易超 60*n 上限。给 100*n 保守余量。
        max_new_tokens = max(1200, 100 * n)
    lines = []
    for i, c in enumerate(chunks):
        full = (c.get("text") or "").replace("\n", " ").strip()
        # 首段 + 中段各取一截，覆盖 chunk 内可能的主题漂移（chunk 头是过渡内容、
        # 真正主题在中段的常见 pattern——p38 chunk 10 头讲双绞线、中后段讲物理层标准）
        head = full[:200]
        mid = full[len(full)//2:len(full)//2 + 150] if len(full) > 350 else ""
        kws = c.get("keywords") or []
        lines.append(f"[Chunk {i:02d}]")
        if kws:
            lines.append(f"  关键词: {', '.join(kws[:6])}")  # jieba top-6 锚主题
        if head:
            lines.append(f"  开头: {head}")
        if mid:
            lines.append(f"  中段: {mid}")
    user_prompt = (
        f"共 {n} 段，请按顺序为每段生成 {n} 个标题：\n\n" +
        "\n".join(lines) +
        f"\n\n输出 JSON 数组（必须 {n} 个元素）。"
        f"\n注意：关键词反映该段实际涵盖的主要概念，标题应跟关键词主题一致；"
        f"如果开头描述跟关键词差异大，说明开头是上段过渡内容，应以关键词为准。"
    )
    model, tok = load_model(model_id)
    messages = [
        {"role": "system", "content": _system_with_lang(GENERATE_HEADLINES_SYSTEM, lang, "headlines")},
        {"role": "user", "content": user_prompt},
    ]
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    import torch
    inputs = tok(text, return_tensors="pt").to(model.device)
    print(f"      [llm-headline-gen] generate for {n} chunks "
          f"(input {inputs['input_ids'].shape[1]} tokens) ...", flush=True)
    with torch.no_grad():
        out = model.generate(
            **inputs, max_new_tokens=max_new_tokens, do_sample=True,
            temperature=0.15, top_p=0.85, pad_token_id=tok.eos_token_id,
        )
    gen_ids = out[0][inputs["input_ids"].shape[1]:]
    raw = tok.decode(gen_ids, skip_special_tokens=True).strip()
    arr = _parse_titles_array(raw, n)
    if arr is None:
        print(f"      [llm-headline-gen] parse failed, raw len={len(raw)}, "
              f"head: {raw[:200]} ... tail: {raw[-100:]}", flush=True)
        return None
    titles = [str(s).strip().strip('"').strip("'") for s in arr]
    n_truncated = sum(1 for t in titles if not t)
    if n_truncated:
        print(f"      [llm-headline-gen] generated {n - n_truncated}/{n} headlines "
              f"({n_truncated} blank from truncation fallback)", flush=True)
    else:
        print(f"      [llm-headline-gen] generated {n} headlines from scratch", flush=True)
    return titles


REFINE_HEADLINES_SYSTEM = """你是教学视频笔记的标题清理助手。下面是若干段视频\
内容（每段有初版标题 + 原文摘录），初版标题由小模型自动生成，常有错别字/不通顺/\
含口语词，需要你重写。

要求：
1. **每段输出 6-15 字名词短语** 标题
2. 反映该段实际教学内容（基于原文判定，不要照搬初版）
3. 去掉口语词（"我们"、"是"、"了"、"那"、"这个"、"接下来"、"然后"等）
4. 去掉句末问号、感叹号、句号
5. 修正错别字（ASR 同音误识，如"双脚线"→"双绞线"、"真的结束"→"帧的结束字段"等）
6. **如果一段实际涵盖两个并列主题，标题用"X 与 Y"格式覆盖**
   （示例：原段讲冲突域 + 广播域 → "冲突域与广播域的隔离"）
7. 严格输出 JSON 数组，元素为字符串，**数量必须等于输入段数**，按顺序对应
8. 不要任何 markdown 标记、解释或前言"""


def refine_headlines(chunks: list[dict],
                     model_id: str = _DEFAULT_MODEL,
                     max_new_tokens: int = 800,
                     lang: str = "zh") -> Optional[list[str]]:
    """让 Qwen 基于 chunk text + Pegasus 初版 headline 重写每段标题。
    成功返回与 chunks 等长的字符串列表；失败返回 None（caller 保留原 headline）。"""
    if not chunks:
        return None
    n = len(chunks)
    lines = []
    for i, c in enumerate(chunks):
        hl = c.get("headline") or ""
        # 取首 150 字够 LLM 理解教学内容
        excerpt = (c.get("text") or "").replace("\n", " ").strip()[:150]
        lines.append(f"[Chunk {i:02d}] 初版标题: {hl}")
        if excerpt:
            lines.append(f"  原文: {excerpt}")
    user_prompt = (
        f"共 {n} 段，请按顺序输出 {n} 个重写后的标题：\n\n" +
        "\n".join(lines) +
        f"\n\n请输出 JSON 数组（必须 {n} 个元素）："
    )
    model, tok = load_model(model_id)
    messages = [
        {"role": "system", "content": _system_with_lang(REFINE_HEADLINES_SYSTEM, lang, "refine_headlines")},
        {"role": "user", "content": user_prompt},
    ]
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    import torch
    inputs = tok(text, return_tensors="pt").to(model.device)
    print(f"      [llm-headline] generate for {n} chunks "
          f"(input {inputs['input_ids'].shape[1]} tokens) ...", flush=True)
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=0.15,
            top_p=0.85,
            pad_token_id=tok.eos_token_id,
        )
    gen_ids = out[0][inputs["input_ids"].shape[1]:]
    raw = tok.decode(gen_ids, skip_special_tokens=True).strip()
    # 抽出 JSON 数组
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.DOTALL)
    if m:
        arr_text = m.group(1)
    else:
        l = raw.find("[")
        r = raw.rfind("]")
        if l < 0 or r <= l:
            print(f"      [llm-headline] JSON array not found: {raw[:200]}", flush=True)
            return None
        arr_text = raw[l:r + 1]
    try:
        arr = json.loads(arr_text)
    except json.JSONDecodeError as e:
        print(f"      [llm-headline] JSON parse failed: {e}, raw: {raw[:200]}", flush=True)
        return None
    if not isinstance(arr, list) or len(arr) != n:
        print(f"      [llm-headline] expected {n} headlines, got {len(arr) if isinstance(arr, list) else type(arr).__name__}",
              flush=True)
        return None
    cleaned = [str(s).strip().strip('"').strip("'") for s in arr]
    print(f"      [llm-headline] refined {n} headlines", flush=True)
    return cleaned


TRANSLATE_SYSTEM_ZH2EN = """You are a translator for educational video notes.
Translate Chinese chapter titles / abstracts / headlines to **natural fluent English**
suitable for a teaching context.

Rules:
1. Keep technical terms accurate (e.g. 双绞线 → twisted pair, 管程 → monitor (concurrency), \
信号量 → semaphore, MAC 帧 → MAC frame, 时分多路复用 → time-division multiplexing)
2. Keep titles concise (3-7 word noun phrases, no trailing punctuation)
3. Keep abstracts as 1-2 fluent English sentences (15-50 words), starting with
   "This chapter ..." / "This section ..."
4. Output a single JSON array of strings, exactly matching the input array length
5. No markdown, no commentary, no preamble"""


TRANSLATE_SYSTEM_EN2ZH = """你是教学视频笔记翻译助手。把英文章标题 / 章概述 / 段标题\
翻译成**自然流畅的中文**，适合教学场景。

要求：
1. 技术术语准确（如 twisted pair → 双绞线、monitor → 管程、semaphore → 信号量、\
MAC frame → MAC 帧、cut-through → 直通交换、HTTP request → HTTP 请求）
2. 标题简洁（6-14 字名词短语，不带句末标点）
3. 概述用 1-2 句中文 prose（30-100 字），以 "本章..." / "本节..." 开头
4. 输出严格单个 JSON 数组，长度与输入数组相等
5. 不要 markdown / 解释 / 前言"""


def translate_bilingual(items: list[str], src_lang: str, tgt_lang: str,
                         model_id: str = _DEFAULT_MODEL,
                         max_new_tokens: Optional[int] = None,
                         ) -> Optional[list[str]]:
    """批量把 items (list of strings) 从 src_lang 翻译到 tgt_lang。
    成功返回与输入等长的字符串 list；失败返回 None。

    支持 src='zh', tgt='en' 或 src='en', tgt='zh'。
    其它语言对暂未支持（返回 None）。

    Used by pipeline 在 chapters/headlines 生成后补一次双语字段，前端 toggle
    切换显示。max_new_tokens 默认按 items 数量动态算（每条 ~200 tokens）。
    """
    if not items:
        return None
    n = len(items)
    if max_new_tokens is None:
        max_new_tokens = max(800, 200 * n)
    if src_lang == "zh" and tgt_lang == "en":
        system = TRANSLATE_SYSTEM_ZH2EN
    elif src_lang == "en" and tgt_lang == "zh":
        system = TRANSLATE_SYSTEM_EN2ZH
    else:
        print(f"      [translate] unsupported pair {src_lang}->{tgt_lang}", flush=True)
        return None
    user_prompt = (f"Translate the following {n} strings. "
                   f"Output a JSON array of exactly {n} strings:\n\n"
                   + json.dumps(items, ensure_ascii=False, indent=2))
    model, tok = load_model(model_id)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_prompt},
    ]
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    import torch
    inputs = tok(text, return_tensors="pt").to(model.device)
    print(f"      [translate] {src_lang}->{tgt_lang} {n} items "
          f"(input {inputs['input_ids'].shape[1]} tokens) ...", flush=True)
    with torch.no_grad():
        out = model.generate(
            **inputs, max_new_tokens=max_new_tokens, do_sample=True,
            temperature=0.1, top_p=0.9, pad_token_id=tok.eos_token_id,
        )
    gen_ids = out[0][inputs["input_ids"].shape[1]:]
    raw = tok.decode(gen_ids, skip_special_tokens=True).strip()
    arr = _parse_titles_array(raw, n)
    if arr is None:
        print(f"      [translate] parse failed, raw len={len(raw)}, "
              f"head: {raw[:200]}", flush=True)
        return None
    out_strs = [str(s).strip().strip('"').strip("'") for s in arr]
    n_filled = sum(1 for s in out_strs if s)
    print(f"      [translate] got {n_filled}/{n} translations", flush=True)
    return out_strs


if __name__ == "__main__":
    # 独立 smoke test：跑现有 cached chunks
    import sys
    from pathlib import Path
    if len(sys.argv) < 2:
        print("usage: python segment_llm.py <chapters.json | summary.json>")
        sys.exit(1)
    src = Path(sys.argv[1])
    data = json.loads(src.read_text(encoding="utf-8"))
    # 接受 summary.json (chunk list) 或 chapters.json (with chunks list)
    if isinstance(data, list):
        chunks = data
    elif "chapters" in data and isinstance(data["chapters"], list) and data["chapters"]:
        # 这是输出 chapters.json，不是输入 chunks，用法错误
        print("[ERR] please pass summary.json (chunk list), not chapters.json")
        sys.exit(1)
    else:
        chunks = data.get("chunks", [])
    if not chunks:
        print("[ERR] no chunks found")
        sys.exit(1)
    print(f"loaded {len(chunks)} chunks from {src}")
    result = segment_hierarchical(chunks)
    if result is None:
        print("[ERR] segmentation failed")
        sys.exit(2)
    print("\n=== outline ===")
    for ch in result["chapters"]:
        print(f"\n■ {ch['title']}  [{_format_time(ch['start'])}-{_format_time(ch['end'])}]  chunks {ch['indices']}")
        for sub in ch.get("children", []):
            print(f"  └ {sub['title']}  [{_format_time(sub['start'])}-{_format_time(sub['end'])}]  chunks {sub['indices']}")
