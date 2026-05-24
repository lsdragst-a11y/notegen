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

import jieba
jieba.setLogLevel(60)  # 静音 jieba 启动 INFO 日志，pipeline 输出已经够吵


def _apply_autoawq_shim():
    """autoawq 0.2.6 跟 transformers 4.49+ import 链兼容修复。
    模块级运行，让任何 import segment_llm 的下游（含 caption_vl）共享 shim。
    幂等。"""
    import sys as _sys
    import types as _types
    import os as _os
    # Windows: autoawq_kernels .pyd 不在默认 DLL 搜索路径，注入 torch lib 目录
    # 让 cudart64_12 / cublas64_12 等可被 awq_ext.pyd 解析
    if hasattr(_os, "add_dll_directory"):
        try:
            import torch as _t
            _t_lib = _os.path.join(_os.path.dirname(_t.__file__), "lib")
            if _os.path.isdir(_t_lib):
                _os.add_dll_directory(_t_lib)
        except Exception:
            pass
    # datasets stub：awq.utils.calib_data import 它，pyarrow 24 在 Windows 上 segfault
    # 推理不需要 calibration，stub 掉
    if "datasets" not in _sys.modules:
        _ds_stub = _types.ModuleType("datasets")
        _ds_stub.load_dataset = lambda *a, **k: None
        try:
            import importlib.machinery as _im
            _ds_stub.__spec__ = _im.ModuleSpec("datasets", loader=None)
        except Exception:
            pass
        _sys.modules["datasets"] = _ds_stub
    # transformers 4.47+ 删了 shard_checkpoint，autoawq 量化路径用，推理用不到
    try:
        import transformers.modeling_utils as _mu
        if not hasattr(_mu, "shard_checkpoint"):
            _mu.shard_checkpoint = lambda *a, **k: None
    except Exception:
        pass
    # transformers 4.57 改了 PytorchGELUTanh 模块组织，旧 autoawq 找不到时退化到 nn.GELU
    try:
        import transformers.activations as _ta
        import torch.nn as _nn
        for _sym in ("PytorchGELUTanh", "NewGELUActivation", "GELUActivation"):
            if not hasattr(_ta, _sym):
                setattr(_ta, _sym, _nn.GELU)
    except Exception:
        pass


_apply_autoawq_shim()


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

    _apply_autoawq_shim()  # 模块级已运行一次，这里幂等再保险
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

Concrete English example (each item has headline + top keywords):
Input:
[Chapter 1]
  - 段标题: What an AI Agent Is  | 高频词: agent / autonomy / reasoning / planning
  - 段标题: Agent vs Automation  | 高频词: automation / rule-based / agent / difference
[Chapter 2]
  - 段标题: Choosing an LLM Provider  | 高频词: provider / OpenAI / Anthropic / API
  - 段标题: API Key Setup  | 高频词: API / key / setup / environment

Output:
["AI Agent Fundamentals", "LLM Provider and API Setup"]

If a headline word does not appear in any chunk's keywords for that chapter,
treat it as an ASR mishearing or topic drift — drop it from the title.""",
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


# vlog 专属：美食探店 / 旅游打卡 / 日常实拍。结构是"场景切换"，不是"教学层次"
SYSTEM_PROMPT_VLOG = """你是 vlog/生活实拍视频结构化助手。给定一个 vlog 按时间顺序的\
"原子段"（每段有索引、时间范围、headline、关键词），把它们组织成符合 vlog 叙事节奏的\
章节大纲。

**⚠️ 输出语言匹配输入 headlines**：headlines 是英文则章标题用英文，中文则用中文。
**不要翻译**——保持原语言一致。

## 硬约束（违反必拒绝）

1. **顶层数量上限根据 n_chunks 自适应**：
   - n ≤ 6 → 顶层 ∈ [3, n]（每 chunk 一章可接受）
   - 7 ≤ n ≤ 12 → 顶层 ∈ [4, 7]（开始归并，每章 1-2 chunks）
   - n ≥ 13 → 顶层 ∈ [5, 8]（强制归并相邻同类，每章 2-4 chunks，**禁止每 chunk 一章**）
2. **单个顶层覆盖的 chunks 数 ≤ 4**（vlog/talk 上限）；n ≥ 13 长 vlog **必须有顶层覆盖 ≥ 2 chunks**（否则就是过碎）
3. 顶层按时间顺序覆盖 [0, n) 全部 chunk_idx，不漏不重不交叉
4. 标题 4-10 字中文 或 2-6 词英文 名词/动名词短语；可保留口语化但不要疑问句
5. **章标题必须从本章内 chunks 的 headlines 抽象**——禁止借用前后邻章主题
6. **长 vlog 归并思路（n ≥ 13）**：相邻 chunks 若属同一主题大类——多个菜品共属"刺身评测"/多个评测维度共属"价格分析"/多个店共属"商圈对比"——**必须合并为一章**。理想章数 ≈ ⌈n × 0.4⌉ ~ ⌈n × 0.6⌉。

## 切分思路（vlog 专属）

vlog 章节边界是**场景/活动/对象的切换**，不是教学概念层次：
- **换地点**（餐厅 → 商场 → 街头 → 回家）
- **换对象**（第一道菜 → 第二道菜 → 第三道菜；A 店 → B 店 → C 店）
- **换活动**（购物 → 试吃 → city walk → 结账总结）
- **节奏切片**（开场介绍 / 内容主体 / 收尾感想）

每章应该围绕**一个独立"片段"**，而不是合并多个独立场景。
如果 chunks 里有"接下来去 X / 我们去 Y / 现在准备 Z"等场景切换信号，
那是天然章节边界，**不要跨这种信号合章**。

**重要：chunk 0 不一定是"开场"**——很多 vlog 一上来就直接做主体内容（吃第一道菜 /
到达第一家店 / 试第一个产品）。如果 chunk 0 的 headline 已经描述了具体内容/对象
（如"酸菜牛肉面"、"大理石质感菜品"），章标题应直接用该内容，**不要硬叫它"开场介绍"**。
只在 chunk 0 真的是"今天我们要做 X / 大家好我是 X"这种纯铺垫时才用"开场"类标题。

## 完整示例（5 段泡面测评 vlog，chunk 0 已经在吃第一种泡面）

输入摘要：酸菜牛肉面(0) + 香辣牛肉面(1) + 韩式泡面(2) + 老北京炸酱面(3) + 酸辣藤骨面(4)

```json
{
  "chapters": [
    {"title": "酸菜牛肉面", "chunks": [0]},
    {"title": "香辣牛肉面", "chunks": [1]},
    {"title": "韩式泡面", "chunks": [2]},
    {"title": "老北京炸酱面", "chunks": [3]},
    {"title": "酸辣藤骨面", "chunks": [4]}
  ]
}
```

**反例（chunk 0 错叫开场）**：`{"title": "开场介绍", "chunks": [0]}` ← chunk 0 实际在
品尝酸菜牛肉面，应直接用"酸菜牛肉面"作标题。

**反例（绝对不要）**：
```json
{"chapters": [
  {"title": "菜单与质感", "chunks": [0, 1]},
  {"title": "笋干与混合", "chunks": [2, 3]},
  {"title": "牛杂口味", "chunks": [4]}
]}
```
← 把 5 个独立菜品强行合成 2-3 章，丢失了"换菜品"的天然边界。

## 自检清单

