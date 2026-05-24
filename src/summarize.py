"""段落摘要。

Baseline 用抽取式（无需下载大模型即可端到端跑通）；
Week 2 升级路径：换成 mT5 / Pegasus / Qwen 微调的生成式摘要。
"""
from __future__ import annotations

import re
from typing import Iterable

import jieba.analyse


# faster-whisper 中文输出几乎只有 ASCII 逗号、没有句号，所以这里把所有标点
# 以及 segment 之间的换行（VAD 切出的天然停顿）都当切点
SENT_SPLIT = re.compile(r"(?<=[。！？!?,;，；、])|\n+")

# 切完后过短的片段（如 "对吧"、"好"）回贴到前一句，避免噪声句
MIN_FRAGMENT_CHARS = 5


def chunk_by_chars(segments: list[dict], chunk_chars: int = 800) -> list[dict]:
    """按累计字符数把 ASR segment 聚合成 chunk，chunk 内用换行保留 segment 边界。
    保留换行的目的：VAD 切出来的 segment 边界是天然的句子停顿，能补救 ASR 缺标点。
    chunk["segments"] 保留原 segment 列表（含 confidence），用于 md 低置信标记。"""
    chunks: list[dict] = []
    buf_parts: list[str] = []
    buf_segs: list[dict] = []
    buf_len, buf_start, buf_end = 0, None, None

    def flush():
        if buf_parts:
            chunks.append({"start": buf_start, "end": buf_end,
                           "text": "\n".join(buf_parts),
                           "segments": list(buf_segs)})

    for seg in segments:
        seg_text = seg["text"].strip()
        if not seg_text:
            continue
        if buf_start is None:
            buf_start = seg["start"]
        if buf_len + len(seg_text) > chunk_chars and buf_parts:
            flush()
            buf_parts, buf_segs, buf_len, buf_start = [], [], 0, seg["start"]
        buf_parts.append(seg_text)
        buf_segs.append(seg)
        buf_len += len(seg_text)
        buf_end = seg["end"]

    flush()
    return chunks


