"""神经摘要：Randeng-Pegasus-238M-Summary-Chinese 生成式摘要。

跟 summarize.py 的 jieba 抽取式同一套返回结构，便于 pipeline 平滑切换。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

# ctranslate2 / torch / pegasus 几方都打包了 OpenMP，必须先放这一行
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import jieba.analyse
import torch
from transformers import PegasusForConditionalGeneration

# tokenizers_pegasus 跟本模块同级，import 时假定 src/ 已在 sys.path 上
from tokenizers_pegasus import PegasusTokenizer
from summarize import (
    chunk_by_chars, keywords_for, extractive_summary,
)  # 复用切块、关键词、抽取式正文

DEFAULT_MODEL_DIR = Path("models/Randeng-Pegasus-238M-Summary-Chinese")
_CACHE: dict[str, object] = {}


# 段首语气连词（按长度降序，避免 "好" 先匹配吃掉 "好接下来" 的 "接下来"）
# "所以" 出现 39 次但语义重要（因果连接），保留
LEAD_FILLERS = (
    "好接下来", "好那么", "那接下来", "好的", "好那",
    "好", "那么", "接下来", "然后",
)

# 段尾语气词
TAIL_FILLERS = ("对不对", "是不是", "对吧", "是吧", "好吗", "嘛", "呢", "哈")

# 整段只剩这些视为噪音，整段丢
DROP_WHOLE = {"好", "嗯", "呃", "接下来", "然后", "那么", "也就是"}

# Pegasus headline 末尾如果停在这些连接词上，意味着被 max_length 截断了，删掉它们
# 例如："mac 真的前六个字节表示的是目的地址也就是要" -> "mac 真的前六个字节表示的是目的地址"
TRAILING_DROP = (
    "也就是要", "也就是说", "也就是", "我们知道", "我们说过", "比如说",
    "因为", "所以", "并且", "或者", "这个", "那个", "这种", "那种",
    "对吧", "对不对",
)

# Pegasus 在数字密集 chunk（如 PPP 协议讲 01111110 这种二进制串、字节数）上偶发
# token 重复："关于 ppp 协议的数字数字" / "字节字节" 等占位词二连重复。
# no_repeat_ngram_size=3 阻不了 2-gram 重复。post-clean 直接 dedup 这些已知占位词。
import re as _re
_HEADLINE_REPEAT_DEDUP = _re.compile(
    "(?P<t>数字|字节|字段|字符|协议|信号|信息|比特|地址|时间|时候|"
    "地方|内容|名字|节点|标志|数据|系统|对象|方法|函数)(?P=t)+"
)

_STRIP_CHARS = " ,，、"


def _clean_segment(text: str) -> str:
    t = text.strip()
    if not t:
        return ""
    # 段首：循环剥离，因为可能连续出现 "好那么所以..."
    changed = True
    while changed:
        changed = False
        for f in LEAD_FILLERS:
            if t.startswith(f) and len(t) > len(f):
                t = t[len(f):].lstrip(_STRIP_CHARS)
                changed = True
                break
    # 段尾
    for f in TAIL_FILLERS:
        if t.endswith(f):
            t = t[:-len(f)].rstrip(_STRIP_CHARS)
            break
    return t


def _is_chapter_title_copy(title: str, member_headlines: list[str]) -> bool:
    """检测 Pegasus 层次化摘要是否退化为"复制其中一段 headline"。

    现象：把 N 个 chunk headlines 拼起来再喂 Pegasus 生成章标题时，输入太短
    (<100 字) 时 Pegasus-238M 倾向直接抄一段 headline 而非综合。
    例：p39 章 3 含 chunk 4 "划分vlan的三种方式" + chunk 5 "每个节点都会有
    自己独一无二的mac 地址"，Pegasus 输出后者作为章标题，未综合。

    判定：title 跟任一 member headline 满足下列之一即认为是 copy：
      (1) 一方完整包含另一方（substring）
      (2) 共同前缀占短者长度 ≥ 0.85

    阈值 0.85 来自王道 OS 章 2 的反例校准：Pegasus 把"如何避免饥饿?"综合成
    "如何避免死锁?"（只改 2 字但意义不同），前缀重合 8/13=0.62。0.6 误判
    为 copy，0.85 放行。同时仍能抓 p39 章 3 "每个节点都会有..." 完整 substring。
    """
    if not title or not member_headlines:
        return False
    for h in member_headlines:
        if not h or len(h) < 4:
            continue
        if title in h or h in title:
            return True
        short = min(len(title), len(h))
        lcp = 0
        while lcp < short and title[lcp] == h[lcp]:
            lcp += 1
        if lcp >= short * 0.85:
            return True
    return False


def _fallback_chapter_title(member_headlines: list[str],
                            max_len: int = 30) -> str:
    """章标题 fallback：把章内前 2 段 headline 拼接，去掉互相包含的冗余，
    截到 max_len。比 "Pegasus 复制单段" 更能体现章节跨度。"""
    valid = [h.strip() for h in member_headlines if h and h.strip()]
    if not valid:
        return ""
    if len(valid) == 1:
        return valid[0][:max_len]
    a, b = valid[0], valid[1]
    if a in b:
        return b[:max_len]
    if b in a:
        return a[:max_len]
    combined = f"{a}·{b}"
    return combined[:max_len]


# 章标题名词化 rewrite：用户路线图阶段 1 子任务 C。
# 目标：把 Pegasus / fallback 输出的 verbal-style 章标题改写成名词性"知识点名称"。
# 例：「如何避免死锁?」→「死锁避免」，「我们轻我们向滑滑滑」→ 删退化前缀，
# 「一个空的集合字典」→「集合与字典」。
_LEADING_VERBAL_PREFIXES = (
    # 第一人称 / 第二人称起头（章标题不该带）
    "我是", "我们是", "我", "我们", "你是", "你们是", "你", "你们",
    "今天", "刚才", "刚刚", "现在", "首先",
    # 单字虚词
    "这", "那",
)
# "如何 X" / "怎么 X" / "为什么 X" → 直接剥前缀（X 本身已是名词短语）
_LEADING_QUESTION_WORDS = ("如何", "怎么", "怎样", "为什么", "为啥", "什么")
# 量词起头："一个 X" / "一种 X" → 剥量词
_LEADING_QUANTIFIERS = ("一个", "一种", "一些", "一类", "一组",
                        "几个", "多个", "若干", "某个", "每个")
# 章标题尾的疑问 / 语气标点
_TRAILING_PUNCT_NOMINAL = "?？!！。.,，;；:：、 "


def nominalize_title(title: str, max_len: int = 30) -> str:
    """rule-based 章标题名词化。

    多轮剥离：boilerplate (主题:/标题: 等) / 句首 verbal marker / 疑问词 / 量词；
    末尾问号 / 句号。剥到不再变化为止。保守不动正文（剥前缀不改后接名词短语）。
    完全无规则匹配时原样返回。
    """
    if not title:
        return title
    t = title.strip().strip(_TRAILING_PUNCT_NOMINAL)
    # 先剥 boilerplate (Pegasus 新闻训练 LCSTS 带来的 "主题:" 等)
    for f in _HEADLINE_LEADING_BOILERPLATE:
        if t.startswith(f) and len(t) > len(f):
            t = t[len(f):].lstrip(" ,，、")
            break
    changed = True
    while changed:
        changed = False
        # 句首 verbal
        for f in _LEADING_VERBAL_PREFIXES:
            if t.startswith(f) and len(t) > len(f):
                t = t[len(f):].lstrip(" ,，、的")
                changed = True
                break
        if changed:
            continue
        # 句首疑问词
        for q in _LEADING_QUESTION_WORDS:
            if t.startswith(q) and len(t) > len(q):
                t = t[len(q):].lstrip(" ,，、的")
                changed = True
                break
        if changed:
            continue
        # 句首量词
        for q in _LEADING_QUANTIFIERS:
            if t.startswith(q) and len(t) > len(q):
                t = t[len(q):].lstrip(" ,，、的")
                changed = True
                break
    t = t.strip(_TRAILING_PUNCT_NOMINAL)
    if not t:
        return title  # 全被剥光了，保守 fallback 原 title
    if len(t) > max_len:
        t = t[:max_len].rstrip(_TRAILING_PUNCT_NOMINAL)
    return t


# Pegasus headline 起头有时带 "主题:" / "标题:" 等 boilerplate（受 LCSTS 新闻
# 训练数据影响 — 新闻摘要里常带 "标题:..."）。这是 Pegasus 通用模式，与讲师
# 风格无关，所有视频都该剥。
_HEADLINE_LEADING_BOILERPLATE = (
    "主题:", "主题：", "标题:", "标题：", "话题:", "话题：",
    "本节:", "本节：", "本章:", "本章：", "讨论:", "讨论：",
    "内容:", "内容：", "导语:", "导语：",
)


def post_clean_headline(headline: str) -> str:
    """对 Pegasus 输出做清洗：剥首部 boilerplate ("主题:" 等)，剥末尾悬空连接词，
    去重复占位词（"数字数字"→"数字"）。"""
    t = headline.strip()
    # 首部 boilerplate
    for f in _HEADLINE_LEADING_BOILERPLATE:
        if t.startswith(f) and len(t) > len(f):
            t = t[len(f):].lstrip(" ,，、")
            break
    # 重复占位词缩为单次（Pegasus 在数字/术语密集 chunk 上偶发的退化）
    t = _HEADLINE_REPEAT_DEDUP.sub(r"\g<t>", t)
    t = t.rstrip("，。,.;；:：、 ")
    # 末尾悬空连接词（循环剥，可能连续多个）
    changed = True
    while changed:
        changed = False
        for f in TRAILING_DROP:
            if t.endswith(f) and len(t) > len(f):
                t = t[:-len(f)].rstrip("，。,.;；:：、 ")
                changed = True
                break
    return t or headline.strip()


def trim_topic_outliers(chunk_text: str, tail_window: int = 3,
                        drop_threshold: float = 0.85,
                        min_segs: int = 8,
                        min_tail_chars: int = 20) -> str:
    """检测 chunk 末尾"主题漂移"——保守版：只看尾部固定窗，整体截或不截。

    动机：TextTiling chunker 切点可能把"上一段尾巴"拼到当前 chunk 开头/末尾。
    case：ClaudeCode chunks #2 主体讲"回滚功能"，但末尾混入"如何手动打开 CNB"的
    下一段开头 → Pegasus 输出 "claude code 自动进入计划模式"（rating 2/5）

    保守策略——只看最后 tail_window 段，跟"主体（前面所有段）"比较：
    - 末尾几段总字数 < min_tail_chars：太短不可靠，不截
    - 关键词集合任一为空：不可靠，不截
    - 末尾窗口 Jaccard 距离 ≥ threshold：截掉，否则保留

    早期版本太激进（每段单独判 → 把"哈哈哈"等短语气词误判孤儿，连带截掉真主体）。
    此版本只截"明显成块的尾巴"，宁可不救也不误伤。

    只用于喂 Pegasus 的版本，原 chunk text 在 md 里仍是完整的。
    """
    segs = [s for s in chunk_text.split("\n") if s.strip()]
    if len(segs) < min_segs:
        return chunk_text
    body_segs = segs[:-tail_window]
    tail_segs = segs[-tail_window:]
    tail_total = sum(len(s) for s in tail_segs)
    if tail_total < min_tail_chars:
        return chunk_text  # 末尾窗口太短不可靠

    body_kw = set(jieba.analyse.extract_tags("".join(body_segs), topK=10))
    tail_kw = set(jieba.analyse.extract_tags("".join(tail_segs), topK=8))
    if not body_kw or not tail_kw:
        return chunk_text
    jac_dist = 1.0 - len(body_kw & tail_kw) / max(len(body_kw | tail_kw), 1)
    if jac_dist >= drop_threshold:
        return "\n".join(body_segs)
    return chunk_text


def clean_for_summary(chunk_text: str) -> str:
    """对 chunk 内每个 segment 做口头禅清洗，再拼回（仅用于喂神经摘要，
    原文 chunk text 仍保留以便 md 里展示）。还做 chunk-level 主题漂移截尾。

    segments 之间用空格分隔（不是 ""）：英文 ASR 跨 segment 的 "want" + "to"
    无分隔会黏成 "wantto"，下游 jieba 当一个 token 提取到 keywords 里。中文段
    多空格也无负面影响（jieba 中文分词不依赖空格）。
    """
    # 先做 chunk 边界 cleaning（截掉末尾孤儿段）
    trimmed = trim_topic_outliers(chunk_text)
    cleaned = []
    for seg in trimmed.split("\n"):
        c = _clean_segment(seg)
        if not c or c in DROP_WHOLE:
            continue
        cleaned.append(c)
    return " ".join(cleaned)


def load_model(model_dir: Path | str = DEFAULT_MODEL_DIR,
               device: str | None = None,
               dtype: torch.dtype | None = None):
    """加载并缓存模型/分词器。重复调用零成本。"""
    key = str(model_dir)
    if key in _CACHE:
        return _CACHE[key]

    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    dtype = dtype or (torch.float16 if device == "cuda" else torch.float32)

    print(f"      [pegasus] loading from {model_dir} (device={device}, dtype={dtype}) ...")
    tokenizer = PegasusTokenizer.from_pretrained(str(model_dir))
    model = PegasusForConditionalGeneration.from_pretrained(
        str(model_dir), torch_dtype=dtype
    ).to(device)
    model.eval()
    _CACHE[key] = (model, tokenizer, device)
    return _CACHE[key]


def summarize_text(text: str, *, max_input: int = 1024,
                   max_summary: int = 48, num_beams: int = 4,
                   length_penalty: float = 0.8) -> str:
    """生成段落标题。Pegasus-238M-Summary-Chinese 在 LCSTS 等新闻数据集上微调，
    最自然的输出是 10-25 字的"标题"——强制让它写长摘要会触发新闻 boilerplate 漂移。
    所以这里定位为"段落小标题"。"""
    model, tokenizer, device = load_model()
    inputs = tokenizer(text, max_length=max_input, truncation=True,
                       return_tensors="pt").to(device)
    with torch.no_grad():
        ids = model.generate(
            inputs["input_ids"],
            attention_mask=inputs.get("attention_mask"),
            max_length=max_summary,
            num_beams=num_beams,
            length_penalty=length_penalty,
            no_repeat_ngram_size=3,
            early_stopping=True,
        )
    return tokenizer.batch_decode(ids, skip_special_tokens=True,
                                  clean_up_tokenization_spaces=False)[0].strip()


def summarize_chapter(chapter_chunks: list[dict], max_headlines: int = 5) -> str:
    """生成章节级概述（用户路线图阶段 1 子任务 B）。

    回答"本章按知识点讲了什么"——把章内各 chunk 的 nominalized headline 拼接。

    放弃路径：原计划用 Pegasus-238M 综合章内 cleaned text 生成 abstractive prose，
    实测在 Python 教学视频章 3 (函数/方法) hallucinate 出 "excel 教程"（讲师用
    Excel 函数做类比触发 LCSTS 训练分布的新闻 boilerplate）。Pegasus 在长输入
    （cleaned text > 500 字）+ 短输出上稳定性差，且 num_beams=4 加重 boilerplate。
    放弃 Pegasus abstractive，改用 chunk headlines 拼接：每个 chunk 的 headline
    已是 Pegasus 在短 context（< 800 字）上生成的 abstractive 知识点，拼起来即
    "本章按知识点的清单"——更可靠、零 hallucination 风险。

    nominalize 各 headline 去 verbal noise，max_headlines 限制长度避免长章 chapter
    overview 过长（5 个就 80-100 字够 prose 风格阅读）。
    """
    headlines: list[str] = []
    for c in chapter_chunks:
        h = (c.get("headline") or "").strip()
        if h:
            headlines.append(nominalize_title(h))
        if len(headlines) >= max_headlines:
            break
    # 去重（相邻 headline 含义重复时 dedupe，避免 Pegasus 重复输出污染）
    seen: set[str] = set()
    deduped: list[str] = []
    for h in headlines:
        key = h[:10]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(h)
    if not deduped:
        return ""
    return "本章涵盖 " + " · ".join(deduped)


def summarize_chunks_no_headline(chunks: Iterable[dict],
                                  target_ratio: float = 0.25,
                                  lang: str = "zh") -> list[dict]:
    """跳过 Pegasus，仅 jieba 抽取式摘要 + 关键词。headline 留空，由下游 LLM 生成。
    用于 --llm-chapters 模式：Pegasus 输出反正会被 Qwen `generate_headlines` 覆盖，
    直接跳过节省 ~30s + ~1GB VRAM。"""
    out = []
    chunks = list(chunks)
    for i, c in enumerate(chunks, 1):
        body = clean_for_summary(c["text"])
        summary = extractive_summary(c["text"], target_ratio=target_ratio, lang=lang)
        out.append({
            "start": c["start"],
            "end": c["end"],
            "text": c["text"],
            "headline": "",  # 由 Qwen `generate_headlines` 填充
            "summary": summary,
            "keywords": keywords_for(body),
            "segments": c.get("segments", []),
        })
        print(f"      [chunk] {i}/{len(chunks)} -> summary {len(summary)} chars "
              f"(Pegasus skipped, headline 等 Qwen 生成)")
    return out


def summarize_chunks(chunks: Iterable[dict], target_ratio: float = 0.25,
                     lang: str = "zh", **gen_kwargs) -> list[dict]:
    """Pegasus 出"段落小标题"（headline），jieba 抽取式补"正文摘要"（summary）。
    短标题 + 抽取式正文的组合在 ASR 转写场景下比单独神经摘要更稳。"""
    out = []
    chunks = list(chunks)
    load_model()  # 提前装一次模型，避免在第一段循环里阻塞输出
    for i, c in enumerate(chunks, 1):
        body = clean_for_summary(c["text"])
        headline = post_clean_headline(summarize_text(body, **gen_kwargs))
        summary = extractive_summary(c["text"], target_ratio=target_ratio, lang=lang)
        out.append({
            "start": c["start"],
            "end": c["end"],
            "text": c["text"],
            "headline": headline,
            "summary": summary,
            "keywords": keywords_for(body),
            "segments": c.get("segments", []),
        })
        print(f"      [pegasus] {i}/{len(chunks)} -> {len(headline)} chars headline")
    return out


if __name__ == "__main__":
    import sys
    sample = sys.stdin.read() if not sys.stdin.isatty() else (
        "在北京冬奥会自由式滑雪女子坡面障碍技巧决赛中，中国选手谷爱凌夺得银牌。"
    )
    print(summarize_text(sample))