1. 顶层数量在 [3, 6] ✓
2. **没有任何顶层 chunks 数 > 3** ✓
3. 覆盖 0~n-1 全部 chunk_idx ✓
4. 标题反映本章实际"片段/场景/对象"，不是抽象总结 ✓
5. 若 chunks 含"接下来 / 然后我们 / 现在去"切换信号，**已经把它当章节边界** ✓

只输出 JSON。"""


# talk 专属：时评 / 访谈 / 资讯解读。结构是"论点切换"
SYSTEM_PROMPT_TALK = """你是时评 / 资讯视频结构化助手。给定一个时评视频按时间顺序的\
"原子段"（每段有索引、时间范围、headline、关键词），把它们组织成符合论述节奏的\
章节大纲。

**⚠️ 输出语言匹配输入 headlines**：headlines 英文则章标题英文，中文则中文。**不要翻译**。

## 硬约束

1. **顶层数量 ∈ [3, 6]**——时评即使主题集中也能拆"事件背景 / 论点 1 / 论点 2 / 收尾"
2. **单个顶层覆盖的 chunks 数 ≤ 3**——论点切换频繁
3. 顶层按时间顺序覆盖 [0, n) 全部 chunk_idx
4. 标题 4-10 字中文 或 2-6 词英文 名词/动名词短语
5. 章标题必须从本章 chunks 的 headlines 抽象，不窜章

## 切分思路（talk 专属）

talk 章节边界是**观点/论据/对象的切换**：
- **事件背景介绍**（提出主题）
- **论点切换**（每个独立观点单独成章）
- **论据列举**（数据 / 案例 / 对比）
- **结论 / 个人感想**

不要按"教学逻辑层次"合并；论点之间即使逻辑相关也应**各自成章**。

## 示例（懂王推文时评，4 段）

```json
{
  "chapters": [
    {"title": "事件背景", "chunks": [0]},
    {"title": "推文内容分析", "chunks": [1]},
    {"title": "动机猜测", "chunks": [2]},
    {"title": "结尾观点", "chunks": [3]}
  ]
}
```

## 自检清单

1. 顶层数量 ∈ [3, 6] ✓
2. **没有任何顶层 chunks 数 > 3** ✓
3. 覆盖 0~n-1 ✓
4. 每章标题反映独立论点，不是大杂烩 ✓