def chunk_by_texttile(segments: list[dict], target_chunk_chars: int = 800,
                      window_chars: int = 400,
                      min_chunk_chars: int | None = None,
                      return_debug: bool = False):
    """语义 chunker：在 segment 间隙跑滑动窗 jieba keyword Jaccard 距离，
    在 "语义跳变最强处" 切 chunk。比 chunk_by_chars 的字符硬切更贴 gold 章节边界。

    动机：EDA 表明 PPT 教学视频里 segment 间几乎没静音 gap（faster-whisper 的 VAD
    已经把停顿吃掉了），段尾标点也几乎全失（990 段里 0 个）。所以 VAD/标点信号都
    用不上；唯一可靠的切分信号是 segment 文本的语义连续性。

    算法（TextTiling 风格）：
    1. 预算每段 jieba 关键词 set；
    2. 在每个相邻 segment 间隙 i，构造左右滑动窗（左右各累计字符 ≤ window_chars
       的相邻 segments），计算左右关键词的 Jaccard 距离 dists[i]；
    3. depth score = dists[i] - 0.5*(dists[i-1]+dists[i+1])，找 local peaks；
    4. 目标切点数 ≈ total_chars / target_chunk_chars - 1；按 depth 降序贪心选切点，
       两两间最小字符距离 ≥ min_chunk_chars，避免聚簇。

    target_chunk_chars 控制 chunk 数量（不是硬上限），window_chars 控制语义窗大小：
    窗太小关键词不稳，窗太大会把真实跳变平滑掉。
    """
    import jieba.analyse

    if min_chunk_chars is None:
        min_chunk_chars = max(200, target_chunk_chars // 2)

    segs = [s for s in segments if s.get("text", "").strip()]
    n = len(segs)
    if n <= 2:
        chunks = chunk_by_chars(segs, chunk_chars=target_chunk_chars)
        return (chunks, {}) if return_debug else chunks

    keys_per_seg = [set(jieba.analyse.extract_tags(s["text"], topK=8))
                    for s in segs]
    char_lens = [len(s["text"]) for s in segs]
    total_chars = sum(char_lens)
    # 累积字符：cum[i] = sum(char_lens[:i])；segs[i] 之后的切点在字符 cum[i+1] 处
    cum = [0]
    for c in char_lens:
        cum.append(cum[-1] + c)

    def jaccard(a: set, b: set) -> float:
        if not a and not b:
            return 0.0
        return 1.0 - len(a & b) / len(a | b)

    dists: list[float] = []
    for i in range(n - 1):  # gap i 在 segs[i] 和 segs[i+1] 之间
        # 左窗：从 i 向左累计 ≤ window_chars
        l, left_chars = i, 0
        while l >= 0 and left_chars < window_chars:
            left_chars += char_lens[l]
            l -= 1
        l_start = l + 1
        # 右窗：从 i+1 向右累计 ≤ window_chars
        r, right_chars = i + 1, 0
        while r < n and right_chars < window_chars:
            right_chars += char_lens[r]
            r += 1
        r_end = r
        L: set = set().union(*keys_per_seg[l_start:i + 1])
        R: set = set().union(*keys_per_seg[i + 1:r_end])
        dists.append(jaccard(L, R))

    depths: list[float] = []
    for i in range(len(dists)):
        left = dists[i - 1] if i > 0 else dists[i]
        right = dists[i + 1] if i < len(dists) - 1 else dists[i]
        depths.append(dists[i] - 0.5 * (left + right))

    target_breaks = max(1, total_chars // target_chunk_chars - 1)
    candidates = sorted(range(len(depths)), key=lambda i: -depths[i])
    chosen: list[int] = []
    chosen_positions: list[int] = []  # 字符位置
    for idx in candidates:
        if len(chosen) >= target_breaks:
            break
        pos = cum[idx + 1]
        if pos < min_chunk_chars or pos > total_chars - min_chunk_chars:
            continue
        if any(abs(pos - p) < min_chunk_chars for p in chosen_positions):
            continue
        chosen.append(idx)
        chosen_positions.append(pos)
    chosen.sort()

    chunks: list[dict] = []
    last = 0
    for idx in chosen:
        buf = segs[last:idx + 1]
        chunks.append({"start": buf[0]["start"], "end": buf[-1]["end"],
                       "text": "\n".join(s["text"] for s in buf),
                       "segments": list(buf)})
        last = idx + 1
    if last < n:
        buf = segs[last:]
        chunks.append({"start": buf[0]["start"], "end": buf[-1]["end"],
                       "text": "\n".join(s["text"] for s in buf),
                       "segments": list(buf)})

    if return_debug:
        debug = {"dists": dists, "depths": depths, "boundaries": chosen,
                 "total_chars": total_chars, "target_breaks": target_breaks}
        return chunks, debug
    return chunks


def split_oversize_chunks(chunks: list[dict],
                          max_dur_sec: float = 120.0,
                          min_split_chars: int = 400) -> tuple[list[dict], list[dict]]:
    """硬切后处理：把 duration > max_dur_sec 且 text 长度 >= min_split_chars 的
    chunk 按时间中点（最近 segment 边界）切成 2 份。while loop 反复跑，直到所有
    chunk 都满足约束或无法再切（segments 数 < 2 / 字符不够）。

    动机：texttile chunker 在 vlog/talk 类视频上不敏感（口语化、关键词稀疏，
    Jaccard 跳变信号弱），常出现 200s+ 的单 chunk 含多个独立场景。硬切兜底
    在所有 category 上通用，不依赖 category 标签。

    Args:
      chunks: chunker 输出，每个 dict 含 {start, end, text, segments[]}
      max_dur_sec: 触发切刀的时长阈值。120s（2 分钟）够大不误伤教学，够小
        能把 vlog 的多场景段切散
      min_split_chars: 触发切刀的字符阈值。短而长（如纯静音/重复段）不切
    Returns:
      (new_chunks, split_log) — split_log 是切刀诊断列表
    """
    result = list(chunks)
    log: list[dict] = []
    # 用 chunk 内容指纹（start 取整 + 字符长度）记 skipped。切完 chunk 会变成两个
    # 新指纹，所以原指纹自然失效；只有真正不可切的 chunk 才会持续命中 skipped
    skipped: set[tuple[float, int]] = set()

    def _fp(c: dict) -> tuple[float, int]:
        return (round((c.get("start") or 0), 2), len(c.get("text", "") or ""))

    # 防御无限循环
    for _ in range(100):
        # 找第一个 oversize 且未 skipped 的 chunk
        target_idx = -1
        for i, c in enumerate(result):
            if _fp(c) in skipped:
                continue
            dur = (c.get("end", 0) or 0) - (c.get("start", 0) or 0)
            text = c.get("text", "") or ""
            segs = c.get("segments", []) or []
            if dur > max_dur_sec and len(text) >= min_split_chars and len(segs) >= 2:
                target_idx = i
                break
        if target_idx < 0:
            break
        c = result[target_idx]
        segs = c["segments"]
        # 找最接近时间中点的 segment 边界（i 处切，左边 segs[:i+1]，右边 segs[i+1:]）
        midpoint = (c["start"] + c["end"]) / 2
        best_i, best_diff = 0, float("inf")
        for i in range(len(segs) - 1):
            boundary = (segs[i].get("end") or 0)
            diff = abs(boundary - midpoint)
            if diff < best_diff:
                best_diff = diff
                best_i = i
        left_segs = segs[:best_i + 1]
        right_segs = segs[best_i + 1:]
        def _seg_chars(ss): return sum(len((s.get("text") or "").strip()) for s in ss)
        if _seg_chars(left_segs) < 80 or _seg_chars(right_segs) < 80:
            log.append({"idx": target_idx, "skipped": True,
                        "reason": "split too unbalanced",
                        "dur": round(c["end"] - c["start"], 1)})
            skipped.add(_fp(c))
            continue
        def _build(segs_):
            text = "\n".join(((s.get("text") or "").strip()) for s in segs_ if (s.get("text") or "").strip())
            return {
                "start": segs_[0].get("start"),
                "end": segs_[-1].get("end"),
                "text": text,
                "segments": list(segs_),
            }
        left = _build(left_segs)
        right = _build(right_segs)
        log.append({
            "idx": target_idx,
            "orig_dur": round(c["end"] - c["start"], 1),
            "orig_chars": len(c.get("text", "")),
            "split_at": round(segs[best_i].get("end") or 0, 1),
            "left_dur": round(left["end"] - left["start"], 1),
            "right_dur": round(right["end"] - right["start"], 1),
        })
        result = result[:target_idx] + [left, right] + result[target_idx + 1:]
    return result, log


def _split_sentences(text: str) -> list[str]:
    """按任意中英文标点切句，再把过短的碎片回贴到前一句。
    应对：口语 ASR 转写经常整段只有 ASCII 逗号，没有句号。"""
    parts = [p.strip() for p in SENT_SPLIT.split(text) if p.strip()]
    merged: list[str] = []
    for p in parts:
        if merged and len(p) < MIN_FRAGMENT_CHARS:
            merged[-1] += p
        else:
            merged.append(p)
    return merged


_DEDUPE_STRIP_RE = re.compile(r"[\d，。、；：！？,.;:!?\s\-—…\"'""''（）()【】\[\]《》<>]+")


def _dedupe_normalize(s: str) -> str:
    """去年份/标点/空白后的规范形，用于"几乎相同"判定。"""
    return _DEDUPE_STRIP_RE.sub("", s)


def _char_bigrams(s: str) -> set[str]:
    if len(s) < 2:
        return {s} if s else set()
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def extractive_summary(text: str, target_ratio: float = 0.25,
                       min_sentences: int = 2, max_sentences: int = 8,
                       lang: str = "zh") -> str:
    """抽取式摘要：按字数比例保留 top-k 句，而非固定句数。
    target_ratio = 0.25 表示摘要长度约为原文 25%。
    lang='en' 时拼接符用 ". "（中文用 "。"），避免英文文本里混入全角句号。"""
    sents = _split_sentences(text)
    if not sents:
        return ""

    target_chars = max(1, int(len(text) * target_ratio))
    keywords = dict(jieba.analyse.extract_tags(text, topK=20, withWeight=True))

    def score(s: str) -> float:
        if not keywords:
            return 1.0 / max(len(s), 1)
        return sum(w for kw, w in keywords.items() if kw in s) / max(len(s), 1) ** 0.5

    ranked = sorted(enumerate(sents), key=lambda x: score(x[1]), reverse=True)

    kept: list[int] = []
    kept_norms: list[str] = []
    kept_bigrams: list[set[str]] = []
    acc = 0
    for idx, sent in ranked:
        if len(kept) >= max_sentences:
            break
        norm = _dedupe_normalize(sent)
        if not norm:
            continue
        # 防"2021年实验室升级…" / "2020年实验室升级…" 这种只差数字的近重复
        if norm in kept_norms:
            continue
        bg = _char_bigrams(norm)
        # 防"百度将深度学习框架开源" / "2016年百度将深度学习框架开源"这种包含/近似重复
        if any(_jaccard(bg, kb) >= 0.75 for kb in kept_bigrams):
            continue
        kept.append(idx)
        kept_norms.append(norm)
        kept_bigrams.append(bg)
        acc += len(sent)
        if acc >= target_chars and len(kept) >= min_sentences:
            break

    keep_idx = sorted(kept)
    picked = [sents[i].rstrip("。！？!?.,;，；、") for i in keep_idx]
    if lang == "en":
        return ". ".join(picked) + "."
    return "。".join(picked) + "。"


def keywords_for(text: str, k: int = 6) -> list[str]:
    # ASR 按 segment 分行（每段 \n 间隔），跨行的英文词 jieba 会粘成一个 token
    # （"want\nto" → "wantto"、"you\ncan" → "youcan"）。BV1GofdBZEW7 实测发现
    # 顶部摘要卡出 youcan/wantto/yourrules 等 50+ 合词。统一把空白压成单空格
    # 再喂 jieba，确保英文 token 切对；中文段无影响（jieba 中文分词不依赖空格）。
    normalized = " ".join(text.split())
    return jieba.analyse.extract_tags(normalized, topK=k)


def summarize_chunks(chunks: Iterable[dict], target_ratio: float = 0.25,
                     lang: str = "zh") -> list[dict]:
    out = []
    for c in chunks:
        out.append({
            "start": c["start"],
            "end": c["end"],
            "text": c["text"],
            "summary": extractive_summary(c["text"], target_ratio=target_ratio, lang=lang),
            "keywords": keywords_for(c["text"]),
            "segments": c.get("segments", []),
        })
    return out


def format_seconds(s: float) -> str:
    s = int(s)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


# jieba TF-IDF 经常把这些虚词/口语词当作 keyword 抽出来，
# 但放进"术语表"会污染观感。把它们从术语候选里剔除。
_GLOSSARY_STOPWORDS = {
    "我们", "你们", "他们", "这里", "那里", "这个", "那个", "这样", "那样",
    "这种", "那种", "这边", "那边", "这次", "那次", "可以", "可能", "应该",
    "需要", "然后", "所以", "因为", "如果", "但是", "就是", "还是", "或者",
    "比如", "比如说", "其实", "确实", "真的", "感觉", "觉得", "知道", "看到",
    "看看", "听到", "听听", "做做", "进行", "一下", "一些", "一点", "一直",
    "一样", "一定", "一般", "什么", "怎么", "怎样", "为什么", "东西",
    "时候", "地方", "方面", "方式", "情况", "事情", "问题", "现在",
    "刚才", "已经", "正在", "继续", "开始", "结束", "完成", "目前",
    "首先", "其次", "最后", "总之", "另外", "此外", "当然", "不过",
    "对吧", "好的", "好吧", "okay", "ok", "yes", "no",
    "当中", "里面", "里头", "下面", "上面", "前面", "后面",  # 讲师口头禅"X 当中"
    "之前", "之后", "之中", "之内", "之外",
    "这片", "那片", "这块", "那块", "这部分", "那部分",  # "这片区域" / "这块/那块"
    "这点", "那点", "这条", "那条", "这种", "那种",  # OS p45 实测"这片"上榜
    "使用", "选择", "输入", "点击", "回车", "进入", "退出", "打开",
    "查看", "保存", "发送", "等待", "运行", "执行",
    "同一个", "另一个", "每一个", "任何一个", "其中一个", "下一个", "上一个",
    "一些", "一种", "一类", "一组", "几个", "多个", "若干",
    "一个", "各个", "每个", "各种", "各类", "各位", "整个",  # OS p49 实测"各个/一个"上榜
    # 英文 stopwords (jieba 对英文按 ASCII space 切，会把常用词当 token；
    # 英文视频里 like/my/news/it/is/a/the 等会上榜。FwOTs4UxQS4 实测)
    "the", "and", "or", "but", "for", "with", "from", "into", "onto",
    "this", "that", "these", "those", "such", "there", "here",
    "is", "are", "was", "were", "be", "been", "being", "am",
    "do", "does", "did", "done", "doing",
    "have", "has", "had", "having",
    "will", "would", "shall", "should", "can", "could", "may", "might", "must",
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
    "my", "your", "his", "its", "our", "their", "mine", "yours", "ours",
    "what", "which", "who", "whom", "whose", "when", "where", "why", "how",
    "if", "then", "else", "than", "as", "so", "because", "though", "although",
    "of", "in", "on", "at", "to", "by", "up", "out", "off", "down",
    "all", "any", "some", "no", "not", "only", "very", "too", "just",
    "like", "really", "actually", "basically", "literally",
    "now", "then", "today", "yesterday", "tomorrow",
    "one", "two", "three", "first", "second", "third", "last", "next",
    "go", "going", "get", "got", "make", "made", "take", "took", "say", "said",
    "see", "saw", "use", "used", "want", "wanted", "know", "knew", "think", "thought",
    # 撇号缩写残片（jieba 按 ASCII 切分把 "I'll" → "I" + "ll"，"you're" → "you" + "re"）
    "ll", "re", "ve", "s", "d", "m", "t", "n", "em",
    # 高频英文动词/动名词（EH5jx5qPabU 实测上榜：open/click/build/add）
    "open", "close", "opened", "closed",
    "click", "clicks", "clicked", "clicking",
    "build", "built", "building", "builds",
    "add", "added", "adding", "adds",
    "remove", "removed", "removing", "removes",
    "delete", "deleted", "deleting", "deletes",
    "create", "created", "creating", "creates",
    "update", "updated", "updating", "updates",
    "save", "saved", "saving", "saves",
    "load", "loaded", "loading", "loads",
    "show", "shown", "showed", "showing",
    "tell", "told", "telling",
    "try", "tried", "trying", "tries",
    "find", "found", "finding",
    "let", "lets", "letting",
    "come", "came", "coming",
    "look", "looked", "looking", "looks",
    "feel", "felt", "feeling", "feels",
    "seem", "seemed", "seeming", "seems",
    "become", "became", "becoming",
    "put", "puts", "putting",
    "set", "sets", "setting",
    "mean", "meant", "meaning", "means",
    "call", "called", "calling", "calls",
    "work", "worked", "working", "works",
    "run", "ran", "running", "runs",
    "start", "started", "starting", "starts",
    "stop", "stopped", "stopping", "stops",
    "talk", "talked", "talking",
    "watch", "watched", "watching",
    "help", "helped", "helping", "helps",
    "need", "needs", "needed", "needing",
    # 高频名词性虚词
    "lot", "lots", "bit", "kind", "sort", "way", "ways", "thing", "things",
    "stuff", "guy", "guys", "people", "person", "part", "parts",
    # 高频形容词/副词
    "new", "old", "good", "bad", "big", "small", "great", "nice",
    "right", "left", "easy", "hard", "different", "same", "similar",
    "much", "many", "few", "lots", "more", "less", "most", "least",
    "another", "other", "others", "whole", "single", "double",
    "definitely", "probably", "maybe", "perhaps", "likely",
}


# G4 (2026-05-24): 仅术语表过滤 generic 名词，**不喂给 jieba**。原因：jieba
# stopwords 同时影响 chunker keyword Jaccard → chunk 边界 → C2 派生 seed →
# segmenter LLM 输出（实测 p65 把 "信息/节点" 加进 jieba stopwords 后章数
# 从 4 跳到 7 + non_contiguous fail + fallback）。所以这些 generic 词只在
# `_is_stopword`（用于 glossary 候选过滤）时合并，jieba.analyse.extract_tags
# 仍用原 _GLOSSARY_STOPWORDS。
# 保留原则：领域专属术语（路由/链路/协议/报文/帧/包/端口/网关/进程/线程）
# 不在此列；只剔除跨域通用的"信息系统类"虚名词。
_GLOSSARY_EXTRA_NOISE = {
    "信息", "节点", "状态", "系统", "网络", "数据", "方法", "规则", "作用",
    "特点", "功能", "工作", "过程", "方式", "方面", "类型", "形式", "结构",
    "关系", "操作", "部分", "内容", "范围", "概念", "原理", "区域", "主干",
    "情况", "条件", "环境", "对象", "对比", "目的", "目标", "结果", "效果",
    "属性", "性质", "特征",
    "一台",  # p65 "我们说自治系统内的每一台路由器" → jieba 抽 "一台" 作 keyword
}


# 让 jieba.analyse.extract_tags 直接跳过 _GLOSSARY_STOPWORDS 里的虚词/口语词。
# 之前只在术语表/glossary 阶段过滤，但 chunker (chunk_by_texttile) 的 keyword
# Jaccard 距离和 chunk-level keywords 都直接用 extract_tags 输出，结果 "这个"
# "等于" "题目" 等虚词常常占 top-5，p85 keyword 渗漏就源于此。
# set_stop_words 影响 jieba 全局状态，本项目没有别的 jieba 用户，安全。
def _init_jieba_stopwords() -> None:
    import tempfile
    from pathlib import Path as _P
    sw_file = _P(tempfile.gettempdir()) / "notegen_jieba_stopwords.txt"
    sw_file.write_text("\n".join(sorted(_GLOSSARY_STOPWORDS)), encoding="utf-8")
    jieba.analyse.set_stop_words(str(sw_file))


_init_jieba_stopwords()


# 英文 keyword 过滤：纯小写 ≤2 字符的 token 不可能是术语（`ll`, `is`, `it` 等）。
# 但 `AI`/`ML`/`UI`/`API` 这种全大写专有缩写要保留——靠 isupper() 判定。
def _is_short_english_filler(kw: str) -> bool:
    if not kw or len(kw) > 2:
        return False
    if not all(c.isascii() and c.isalpha() for c in kw):
        return False
    return kw.islower()  # AI/ML/UI 等大写缩写不命中


# stopword 匹配做 case-insensitive：中英混 ASR 里 jieba 抽出来的英文 token
# 经常首字母大写（"Like"、"So"、"Different"），原 set 全 lowercase 漏掉它们
_GLOSSARY_STOPWORDS_LOWER: set[str] = set()  # lazy init，避免 import 时序问题


def _is_stopword(kw: str) -> bool:
    """大小写不敏感匹配 _GLOSSARY_STOPWORDS ∪ _GLOSSARY_EXTRA_NOISE。
    EXTRA_NOISE 只在术语表过滤生效，不喂给 jieba 全局 stopwords（避免影响 chunker）。"""
    global _GLOSSARY_STOPWORDS_LOWER
    if not _GLOSSARY_STOPWORDS_LOWER:
        _GLOSSARY_STOPWORDS_LOWER = {s.lower() for s in _GLOSSARY_STOPWORDS}
        _GLOSSARY_STOPWORDS_LOWER |= {s.lower() for s in _GLOSSARY_EXTRA_NOISE}
    return kw.lower() in _GLOSSARY_STOPWORDS_LOWER


def build_overview_keywords(summaries: list[dict], top_k: int = 8) -> list[str]:
    """跨段聚合关键词，按"在多少段出现"打分（document frequency），
    挑出全局核心关键词作为顶部摘要卡里的速览。

    同词大小写聚合（Agent / agent / agents 等）按 lowercase key 合并 df，
    显示时取该 lower key 下首次出现的原形（BV1S6kQBNEJq 实测顶部曾同时出
    'Agent · agent'，重复占位）。
    """
    df: dict[str, int] = {}                 # key = lowercased keyword
    display: dict[str, str] = {}            # lower key -> 首次出现的原形
    first_pos: dict[str, int] = {}          # lower key -> 首次出现的段 idx
    for i, item in enumerate(summaries):
        seen: set[str] = set()
        for kw in item.get("keywords", []) or []:
            if len(kw) < 2 or _is_stopword(kw):
                continue
            if kw.isdigit():  # OS p49 "12" 这种纯数字 token 不算术语
                continue
            if _is_short_english_filler(kw):  # 'll', 're', 've', 'is' 等撇号残片
                continue
            key = kw.lower()
            if key in seen:
                continue
            seen.add(key)
            df[key] = df.get(key, 0) + 1
            display.setdefault(key, kw)
            first_pos.setdefault(key, i)
    # df 相同时按"首次出现位置"靠前的优先（保留原顺序的可读性）
    ordered = sorted(df.items(), key=lambda kv: (-kv[1], first_pos.get(kv[0], 0)))
    return [display[k] for k, _ in ordered[:top_k]]


def _find_term_snippet(term: str, text: str, max_chars: int = 80) -> str:
    """从 chunk 文本中找首次包含 term 的句子（或片段），截到 max_chars。"""
    if not text:
        return ""
    for sent in _split_sentences(text):
        if term in sent:
            s = sent.strip()
            if len(s) > max_chars:
                s = s[:max_chars].rstrip() + "…"
            return s
    return ""


def build_glossary(summaries: list[dict], top_k: int = 15,
                   min_df: int | None = None) -> list[dict]:
    """术语表：跨段投票挑 top-K 显著术语，每个术语带首次出现段和上下文 snippet。

    筛选规则：
      - term 长度 ≥ 2 字
      - 不在停用词表里
      - 在 ≥ min_df 段出现，过滤"局部关键词"
      - 至少在某段的 keywords 列表里（说明 jieba TF-IDF 认为它对那段显著）

    min_df 自适应：n_chunks ≥ 8 时取 2（严格，过滤偶发词）；
    短视频 (<8 段) 关键词分布稀，强 df 过滤会让术语表退化为 0-3 条，所以放宽到 1。

    排序：按 df 降序，df 相同按首次出现位置靠前优先（更稳定可读）。
    """
    if min_df is None:
        min_df = 2 if len(summaries) >= 8 else 1
    df: dict[str, int] = {}
    first_idx: dict[str, int] = {}
    # G2: 例子标识符 (R1/R23/Net1/AS65000) 不是术语，是讲师举例的占位名
    # p65 实测术语表里 R1/R23/Net1 上榜挤掉真正术语
    # 规则：1-2 字符大写前缀 + 数字 (R1/R23/AS65000) 或 Net + 数字 (Net0/Net1)
    # 保留：IPv4/HTTP2/RFC1918/SHA256/BGP4 等 ≥3 字母前缀的真术语
    _example_label_re = re.compile(r"^[A-Z]{1,2}\d+$|^Net\d+$")
    for i, item in enumerate(summaries):
        for kw in set(item.get("keywords", []) or []):
            if len(kw) < 2 or _is_stopword(kw):
                continue
            if _is_short_english_filler(kw):
                continue
            if _example_label_re.match(kw):
                continue
            df[kw] = df.get(kw, 0) + 1
            first_idx.setdefault(kw, i)

    candidates = [(t, df[t]) for t in df if df[t] >= min_df]
    candidates.sort(key=lambda kv: (-kv[1], first_idx.get(kv[0], 0)))

    out: list[dict] = []
    for term, count in candidates[:top_k]:
        idx = first_idx.get(term, 0)
        ref = summaries[idx]
        snippet = _find_term_snippet(term, ref.get("text", ""))
        out.append({
            "term": term,
            "df": count,
            "first_idx": idx,
            "first_start": ref.get("start", 0),
            "snippet": snippet,
        })
    return out


def chapter_recap(chunk_texts: list[str], max_sentences: int = 2,
                  lang: str = "zh") -> str:
    """章节小结：把章内所有段文本拼起来跑抽取式，挑 1-2 句作 recap。
    去重：ASR 重复段（如王道 OS 的 chunk 11）可能让抽取式选到同义/同字句子，去掉。"""
    if not chunk_texts:
        return ""
    joined = "\n".join(chunk_texts)
    raw = extractive_summary(joined, target_ratio=0.08,
                             min_sentences=1, max_sentences=max_sentences + 1,
                             lang=lang)
    sep_re = r"[。.]" if lang == "en" else "。"
    end_punct = "." if lang == "en" else "。"
    joiner = ". " if lang == "en" else "。"
    parts = [p.strip() for p in re.split(sep_re, raw) if p.strip()]
    seen: set[str] = set()
    kept: list[str] = []
    for p in parts:
        key = p[:20]  # 用前 20 字作 dedup key，能抓 ASR 重复段
        if key in seen:
            continue
        seen.add(key)
        kept.append(p)
        if len(kept) >= max_sentences:
            break
    return joiner.join(kept) + end_punct if kept else ""


# 重难点标记（用户路线图阶段 1 子任务 D）。
# ⭐ 重点：chunk text 含定义 / 强调模式。讲师在教学视频里讲到关键概念时，倾向
#   用 "X 就是 / 即 / 所谓 / 注意 / 重点是 / 关键是 / 一定要" 等套话框 — 这套
#   regex 捕捉这些 trigger。
# 🎯 难点：chunk 内 ASR segment 平均 confidence 低于阈值。低 confidence 来自
#   术语密集 / 长句 / 口音含混 — 三种都对应"学生难理解"段。
_EMPHASIS_RE = __import__("re").compile(
    # 定义模式
    r"(?:就是|即(?:[^及])|所谓|意思是|定义为|定义是|表示|称为|称之为)"
    # 强调模式
    r"|(?:注意(?:[,，。!！]|$)|切记|重点(?:是|在|就是)|关键(?:是|在|就是|点)|核心(?:是|在|就是)"
    r"|强调|要点|别忘了|一定要|必须(?:要|得)|千万(?:别|不要)|记住)"
    # 形容词强调
    r"|(?:很重要|非常重要|尤其重要|至关重要|特别重要)"
)


def detect_emphasis_count(chunk_text: str) -> int:
    """统计 chunk 内强调/定义模式 trigger 数量。"""
    if not chunk_text:
        return 0
    return len(_EMPHASIS_RE.findall(chunk_text))


def detect_difficulty(chunk: dict, conf_threshold: float = 0.75,
                       min_low_segs: int = 2) -> bool:
    """难点检测：chunk 内 ASR confidence 低段 ≥ min_low_segs 视为难点。

    用"低段计数"而非"平均 confidence"：避免被 chunk 内一两段高 confidence 拉高
    平均拉走信号。教学视频里"难"通常是某几段术语密集/长句 confidence 低，其他
    段 confidence 正常 — 计数比 mean 更准。
    """
    segs = chunk.get("segments") or []
    if not segs:
        return False
    low = sum(1 for s in segs
              if (c := s.get("confidence")) is not None and c < conf_threshold)
    return low >= min_low_segs


def chunk_marks(item: dict, min_count: int = 4,
                min_density_per_100c: float = 0.7) -> list[str]:
    """返回 chunk 的重难点标记列表。

    ⭐ 重点判定用复合规则：count >= min_count（绝对门槛） AND density 每 100 字
    >= min_density_per_100c（相对密度）。单 count 阈值在长 chunk 上 saturate，
    单 density 在短 chunk 上 noisy；两者并用更鲁棒。校准：
    - Python 视频每 chunk ~10 emphasis、密度 0.8-1.6 → 大部分 ⭐
    - 王道 OS 每 chunk ~1-4 emphasis、密度低 → 少数 ⭐（讲师风格不爱"就是/即"）
    """
    text = item.get("text", "") or ""
    count = detect_emphasis_count(text)
    density = count / max(len(text), 1) * 100
    marks = []
    if count >= min_count and density >= min_density_per_100c:
        marks.append("⭐")
    if detect_difficulty(item):
        marks.append("🎯")
    # I4-d: 例题段标记（pipeline.py 在 _detect_example_chunks 后写入 is_example）
    if item.get("is_example"):
        marks.append("📝 例题")
    return marks


def _render_text_with_confidence(item: dict, threshold: float) -> str:
    """根据 segment-level confidence 渲染原文：低于 threshold 的段前加 [?] 标记。
    item.segments 缺失或 confidence 字段没填（旧 ASR cache）时退化为 item.text。"""
    segs = item.get("segments") or []
    if not segs or threshold <= 0:
        return item["text"]
    lines: list[str] = []
    for s in segs:
        c = s.get("confidence")
        text = s.get("text", "").strip()
        if not text:
            continue
        if c is not None and c < threshold:
            lines.append(f"[?{c:.2f}] {text}")
        else:
            lines.append(text)
    return "\n".join(lines) if lines else item["text"]


def _format_item(item: dict, idx: int, depth: int = 2,
                 keyframe_rel_prefix: str = "",
                 anchor: bool = False,
                 confidence_threshold: float = 0.0,
                 show_marks: bool = True) -> list[str]:
    ts = f"{format_seconds(item['start'])} - {format_seconds(item['end'])}"
    headline = item.get("headline")
    head_prefix = "#" * depth + " "
    label = f"第 {idx} 段"
    marks = chunk_marks(item) if show_marks else []
    mark_str = (" " + " ".join(marks)) if marks else ""
    h = (f"{head_prefix}{label}：{headline}{mark_str}（{ts}）" if headline
         else f"{head_prefix}{label}{mark_str}（{ts}）")
    out = []
    if anchor:
        out.append(f'<a id="chunk-{idx}"></a>\n')
    out.append(h + "\n")
    kf = item.get("keyframe")
    if kf and kf.get("rel"):
        out.append(f"![keyframe]({keyframe_rel_prefix}{kf['rel']})\n")
    kw = " · ".join(item.get("keywords", []))
    if kw:
        out.append(f"**关键词**：{kw}\n")
    out.append(f"{item['summary']}\n")
    out.append("<details><summary>原文</summary>\n")
    out.append(f"{_render_text_with_confidence(item, confidence_threshold)}\n")
    out.append("</details>\n")
    return out


def _chapter_label(ci: int, category: str) -> str:
    """章节级标签：vlog/talk 用「片段 N」（无量词，避免和 chunk 级「第 N 段」撞名），
    teaching/popsci 用「第 N 章」。"""
    return f"片段 {ci}" if category in ("vlog", "talk") else f"第 {ci} 章"


def _format_overview_card(summaries: list[dict],
                          chapters: list[dict] | None,
                          category: str = "teaching") -> list[str]:
    """顶部摘要卡：时长 / 章段数 / 核心关键词。

    vlog/talk 不显示「N 章」字段（避免和「M 段」撞「段」字 → 「2 段 / 3 段」）。"""
    if not summaries:
        return []
    is_vlog_like = category in ("vlog", "talk")
    total = summaries[-1].get("end", 0) - summaries[0].get("start", 0)
    n_chap = len(chapters) if chapters else 0
    n_seg = len(summaries)
    chap_part = f"{n_chap} 章 / " if (n_chap and not is_vlog_like) else ""
    kws = build_overview_keywords(summaries, top_k=8)
    kw_part = f" · **核心关键词** {' · '.join(kws)}" if kws else ""
    return [f"> **时长** {format_seconds(total)} · "
            f"**{chap_part}{n_seg} 段**{kw_part}\n"]


def _format_toc(chapters: list[dict], icon: str = "📑", label: str = "目录",
                category: str = "teaching") -> list[str]:
    lines = [f"## {icon} {label}\n"]
    for ci, ch in enumerate(chapters, 1):
        ts = f"{format_seconds(ch['start'])} - {format_seconds(ch['end'])}"
        lines.append(
            f"{ci}. [{_chapter_label(ci, category)}：{ch['title']}](#chapter-{ci})（{ts}）\n")
    return lines


def _format_knowledge_points(summaries: list[dict],
                             chapters: list[dict],
                             show_marks: bool = True) -> list[str]:
    """知识点速览：按章列出章内各段 headline 作为 bullet，带重难点标记。"""
    lines = ["## 💡 知识点速览\n"]
    for ci, ch in enumerate(chapters, 1):
        lines.append(f"**第 {ci} 章 · {ch['title']}**\n")
        for global_idx in ch["indices"]:
            item = summaries[global_idx]
            headline = item.get("headline") or item.get("summary", "")[:40]
            if not headline:
                continue
            ts = format_seconds(item["start"])
            marks = chunk_marks(item) if show_marks else []
            mark_str = (" " + " ".join(marks)) if marks else ""
            lines.append(
                f"- [{ts} 第 {global_idx + 1} 段](#chunk-{global_idx + 1})：{headline}{mark_str}\n")
        lines.append("")  # 章间空行
    return lines


def _format_chapter_quiz(quiz: dict) -> list[str]:
    """章末自测题 → markdown 折叠块。

    每题用 <details> 折叠答案。**不**用 blockquote 包裹（部分 markdown
    渲染器不支持 blockquote 内嵌 HTML），独立 section 风格更兼容。
    输入 quiz = {"questions": [{"type": "mc"|"tf", ...}, ...]}。
    """
    questions = quiz.get("questions", []) if quiz else []
    if not questions:
        return []
    lines = ["**🎓 本章自测**\n"]
    for qi, q in enumerate(questions, 1):
        qtype = q.get("type")
        qtext = q.get("q", "")
        expl = q.get("explanation", "")
        if qtype == "mc":
            opts = q.get("options", [])
            ai = q.get("answer_idx", 0)
            ans_letter = "ABCD"[ai] if 0 <= ai < 4 else "?"
            ans_text = opts[ai] if 0 <= ai < len(opts) else ""
            lines.append(
                f"<details>\n<summary><b>Q{qi}（选择）.</b> {qtext}</summary>\n")
            for oi, opt in enumerate(opts):
                lines.append(f"- {'ABCD'[oi]}. {opt}")
            lines.append(f"\n**答案**：{ans_letter}. {ans_text}")
            if expl:
                lines.append(f"\n**解析**：{expl}")
            lines.append("</details>\n")
        elif qtype == "tf":
            ans = q.get("answer")
            ans_str = "对 ✓" if ans else "错 ✗"
            lines.append(
                f"<details>\n<summary><b>Q{qi}（判断）.</b> {qtext}</summary>\n")
            lines.append(f"**答案**：{ans_str}")
            if expl:
                lines.append(f"\n**解析**：{expl}")
            lines.append("</details>\n")
    return lines


def _format_glossary(summaries: list[dict]) -> list[str]:
    glossary = build_glossary(summaries, top_k=15)
    if not glossary:
        return []
    lines = ["## 📚 术语表\n"]
    for g in glossary:
        ts = format_seconds(g["first_start"])
        ref = f"[{ts} 第 {g['first_idx'] + 1} 段](#chunk-{g['first_idx'] + 1})"
        snippet = f"：{g['snippet']}" if g["snippet"] else ""
        lines.append(f"- **{g['term']}**（首次：{ref}）{snippet}\n")
    return lines


def to_markdown(summaries: list[dict], title: str = "网课笔记",
                chapters: list[dict] | None = None,
                keyframe_rel_prefix: str = "",
                learning_mode: bool = True,
                confidence_threshold: float = 0.0,
                lang: str = "zh",
                category: str = "teaching") -> str:
    """没有 chapters 时输出扁平 H2 段落；有 chapters 时输出 H2 章节 + H3 段落。

    category 派生模板分发（对齐前端 NotesContent.tsx）：
      teaching: 全开（摘要卡 / 📑 目录 / 💡 知识点速览 / 📚 术语表 / 🎯⭐ 标记 / 本章小结）
      popsci:   保留摘要卡 / 目录 / 知识点速览 / 术语表 / 本章小结；关闭 🎯⭐ 标记
      vlog/talk: 仅保留摘要卡 / 时间轴 TOC；关闭知识点速览 / 术语表 / 标记 / 本章小结；
                章节单位用"段"、TOC 用 🎬 时间轴、章节概述改"本段简介"

    learning_mode=False 是旧 flag，等价于关闭所有学习类元素（最朴素 md）。
    """
    is_vlog_like = category in ("vlog", "talk")
    show_marks = learning_mode and category == "teaching"
    show_kp = learning_mode and (not is_vlog_like)
    show_glossary = learning_mode and (not is_vlog_like)
    show_chapter_recap = learning_mode and (not is_vlog_like)

    toc_icon = "🎬" if is_vlog_like else "📑"
    toc_label = "时间轴" if is_vlog_like else "目录"
    chapter_abstract_label = "本段简介" if is_vlog_like else "本章概述"

    lines = [f"# {title}\n"]
    if learning_mode:
        lines.extend(_format_overview_card(summaries, chapters, category=category))
        if chapters:
            lines.extend(_format_toc(chapters, icon=toc_icon, label=toc_label,
                                     category=category))
            if show_kp:
                lines.extend(_format_knowledge_points(summaries, chapters,
                                                     show_marks=show_marks))
        if show_glossary:
            lines.extend(_format_glossary(summaries))
        if any(lines[1:]):
            lines.append("---\n")

    if chapters:
        for ci, ch in enumerate(chapters, 1):
            ts = f"{format_seconds(ch['start'])} - {format_seconds(ch['end'])}"
            if learning_mode:
                lines.append(f'<a id="chapter-{ci}"></a>\n')
            lines.append(f"## {_chapter_label(ci, category)}：{ch['title']}（{ts}）\n")
            # 章节级 abstractive 概述（pipeline neural 模式生成，置于章标题下）
            ab = ch.get("abstract")
            if ab:
                lines.append(f"> **{chapter_abstract_label}**：{ab}\n")
            for global_idx in ch["indices"]:
                lines.extend(_format_item(
                    summaries[global_idx], global_idx + 1,
                    depth=3, keyframe_rel_prefix=keyframe_rel_prefix,
                    anchor=learning_mode,
                    confidence_threshold=confidence_threshold,
                    show_marks=show_marks))
            if show_chapter_recap:
                # LLM 生成的 recap（3-5 条 bullet markdown）优先；缺时 fallback 抽取式
                llm_recap = ch.get("recap")
                if llm_recap:
                    lines.append("> **📝 本章复习要点**：\n>")
                    for ln in llm_recap.split("\n"):
                        ln = ln.strip()
                        if ln:
                            lines.append(f"> {ln}")
                    lines.append("")
                else:
                    recap_texts = [summaries[i].get("text", "") for i in ch["indices"]]
                    recap = chapter_recap(recap_texts, max_sentences=2, lang=lang)
                    if recap:
                        lines.append(f"> **本章小结**：{recap}\n")
                # 章末自测题（仅 learning 类有 ch['quiz']；vlog/talk 不生成）
                quiz = ch.get("quiz")
                if quiz:
                    lines.extend(_format_chapter_quiz(quiz))
    else:
        for i, item in enumerate(summaries, 1):
            lines.extend(_format_item(item, i, depth=2,
                                      keyframe_rel_prefix=keyframe_rel_prefix,
                                      anchor=learning_mode,
                                      confidence_threshold=confidence_threshold,
                                      show_marks=show_marks))
    return "\n".join(lines)