只输出 JSON。"""


# category → system prompt
_CATEGORY_PROMPTS: dict[str, str] = {
    "teaching": SYSTEM_PROMPT,
    "popsci": SYSTEM_PROMPT,   # 科普走教学 prompt（章节按概念层次合理）
    "vlog": SYSTEM_PROMPT_VLOG,
    "talk": SYSTEM_PROMPT_TALK,
}


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
    # 一致性修正：若 repair 给顶层补了 chunk 但原 children 没覆盖父 chunks 全部，
    # 清空该层 children — 让下游 auto_subs 兜底重新生成（否则 _diagnose 看父 children
    # 通过但 _validate 校验 children 覆盖会 fail，输出空 chapters。
    # 2026-05-21 回归测试 BV19E411D78Q_p42 暴露）
    for ch in parsed.get("chapters", []):
        children = ch.get("children")
        if not isinstance(children, list) or not children:
            continue
        parent_chs = sorted(set(c for c in (ch.get("chunks") or []) if isinstance(c, int)))
        child_seen: list[int] = []
        for sub in children:
            child_seen.extend(c for c in (sub.get("chunks") or []) if isinstance(c, int))
        if sorted(set(child_seen)) != parent_chs:
            ch.pop("children", None)
    return parsed


# 中文虚词/连接词 stopword，jieba 切出来但不作为主题词候选
# （避免把 "的"、"和" 这种当成"共享 token"误剥）
_ZH_STOP = frozenset(
    "的 了 和 与 及 或 在 是 有 为 对 从 到 把 被 让 使 之 其 之间 以及 "
    "如何 什么 介绍 讲解 概述 简介 概念 内容 部分 章节 课程 这个 那个".split()
)

def _extract_zh_topic_tokens(s: str) -> set[str]:
    """jieba 切 -> 长度 ≥2 的纯中文 token；过滤 stopword + 含数字/字母的混合词。
    用 cut_for_search 而非 cut：词典里 "子网掩码" 是整词，cut 切不出独立 "子网"
    导致 "子网划分/子网掩码/子网寻址" 共享 "子网" 漏检。cut_for_search 在长词上
    多吐子词，保留 substring 共享信号；同时仍是语义切分，"管程引入" 不会吐出
    "管程引" 这种字符 garbage。
    """
    out: set[str] = set()
    for tok in jieba.cut_for_search(s, HMM=True):
        tok = tok.strip()
        if len(tok) < 2:
            continue
        if not re.fullmatch(r"[一-鿿]+", tok):
            continue  # 含字母/数字/标点的混合词交给英文路径
        if tok in _ZH_STOP:
            continue
        out.add(tok)
    return out


def _dedupe_common_topic_token(titles: list[str]) -> list[str]:
    """章标题主题词去重：若某 token 在 >=85% 章里出现，从所有标题剥离。
    剥后变空或连接词残留则该章回退原文。

    针对 LLM hedge 倾向产生的"NAT与IP / NAT功能 / NAT表" 或 "子网划分 / 子网掩码 /
    子网寻址" 这类冗余主干。仅在 N>=3 时触发。

    双 token 路径：
      - 英文/缩写：正则 [A-Za-z][A-Za-z0-9]+ | [A-Z]{2,}
      - 中文：jieba 切词 + stopword 过滤，长度≥2 纯中文
    """
    n = len(titles)
    if n < 3:
        return titles
    threshold = (n * 85 + 99) // 100  # ceil(N*0.85)

    en_re = re.compile(r"[A-Za-z][A-Za-z0-9]+|[A-Z]{2,}")
    title_tokens: list[set[str]] = []
    for s in titles:
        toks = {t.upper() for t in en_re.findall(s)}
        toks |= _extract_zh_topic_tokens(s)
        title_tokens.append(toks)

    counter: dict[str, int] = {}
    for ts in title_tokens:
        for tok in ts:
            counter[tok] = counter.get(tok, 0) + 1
    strip = [tok for tok, c in counter.items() if c >= threshold]
    if not strip:
        return titles

    out = []
    for orig in titles:
        new = orig
        for tok in strip:
            if re.fullmatch(r"[一-鿿]+", tok):
                # 中文 token：CJK 没有 word boundary，直接 literal 替换；
                # jieba 已保证 token 是语义单位，不会误吃 "管程引入" 中的 "管程"
                # 时把 "引入" 一起带走
                new = new.replace(tok, "")
            else:
                # 英文/缩写：用 lookaround 避开 \b 在 unicode \w 下的歧义
                # （"NAT与IP" 里 与 是 unicode word char，\b 不匹配 T-与 边界）
                new = re.sub(
                    rf"(?<![A-Za-z0-9]){re.escape(tok)}(?![A-Za-z0-9])",
                    "", new, flags=re.IGNORECASE,
                )
        # 收尾：折叠空格，剥两端连接符 / 标点
        new = re.sub(r"\s{2,}", " ", new).strip(" -·、，,.与和及的-")
        # 剥光了或剩连接词残骸，回退原文保险
        if not new or not re.search(r"[\w一-鿿]", new):
            new = orig
        out.append(new)
    if any(out[i] != titles[i] for i in range(n)):
        print(f"      [title-dedup] 剥离主题词 {strip} 自 {n} 章标题", flush=True)
    return out


def _diagnose_outline(parsed: dict, n_chunks: int,
                       chunks: Optional[list[dict]] = None,
                       category: str = "teaching") -> Optional[str]:
    """validation 失败时给 LLM 的人类可读 feedback。通过返回 None。

    chunks（含 start/end）非 None 时启用"单章时长不得超 45%"硬约束：
    见 2026-05-20 audit，NAT p51 一次切 4 章 ch1=48.4%，强制切更细。

    category vlog/talk 时单顶层 chunks 上限收紧到 3（教学/科普 5）。
    """
    # vlog/talk cap=4（2026-05-21 放宽，原 3 太严）：长 vlog n>=15 时 5 章×3=15<n 必然
    # 需要归并到每章 3-4 chunks。教学/科普仍 5（PPT 章节可能更长）。
    max_chunks_per_top = 4 if category in ("vlog", "talk") else 5
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
        # 每章 chunks 必须在时间线上连续（不能跳号），否则会造成章节区间嵌套
        if chs_set and chs_set[-1] - chs_set[0] + 1 != len(chs_set):
            gaps = sorted(set(range(chs_set[0], chs_set[-1] + 1)) - set(chs_set))
            return (f"第 {ci+1} 章 '{ch.get('title','')}' chunks={chs_set} 不连续，"
                    f"中间缺 {gaps}（每章 chunks 必须是连续区间，"
                    f"否则会与其它章时间重叠）")
        seen.extend(chs_set)
        # >max_chunks_per_top + no children 的硬性检查
        children = ch.get("children")
        has_children = isinstance(children, list) and len(children) > 0
        if len(chs_set) > max_chunks_per_top and not has_children:
            return (f"第 {ci+1} 章 '{ch.get('title','')}' 覆盖 {len(chs_set)} 个 chunks "
                    f"超过 {max_chunks_per_top} 个上限，必须拆为多个顶层"
                    f"（推荐每顶层 1-{max_chunks_per_top} chunks）")
    # 重叠 / 缺失检查
    duplicates = sorted(set([x for x in seen if seen.count(x) > 1]))
    if duplicates:
        return f"chunk_idx {duplicates} 出现在多个顶层（不允许跨章重叠）"
    missing = sorted(set(range(n_chunks)) - set(seen))
    if missing:
        return f"缺少 chunk_idx {missing}（必须覆盖 0~{n_chunks-1} 全部，不能漏）"
    # 顶层数下限统一为 children-aware：n>=4 要求 ≥3 顶层，n>=3 要求 ≥2 顶层；
    # 1 顶层 + ≥2 children 视为等价导航形态（auto_subs 兜底走这条；LLM 主动
    # 切"单顶层+多 children" 也命中）。2026-05-21 stress test 揭示原本两条规则
    # 不一致：L740 children-blind 在 n>=4 时把 auto_subs 注入的 N children 仍然
    # reject，导致 belt-and-suspenders 永不生效。
    min_top = 3 if n_chunks >= 4 else 2
    if n_chunks >= 3 and len(chapters) < min_top:
        top0_children = chapters[0].get("children") if chapters else None
        has_nav_subs = isinstance(top0_children, list) and len(top0_children) >= 2
        if not has_nav_subs:
            return (f"n_chunks={n_chunks} 顶层数 {len(chapters)} < {min_top}"
                    f"（应至少 {min_top} 顶层，或 1 顶层下挂 ≥2 children，"
                    f"否则笔记零导航价值）")
    # 2026-05-21 BV1q6 日料 vlog 16/19 几乎一章一 chunk 揭示：vlog/talk LLM 倾向不归并
    # 长 vlog 相邻同类 chunks，导致章节过碎。加比例硬约束：vlog/talk + n_chunks>=8 时
    # n_chapters / n_chunks 比 > 0.65 视为"过碎"，引导 LLM retry 时主动归并。
    # 教学/科普不限（教学每章 1-2 chunks 是正常的）。
    if category in ("vlog", "talk") and n_chunks >= 8:
        ratio = len(chapters) / n_chunks
        if ratio > 0.65:
            target_max = max(5, int(n_chunks * 0.6))
            return (f"n_chunks={n_chunks} 时切了 {len(chapters)} 章，"
                    f"过碎（比例 {ratio:.2f} > 0.65）。"
                    f"vlog/talk 长视频必须把相邻同类 chunks 归并——"
                    f"目标 ≤ {target_max} 章（每章 ~{n_chunks//target_max}-"
                    f"{(n_chunks+target_max-1)//target_max} chunks）")
    # 单章时长上限：n_chunks>=5 且 >=2 章时，任一章不得占总时长 >45%
    # 阈值取 45%（NAT p51 ch1=48.4% 命中，烤肉 vlog n=4 不受影响）
    if chunks is not None and n_chunks >= 5 and len(chapters) >= 2 and len(chunks) == n_chunks:
        total = chunks[-1].get("end", 0) - chunks[0].get("start", 0)
        if total > 0:
            for ci, ch in enumerate(chapters):
                cs = sorted(set(ch.get("chunks") or []))
                if not cs:
                    continue
                ch_dur = chunks[cs[-1]].get("end", 0) - chunks[cs[0]].get("start", 0)
                pct = ch_dur / total
                if pct > 0.45:
                    return (f"第 {ci+1} 章 '{ch.get('title','')}' 覆盖 "
                            f"{ch_dur/60:.1f}min/{total/60:.1f}min = "
                            f"{pct*100:.0f}% 总时长（>45% 上限），"
                            f"必须把这一章拆为多个更短的顶层")
    return None


def _validate_outline(outline: dict, n_chunks: int,
                       chunks: Optional[list[dict]] = None,
                       category: str = "teaching") -> Optional[dict]:
    """校验 LLM 输出：chunks 必须覆盖 [0, n_chunks) 全部，按顺序，无重叠。
    通过返回规整后的 outline；不通过返回 None。

    category vlog/talk 时单顶层 chunks 上限收紧到 3（教学/科普仍是 5）。
    """
    # 按 category 决定单顶层 chunks 上限
    # vlog/talk cap=4（2026-05-21 放宽，原 3 太严）：长 vlog n>=15 时 5 章×3=15<n 必然
    # 需要归并到每章 3-4 chunks。教学/科普仍 5（PPT 章节可能更长）。
    max_chunks_per_top = 4 if category in ("vlog", "talk") else 5
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
        # 每章 chunks 必须是时间上连续区间（否则会与其它章时间嵌套，见审计 video 4）
        if chs[-1] - chs[0] + 1 != len(chs):
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
    # 硬约束：promote 后仍有 >max_chunks_per_top chunks 顶层且无 children →
    # 视为 catch-all 失败，caller 应 fallback 到 TextTiling
    for ch in out_chapters:
        if len(ch["chunks"]) > max_chunks_per_top and not ch.get("children"):
            return None
    # 顶层数软下限（children-aware，与 _diagnose_outline 对齐）：
    # n>=4 要求 ≥3 顶层，n>=3 要求 ≥2 顶层；1 顶层 + ≥2 children 等价导航形态
    min_top = 3 if n_chunks >= 4 else 2
    if n_chunks >= 3 and len(out_chapters) < min_top:
        top0_children = out_chapters[0].get("children") if out_chapters else None
        if not (isinstance(top0_children, list) and len(top0_children) >= 2):
            return None
    # 过碎硬约束（与 _diagnose 对齐）：vlog/talk n>=8 时 chapters/chunks > 0.65 reject
    if category in ("vlog", "talk") and n_chunks >= 8:
        if len(out_chapters) / n_chunks > 0.65:
            return None
    # 单章时长上限（n_chunks≥5 + ≥2 章 + 任一章 >45% 总时长 → reject）
    if chunks is not None and n_chunks >= 5 and len(out_chapters) >= 2 and len(chunks) == n_chunks:
        total = chunks[-1].get("end", 0) - chunks[0].get("start", 0)
        if total > 0:
            for ch in out_chapters:
                cs = ch["chunks"]
                ch_dur = chunks[cs[-1]].get("end", 0) - chunks[cs[0]].get("start", 0)
                if ch_dur / total > 0.45:
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
                          category: str = "teaching",
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
    # 按 category 选 system prompt 和 user prompt 措辞
    sys_prompt_base = _CATEGORY_PROMPTS.get(category, SYSTEM_PROMPT)
    cat_label = {"teaching": "教学视频", "popsci": "科普视频",
                 "vlog": "vlog 实拍视频", "talk": "时评/资讯视频"}.get(category, "视频")
    # vlog/talk 的单顶层上限更小（3 而非 5），retry 提示词要同步
    chunks_per_top_cap = 4 if category in ("vlog", "talk") else 5
    user_prompt = (
        f"{cat_label}共 {n} 个原子段（chunk_idx 0~{n-1}）：\n\n"
        f"{chunk_text}\n"
        f"{visual_block}\n"
        "请按要求输出层级化大纲 JSON。"
    )
    model, tok = load_model(model_id)
    base_messages = [
        {"role": "system", "content": _system_with_lang(sys_prompt_base, lang, "segment")},
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
            temp = 0.05  # 2026-05-20 起从 0.15 降到 0.05 减切粒度方差
        else:
            messages = base_messages + [
                {"role": "assistant", "content": last_raw or ""},
                {"role": "user", "content":
                    f"上次输出违反硬约束：{last_err}\n\n"
                    f"请**重新输出完整的 JSON**（不要 partial 不要 diff），严格遵守所有硬约束："
                    f"顶层数 ∈ [3,6]、单顶层 chunks ≤ {chunks_per_top_cap}、"
                    f"覆盖 0~{n-1} 全部 chunk_idx 无漏无重。"},
            ]
            # 重试温度更低更确定性
            temp = max(0.02, 0.05 - 0.01 * attempt)
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
        # 后处理：把"过粗顶层（>cap chunks + 有 children）"的 children 提升为顶层
        before_promote_chs = [len(c.get("chunks") or []) for c in parsed.get("chapters", [])]
        parsed = _promote_oversized(parsed, max_chunks_per_top=chunks_per_top_cap)
        after_promote_chs = [len(c.get("chunks") or []) for c in parsed.get("chapters", [])]
        if before_promote_chs != after_promote_chs and "promote_oversized" not in meta["repair_used"]:
            meta["repair_used"].append("promote_oversized")
        err = _diagnose_outline(parsed, n, chunks=chunks, category=category)
        if err is None:
            ok = True
            last_err = None
            meta["pass_via"] = f"attempt_{attempt+1}"
            print(f"      [llm] attempt {attempt+1} [OK] validation passed", flush=True)
            break
        last_err = err
        # 抓 err 的短类型（"oversize" / "missing" / "duplicate" / "too_few" / "non_contiguous"）
        if "个上限" in err:
            meta["fail_reasons"].append("oversize")
        elif "缺少 chunk_idx" in err:
            meta["fail_reasons"].append("missing")
        elif "出现在多个顶层" in err:
            meta["fail_reasons"].append("duplicate")
        elif "顶层数" in err and "应至少 3" in err:
            # 合并后 too_few_chapters: "顶层数 X < 3（应至少 3 顶层...）"
            meta["fail_reasons"].append("too_few_chapters")
        elif "顶层数" in err and "应至少 2" in err:
            # 合并后 no_nav_points: "顶层数 X < 2（应至少 2 顶层...）"
            meta["fail_reasons"].append("no_nav_points")
        elif "过碎" in err:
            meta["fail_reasons"].append("over_segmented")
        elif "不连续" in err:
            meta["fail_reasons"].append("non_contiguous")
        elif "总时长（>45%" in err:
            meta["fail_reasons"].append("dominant_chapter")
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
            repaired = _promote_oversized(repaired, max_chunks_per_top=chunks_per_top_cap)
            before_oversize_chs = [len(c.get("chunks") or []) for c in repaired.get("chapters", [])]
            repaired = _repair_oversize(repaired, chunks, max_chunks_per_top=chunks_per_top_cap)
            after_oversize_chs = [len(c.get("chunks") or []) for c in repaired.get("chapters", [])]
            if before_oversize_chs != after_oversize_chs:
                meta["repair_used"].append("repair_oversize")
            err = _diagnose_outline(repaired, n, category=category)
            if err is None:
                parsed = repaired
                ok = True
                meta["pass_via"] = "repair"
                print(f"      [llm] programmatic repair [OK]", flush=True)
            else:
                print(f"      [llm] repair attempted but still invalid: {err}", flush=True)
        # Step 3 (兜底): 单顶层 n_chunks≥3 → 用 chunks headline 自动生 1:N 子章节
        # 保留 LLM 的"语义统一"判断，但用 sub-chapters 给用户至少 N 个导航点
        if not ok and parsed is not None:
            chs = parsed.get("chapters") or []
            if (len(chs) == 1 and n >= 3
                    and isinstance(chs[0].get("chunks"), list)
                    and sorted(chs[0]["chunks"]) == list(range(n))):
                sub_chapters = []
                for i in range(n):
                    head = (chunks[i].get("headline") or "").strip()
                    if not head:
                        head = chunks[i].get("text", "").strip()[:20] or f"段 {i+1}"
                    sub_chapters.append({"title": head[:30], "chunks": [i]})
                chs[0]["children"] = sub_chapters
                err2 = _diagnose_outline(parsed, n, chunks=chunks)
                if err2 is None:
                    ok = True
                    meta["pass_via"] = "repair"
                    if "auto_subs_for_single_top" not in meta["repair_used"]:
                        meta["repair_used"].append("auto_subs_for_single_top")
                    print(f"      [llm] 单顶层兜底：自动生成 {n} 个子章节 [OK]", flush=True)
                else:
                    print(f"      [llm] auto-subs 兜底失败: {err2}", flush=True)
    if not ok or parsed is None:
        print(f"      [llm] all {max_retries+1} attempts + repair failed (last: {last_err})",
              flush=True)
        # 返回 _meta 让 caller 写到 ablation 里（虽然没出 chapters），便于事后
        # 在论文附录 B 表里准确显示 "LLM 跑了 N 次 attempt 失败 → fallback"
        return {"chapters": [], "_meta": meta}
    outline = _validate_outline(parsed, n, chunks=chunks, category=category)
    if outline is None:
        # 理论上 _diagnose 通过了 _validate 也该通过，兜底
        print(f"      [llm] outline validation failed after diagnose passed (bug?)", flush=True)
        return {"chapters": [], "_meta": meta}

    # B1: 二次调 LLM，按"只看本章 headlines"重写章标题，避开邻章串台问题
    refined_titles = refine_chapter_titles(outline, chunks, lang=lang, category=category)
    if refined_titles and len(refined_titles) == len(outline["chapters"]):
        # 空字符串不覆盖原 title（refine 内部兜底可能补空串）
        for ch, new_title in zip(outline["chapters"], refined_titles):
            if not new_title or not new_title.strip():
                continue
            ch["title_v1"] = ch["title"]  # 留底，便于对照
            ch["title"] = new_title

    # B2: 主题词去重 — 若某 alphanumeric token 在 >=85% 章标题里出现（且 ≥3 章），
    # 从所有标题剥离，避免 "NAT与IP / NAT功能 / NAT表 / ..." 这种冗余开头
    deduped = _dedupe_common_topic_token([ch["title"] for ch in outline["chapters"]])
    for ch, new_title in zip(outline["chapters"], deduped):
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
连续段（每段两行：段标题 + 高频词），为每章生成一个 6-14 字（中文）或 3-7 词\
（英文）的章标题。

**⚠️ 输出语言匹配输入**：段标题是英文则章标题用英文（如 "AI Agent Tooling"），\
段标题是中文则章标题用中文（如 "管程引入与基本特征"）。**不要翻译**。

## Step 1 — 命名前必做：段标题校准（防 ASR 错字 / 标题漂移）

"段标题"由上游 LLM 从一句口语生成，**可能含 ASR 错字或漂移**（实际段内容跟\
"高频词"才对得上）。所以**第一步是校准每个段标题**：

1. 扫"段标题"里的每个名词
2. 看该名词是否在**本段"高频词"列表**里出现（或近义、同字根、同型号）
3. **若名词没出现 → 是 ASR 错字 / 漂移，从命名候选里剔除，禁止原样进入章标题**
4. 命名时改用"高频词"里实际出现的概念

校准示例（教学场景较少触发，主要用于 ASR 极差时）：
  段标题: 烟台显卡  | 高频词: 块钱 / 一千 / 英瑞 / 一套
  → "烟台" 不在高频词 → 剔除（ASR 错字）；命名候选只剩"显卡 + 询价"

## Step 2 — 命名规则

1. **标题关键词必须在"已校准段标题"或"高频词"里出现过**——绝对不要借用其他章
2. 名词短语，不带动词 / 疑问 / 句末标点
3. **强制并列检查**（仅对校准通过的段适用）：若本章有 ≥2 个 chunks，检查
   **校准后**的段标题是否包含 ≥2 个并列子主题（如"定常子网划分" + "变长子网\
   划分"，"直通交换" + "存储转发"）。命中并列时**标题必须用 "X 与 Y" / "X 和 Y"\
   包含全部并列主题，不允许只挑一个写**。
   **校准失败的段绝不进入 "X 与 Y" 拼接** ——这种情况只用通过校准的那段，或两\
   段共同高频词抽象命名。
4. 单段成章时，标题可与该段标题相近但略上升抽象层。**绝对不要**把单段成章错用
   为"开场介绍 / 结尾感想 / 收尾总结"等通用模板——如果段标题已描述具体对象/事件
   （如"酸菜牛肉面"、"大理石质感菜品"），章标题就用其本身或其变体

## 反例（不允许）

输入：[第 1 章: 段标题包括"直通交换方式"、"存储转发交换"]
错误输出："直通交换" ✗（漏存储转发）
正确输出："直通与存储转发" ✓

输入：[第 1 章: 段标题包括"定常子网划分原理"、"变长子网划分实例"、"IP地址资源分配"]
错误输出："变长子网划分与IP资源" ✗（漏定常子网划分）
正确输出："定常与变长子网划分" ✓（次主题 IP 资源进 abstract，不进标题）

## 输出格式（必须严格遵守）

**整个输出是 ONE JSON 数组**，长度等于输入章数。**不要**分成多个 `[...]` 数组。

示例（输入 3 章；每段含"段标题"+"高频词"）：
输入：
[第 1 章]
  - 段标题: 进程概念  | 高频词: 进程 / PCB / 调度 / 上下文
  - 段标题: 线程引入  | 高频词: 线程 / 轻量 / TCB / 用户态
[第 2 章]
  - 段标题: 信号量定义  | 高频词: 信号量 / 临界区 / wait / signal
  - 段标题: PV 操作  | 高频词: P / V / 原子 / 互斥
[第 3 章]
  - 段标题: 死锁条件  | 高频词: 死锁 / 互斥 / 占有等待 / 不剥夺

输出：
["进程与线程基础", "信号量与PV操作", "死锁产生条件"]

注意：**所有标题在一个数组里**，逗号分隔,**不要**输出多个 `[...]`。"""


# vlog/talk 专属章标题 prompt — 避开 "X 与 Y 与 Z" 拼接机械感
TITLE_CHAPTER_VLOG_SYSTEM = """你是 vlog / 实拍视频的片段命名助手。给定若干"片段"\
（每段含"段标题 + 高频词"两行），为每个片段生成一个 4-12 字的中文片段标题。

**⚠️ 输出语言匹配输入**：段标题英文则片段标题用英文，中文则用中文。**不要翻译**。

## Step 1 — 命名前必做：段标题校准（防 ASR 错字 / 标题漂移）

"段标题"由上游 LLM 从一句口语生成，**可能含 ASR 错字或漂移**（实际段内容跟"高频词"\
才对得上）。所以**第一步是校准每个段标题**：

1. 扫"段标题"里的每个名词
2. 看该名词是否在**本段"高频词"列表**里出现（或近义、同字根、同型号）
3. **若名词没出现 → 它是 ASR 错字 / 漂移，从命名候选里剔除，禁止原样进入片段标题**
4. 命名时改用"高频词"里实际出现的概念

校准示例 1：
  段标题: 烟台显卡  | 高频词: 块钱 / 一千 / 英瑞 / 一套
  校准过程：
    - "烟台" 不在高频词 → 剔除（应为 ASR 错字 "验台/验代"）
    - "显卡" 是类目泛指，跟高频词"英瑞/块钱"的"显卡询价"语义一致 → 可保留
  → 候选命名词：显卡 + 询价/价格

校准示例 2：
  段标题: 电源配件  | 高频词: X79 / 580 / 配件 / 双路 / 半个
  校准过程：
    - "电源" 不在高频词（与 X79/580 不一致）→ 剔除（漂移）
    - "配件" 在高频词 → 保留
  → 候选命名词：X79 / 580 / 配件 / 双路

## Step 2 — 命名规则

1. 用名词或动名词短语，不带句末标点 / 疑问 / 数字序号（如"第一道菜"）
2. **单段成片段**：用"已校准段标题"或基于其抽象（如"酸菜牛肉面"→保留）
3. **2 段成片段**：
   - 优先**用上位词**统一两段（如"鸽子腿 + 价格"→"鸽子腿评价"）
   - **校准失败的段绝不进入 "X 与 Y" 拼接** ——这种情况只有两个出路：①用通过\
     校准的那段命名 ②用两段共同高频词抽象命名
   - 只有两段**都通过校准且确为真并列概念**时才可用"X 与 Y"
4. **3+ 段成片段**：禁止"X 与 Y 与 Z" 三连拼接，抽象出**共同上位概念**：
   - 多个菜品 → "海鲜评测" / "刺身系列"
   - 多个评测维度 → "细节点评" / "口感与价格"
   - 多个店 → "店家对比" / "横评"
5. **可读性 + 检索关键词** —— 读者扫一眼能秒懂这段讲了什么

## 完整校准+命名正例（输入 → 校准 → 输出）

输入：
[片段 1]
  - 段标题: 烟台显卡  | 高频词: 块钱 / 一千 / 英瑞 / 一套
  - 段标题: 3070显卡  | 高频词: 1000 / 块钱 / 内存 / 9000

校准：
  段 1："烟台"不在高频词 → 剔除；"显卡"为类目可保留 → 候选：显卡/询价
  段 2："3070"在高频词 → 保留；"显卡"保留 → 候选：3070/显卡
共同主题：显卡 + 价格询问 → 标题"显卡询价对比"
**错例**："烟台显卡与3070显卡" ✗（"烟台"未通过校准，绝不能进标题）

输入：
[片段 1]
  - 段标题: 电源配件  | 高频词: X79 / 580 / 配件 / 双路 / 半个
  - 段标题: 580显卡  | 高频词: 1000 / 块钱 / 580 / 10 / R7X / 750Ti

校准：
  段 1："电源"不在高频词 → 剔除；"配件"在高频词 → 候选：X79/580/配件
  段 2："580""750Ti""R7X"在高频词 → 保留 → 候选：580/750Ti/R7X 显卡
共同主题：杂牌老显卡组合 → 标题"X79与580显卡配件"
**错例**："电源配件与580显卡" ✗（"电源"未通过校准）

## 拼接机械感反例

- "安全与小麻烦与蚝虾" ✗ → "蚝虾品质评测" ✓
- "蚝虾与自助筛选与及格" ✗ → "蚝虾选购标准" ✓

## 输出格式

**整个输出是 ONE JSON 数组**，长度等于输入片段数，元素是字符串。
**不要**分成多个 `[...]` 数组、不要 markdown 标记，**不要输出校准过程**——\
校准在你脑里做，只输出最终标题数组。"""


_HEADLINE_DROP_TEXT_HITS = 3  # noun 在 chunk text 出现 ≥ 该次数即视为"段内主题"
                              # （即便不在 top-K kw 也保留），低于则视为 ASR 错字/漂移


def _calibrate_headline_words(headline: str, keywords: list,
                              text: str) -> dict:
    """Python 端 Step 1 校准：从 headline 里挑出名词，逐个验证是否在 keywords
    或 chunk text 里有支撑。返回 {ok, drop} 两个名词列表。

    drop 里的词将作为 "已识别 ASR 错字" 显式传给 LLM，模型不再自己做这一步。
    """
    import jieba.posseg as pseg
    kw_set = set(str(k) for k in keywords)
    ok, drop = [], []
    seen = set()
    for w, flag in pseg.cut(headline):
        if w in seen or len(w) < 2:
            continue
        seen.add(w)
        # ASCII 数字 / 英文（型号 X79/580/3070/R7X 等）不参与校验：
        # 即便不在 top-K kw 里，这类型号也是 chunker 从文本里有意识保留的，
        # 误 drop 反而损失关键信息
        if w.isascii():
            ok.append(w)
            continue
        # 只校验名词：jieba pos 含 n*/nz；m(数词) 多为 ASCII 已在上面跳过
        if not (flag.startswith("n") or flag in ("nz",)):
            continue
        # 严格匹配 + 子串匹配 + 高频词全字符串包含
        in_kw = (w in kw_set
                 or any(w in k or k in w for k in kw_set))
        in_text = text.count(w) >= _HEADLINE_DROP_TEXT_HITS if text else False
        if in_kw or in_text:
            ok.append(w)
        else:
            drop.append(w)
    return {"ok": ok, "drop": drop}


def refine_chapter_titles(outline: dict, chunks: list[dict],
                          model_id: str = _DEFAULT_MODEL,
                          max_new_tokens: int = 400,
                          lang: str = "zh",
                          category: str = "teaching") -> Optional[list[str]]:
    """二次调 LLM，仅基于每章内部 chunks 的 headlines 命名章标题。
    避开"一次切+命名"时邻章 headline 串台。成功返回与顶层等长的标题列表。

    category=vlog/talk 时切到 TITLE_CHAPTER_VLOG_SYSTEM，避开 "X 与 Y 与 Z" 拼接。"""
    chapters = outline.get("chapters", [])
    if not chapters:
        return None
    K = len(chapters)
    lines = []
    any_drop = False
    for ci, ch in enumerate(chapters):
        lines.append(f"[第 {ci+1} 章]")
        for idx in ch["chunks"]:
            c = chunks[idx]
            hl = c.get("headline") or c.get("text", "")[:30]
            kws = c.get("keywords") or []
            text = c.get("text", "") or ""
            kws_str = " / ".join(str(k) for k in kws[:5]) if kws else "(无)"
            cal = _calibrate_headline_words(hl, kws, text)
            line = f"  - 段标题: {hl}  | 高频词: {kws_str}"
            if cal["drop"]:
                any_drop = True
                line += f"  | ⚠️ 已识别 ASR 错字 (禁用): {', '.join(cal['drop'])}"
            lines.append(line)
    body = "\n".join(lines)
    drop_clause = (
        "\n⚠️ 标注了「已识别 ASR 错字」的词是 Python 校准过的，**绝对禁止**\n"
        "进入任何章/片段标题。若该段所有关键名词都被标禁，则该段不能单独主导\n"
        "命名，必须借同章其他段或共同高频词抽象。\n"
        if any_drop else "")
    user_prompt = (f"共 {K} 章/片段，请按顺序命名。\n"
                   f"{drop_clause}\n"
                   f"{body}\n\n"
                   f"输出 JSON 数组（必须 {K} 个元素）：")
    model, tok = load_model(model_id)
    # vlog/talk 用专属 prompt 避开 "X 与 Y 与 Z" 拼接
    sys_prompt = (TITLE_CHAPTER_VLOG_SYSTEM if category in ("vlog", "talk")
                  else TITLE_CHAPTER_SYSTEM)
    messages = [
        {"role": "system", "content": _system_with_lang(sys_prompt, lang, "title")},
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
    # 之前的 "K//2 个就用空串补齐"逻辑会让 LLM **漏中间某章** 时所有标题视觉
    # 上整体错位 1 位（用户实测：5 章 LLM 出 4 个，末位空 + ch2-4 用了下一章的
    # headline，看起来全偏移）。改用更严格的策略：少一个就 reject，让 caller
    # 保留 segment_hierarchical 第一步给的 fallback 标题
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


VLOG_SECTION_ABSTRACT_SYSTEM = """你是 vlog / 实拍视频的片段简介助手。给定若干片段\
（每个片段含若干场景标题），为每个片段生成 1-2 句话的简介。

**⚠️ 输出语言匹配输入**：标题是英文则简介用英文（"This section explores..."），\
中文则用中文（"本段..."）。**不要翻译**——保持原语言一致。

要求：
1. 每段输出 30-100 字（中文）或 15-50 词（英文）的陈述句 prose 简介
2. **必须以「本段」/「这一段」开头**（中文），**禁止使用「本章」**——这是 vlog 类\
   叙事内容，没有"章"的概念，用"段/片段"才贴
3. 用陈述句概括"本段拍了什么 + 看点"
4. **必须包含 1-2 个具体场景元素**（地点 / 人物 / 物品 / 价格 / 体验），不允许只写\
   "本段介绍 X 的相关内容" 这种空泛表述
5. 简介里出现的关键词必须从本段的场景标题里抽，**不要借邻段关键词**
6. **不要**列举式 "本段涵盖 X、Y、Z"，要 prose 风格的连贯句子
7. 单场景成段时，可在该场景标题基础上展开成 1 句话
8. **严格输出 K 个 abstract**（K = 片段数）：每段对应一个 abstract
9. 严格输出 JSON 数组，长度 = 片段数，元素为字符串

## 写作格式参考（下面是格式 demo，**不是输入数据**——不要把示例里的实体词抄到你的输出）

格式反例（不允许的写法）：
- "本章探讨 X 的相关内容。" ✗ ——用"本章"且空泛、无具体场景
- "本段介绍 X 的历史背景及其背后的故事。" ✗ ——空话，没说本段实际拍了什么

格式正例（应该的写法）：
- "本段走访 <地点>，展示 <物品> 的 <价格/数值> 与 <对比项> 的反差，揭示 <洞察>。"
- "本段实地探访 <场景>，对比 <A> 和 <B> 的 <差异>，解释 <根因>。"

**关键约束**：写 abstract 时只能用**当前输入数据本片段标题里出现过的实体词**——
不允许引入示例占位符里的概念（如"北极"、"底特律"、"KFC"、"超市"）到当前输出，
除非那些词真的出现在你这次的输入数据里。

## 输出格式（必须严格遵守）

**整个输出是 ONE JSON 数组**，**不要**分成多个 `[...]` 数组。

不要 markdown / 解释 / 前言。"""


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
                               lang: str = "zh",
                               category: str = "teaching") -> Optional[list[str]]:
    """批量生成章节级 abstractive 概述（1-2 句 prose）。
    chapters 需含 chunks 列表（每个 chunk 含 headline）。
    成功返回与 chapters 等长字符串列表；失败返回 None（caller 应 fallback summarize_chapter）。

    category=vlog/talk 时切到 VLOG_SECTION_ABSTRACT_SYSTEM（"本段..."开头 + 场景元素），
    其余走 CHAPTER_ABSTRACT_SYSTEM（"本章..."开头 + 技术点）。

    max_new_tokens 默认按 K 动态算（每 abstract ~150 tokens），防多章 K>=6 截断。"""
    if not chapters:
        return None
    K = len(chapters)
    if max_new_tokens is None:
        max_new_tokens = max(600, 180 * K)
    is_vlog_like = category in ("vlog", "talk")
    unit_word = "片段" if is_vlog_like else "章"
    sys_prompt = (VLOG_SECTION_ABSTRACT_SYSTEM if is_vlog_like
                  else CHAPTER_ABSTRACT_SYSTEM)
    # 2026-05-21 BV1q6 日料 vlog 揭示：只喂 headline 关键词导致 LLM 从字面 hallucinate
    # abstract（"心理线"→股市，"包容心"→情感，"皇上价格"→清朝皇帝）。补 snippet
    # 让 LLM 看见 ASR 实际内容。snippet 优先 summary（抽取式紧凑），fallback text[:200]。
    # 长视频 K>=10 时收紧 snippet 长度防 context 超额。
    snippet_max = 200 if K <= 8 else 120
    lines = []
    any_drop = False
    all_drops: set[str] = set()
    for ci, ch in enumerate(chapters):
        title = ch.get("title", "")
        lines.append(f"[第 {ci+1} {unit_word}" + (f": {title}" if title else "") + "]")
        for sub_c in ch.get("chunks", []):
            hl = (sub_c.get("headline") or "").strip()
            kws = sub_c.get("keywords") or []
            text = sub_c.get("text", "") or ""
            cal = _calibrate_headline_words(hl, kws, text) if hl else {"drop": []}
            # 标题校准结果：headline 里的 ASR 错字直接从 headline 字面 mask 掉
            # （drop 词替换成 [?]），让 LLM 看不到原词。比单纯 prompt 警告稳得多
            hl_display = hl
            for w in cal["drop"]:
                hl_display = hl_display.replace(w, "[?]")
                all_drops.add(w)
                any_drop = True
            if hl_display:
                lines.append(f"  - {hl_display}")
            snippet = (sub_c.get("summary") or sub_c.get("text") or "").strip()
            if snippet:
                snippet = re.sub(r"\s+", " ", snippet)[:snippet_max]
                # snippet 里同 mask：保留上下文但屏蔽 ASR 错字字面
                for w in cal["drop"]:
                    snippet = snippet.replace(w, "[?]")
                lines.append(f"    内容: {snippet}")
    body = "\n".join(lines)
    drop_clause = (
        f"\n⚠️ 文本中的 [?] 是 Python 校准过的 ASR 错字 mask "
        f"(原词: {', '.join(sorted(all_drops))})——abstract 里**不要**写 [?]，"
        f"也**不要**尝试还原原词；用「内容」里实际描述的概念替代。\n"
        if any_drop else "")
    user_prompt = (f"共 {K} {unit_word}，请基于每{unit_word}下"
                   f"「内容」字段中的实际转写文本生成 1-2 句简介。"
                   f"**严格根据「内容」实际讲的事情写**——"
                   f"不要从{unit_word}标题字面猜测含义，"
                   f"不要写「内容」里没出现的概念或场景。"
                   f"{drop_clause}\n{body}\n\n"
                   f"输出 JSON 数组（必须 {K} 个元素）：")
    model, tok = load_model(model_id)
    messages = [
        {"role": "system", "content": _system_with_lang(sys_prompt, lang, "abstract")},
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


CHAPTER_RECAP_SYSTEM = """你是教学视频的**复习要点**生成助手。给定一章的内容，\
生成 3-5 条复习要点，专门为期末/考研复习场景设计。

**⚠️ 输出语言匹配输入**：段内容是英文则要点用英文，中文则用中文。**不要翻译**。

## 与 abstract 的区别
- abstract 是"本章讲了什么"的概括（1-2 句陈述句）
- recap 是"学完本章要能复述什么"的可考点（3-5 条 bullet）
- 不要重复 abstract 已经说过的话——要更细、可考的知识点

## 要求
1. **3-5 条 / 章**：少于 3 条信息不够，多于 5 条复习过载
2. **每条 10-30 字（中文）或 5-15 词（英文）**：精炼但完整
3. **复习导向**：是"X 是什么/为什么/怎么做"的具体可考点，不是空泛概括
4. **基于本章实际内容**（chunks 的 headline / 内容）——不要从章标题字面猜测
5. **每条单独成行，以 "- " 开头**
6. 用名词性短句，不带句末标点（不要 ?!。）

## 输出格式（绝对硬约束，违反直接重试）

**输入有 K 章 → 输出 JSON 数组必须 K 个元素**（每个元素 = 该章独立 recap 字符串，含 `\\n` 分隔的多行 bullet）。

**绝对禁止**：
- ✗ 把多章 recap 合并成一个字符串（哪怕章主题相近）
- ✗ 输出多个 `[...]` 数组连写
- ✗ markdown fence (```​json) 包裹

每个 chapter 都要在数组里独占一个元素，**即便该章只有 1 个 chunk**也单独输出一个 recap。

示例（输入 **3** 章——注意输出数组有 **3** 个元素，一一对应）：
输入：
[第 1 章: 进程与线程基础]
  - 进程概念  | 内容: 进程是程序的一次执行，是 OS 资源分配的基本单位...
  - 线程引入  | 内容: 线程是 CPU 调度的基本单位，同一进程内线程共享地址空间...
[第 2 章: 信号量与 PV 操作]
  - 信号量定义  | 内容: 信号量是一个整型变量，配合 PV 操作实现进程同步...
  - PV 操作  | 内容: P 操作 = wait = -1；V 操作 = signal = +1，必须原子执行...
[第 3 章: 死锁条件]
  - 死锁四必要条件  | 内容: 互斥、占有等待、不剥夺、循环等待...

输出（3 个元素，按章顺序）：
[
  "- 进程是 OS 资源分配单位，含 PCB 描述\\n- 线程是 CPU 调度单位，同进程线程共享地址空间\\n- 上下文切换：进程开销 > 线程开销",
  "- 信号量是整型变量，配 PV 实现同步互斥\\n- P 操作：sem-- 若负则阻塞\\n- V 操作：sem++ 若不正则唤醒\\n- PV 必须原子，否则失去互斥保证",
  "- 死锁四必要条件：互斥、占有等待、不剥夺、循环等待\\n- 缺任一条件死锁即不能成立\\n- 预防死锁 = 破坏其中一个条件"
]"""


def generate_chapter_recaps(chapters: list[dict],
                            model_id: str = _DEFAULT_MODEL,
                            max_new_tokens: Optional[int] = None,
                            lang: str = "zh") -> Optional[list[str]]:
    """学习类章末复习要点（3-5 条 bullet list）。
    chapters 需含 chunks 列表（每个 chunk 含 headline + summary/text）。

    返回与 chapters 等长字符串列表（每个字符串是多行 bullet markdown）；
    失败返回 None，caller 应 fallback 到抽取式 chapter_recap。

    与 generate_chapter_abstracts 的区别：abstract 是 prose 概括（1-2 句），
    recap 是 bullet 复习点（3-5 条），用于学习/考研场景。仅对 teaching/popsci
    类视频生成，vlog/talk 略过（recap 概念在 vlog 上无意义）。"""
    if not chapters:
        return None
    K = len(chapters)
    if max_new_tokens is None:
        max_new_tokens = max(800, 220 * K)
    snippet_max = 200 if K <= 8 else 120
    lines = []
    any_drop = False
    all_drops: set[str] = set()
    for ci, ch in enumerate(chapters):
        title = ch.get("title", "")
        lines.append(f"[第 {ci+1} 章" + (f": {title}" if title else "") + "]")
        for sub_c in ch.get("chunks", []):
            hl = (sub_c.get("headline") or "").strip()
            kws = sub_c.get("keywords") or []
            text = sub_c.get("text", "") or ""
            cal = _calibrate_headline_words(hl, kws, text) if hl else {"drop": []}
            hl_display = hl
            for w in cal["drop"]:
                hl_display = hl_display.replace(w, "[?]")
                all_drops.add(w)
                any_drop = True
            if hl_display:
                lines.append(f"  - {hl_display}")
            snippet = (sub_c.get("summary") or sub_c.get("text") or "").strip()
            if snippet:
                snippet = re.sub(r"\s+", " ", snippet)[:snippet_max]
                for w in cal["drop"]:
                    snippet = snippet.replace(w, "[?]")
                lines.append(f"    内容: {snippet}")
    body = "\n".join(lines)
    drop_clause = (
        f"\n⚠️ 文本中的 [?] 是 Python 校准过的 ASR 错字 mask"
        f"(原词: {', '.join(sorted(all_drops))})——recap 里**不要**写 [?]，"
        f"也**不要**尝试还原原词。\n"
        if any_drop else "")
    user_prompt = (f"共 {K} 章，按顺序为每章生成 3-5 条复习要点 bullet list。\n"
                   f"**输出数组必须有 {K} 个元素**——每章对应一个独立的 recap "
                   f"字符串，禁止合并章。\n"
                   f"{drop_clause}\n{body}\n\n"
                   f"输出 JSON 数组（必须 {K} 个元素，每个元素是含 \\n 的多行 "
                   f"bullet 字符串）：")
    model, tok = load_model(model_id)
    messages = [
        {"role": "system", "content": _system_with_lang(CHAPTER_RECAP_SYSTEM, lang, "recap")},
        {"role": "user", "content": user_prompt},
    ]
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    import torch
    inputs = tok(text, return_tensors="pt").to(model.device)
    print(f"      [llm-chapter-recap] generate for {K} chapters "
          f"(input {inputs['input_ids'].shape[1]} tokens) ...", flush=True)
    with torch.no_grad():
        out = model.generate(
            **inputs, max_new_tokens=max_new_tokens, do_sample=True,
            temperature=0.25, top_p=0.9, pad_token_id=tok.eos_token_id,
        )
    gen_ids = out[0][inputs["input_ids"].shape[1]:]
    raw = tok.decode(gen_ids, skip_special_tokens=True).strip()
    arr = _parse_titles_array(raw, K)
    if arr is None:
        print(f"      [llm-chapter-recap] parse failed, raw: {raw[:250]}", flush=True)
        return None
    recaps = [str(s).strip().strip('"').strip("'") for s in arr]
    print(f"      [llm-chapter-recap] generated {K} chapter recaps", flush=True)
    return recaps


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
        # 三段采样覆盖整 chunk，防 head-only / tail-only recency bias。
        # 2026-05-21 BV1q6 vlog 揭示原版 head+mid 仍漏：chunk6 90% 内容讲"年糕虾"
        # 但 tail 末句提到"南瓜汤" → LLM 把"南瓜汤"当 headline。补 tail 让 LLM 看见
        # 主题在三段中出现频率（≥2 段共现 = 主体；仅 1 段出现 = catchy 过渡词）。
        head = full[:200]
        mid = full[len(full)//2:len(full)//2 + 150] if len(full) > 350 else ""
        tail = full[-150:] if len(full) > 350 else ""
        kws = c.get("keywords") or []
        lines.append(f"[Chunk {i:02d}]")
        if kws:
            lines.append(f"  关键词: {', '.join(kws[:6])}")  # jieba top-6 锚主题
        if head:
            lines.append(f"  开头: {head}")
        if mid:
            lines.append(f"  中段: {mid}")
        if tail:
            lines.append(f"  结尾: {tail}")
    user_prompt = (
        f"共 {n} 段，请按顺序为每段生成 {n} 个标题：\n\n" +
        "\n".join(lines) +
        f"\n\n输出 JSON 数组（必须 {n} 个元素）。\n"
        f"## 标题选词硬约束\n"
        f"1. **标题的核心名词必须满足以下任一**：\n"
        f"   (a) 出现在该段的关键词列表中（首选），或\n"
        f"   (b) 在开头/中段/结尾三段采样中出现 **≥2 段**（共现 = 主体）\n"
        f"2. **禁止采用只在单一段出现且不在关键词的词** —— 那是上段或下段过渡词\n"
        f"3. 2026-05-21 BV1q6 反例：某段 keywords=[好吃,黑头,刺身] 但 tail 末句\n"
        f"   出现一次'护眼仪' → 错误抓'护眼仪'作标题。正确做法：keywords 没有\n"
        f"   '护眼仪' 且 head/mid 没有 → 是下段过渡，应从 keywords 选'刺身'类主体\n"
        f"4. 标题 4-12 字中文 或 2-6 词英文，名词短语，去口语词"
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
