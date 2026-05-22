"""端到端：URL or 本地视频 → Markdown 笔记。"""
from __future__ import annotations

import argparse
import faulthandler
import json
import sys
from pathlib import Path

# faster-whisper / ctranslate2 退出阶段偶发 Windows STATUS_FATAL_APP_EXIT
# (rc=0xC0000409)，Python 端无 traceback；faulthandler 把 fatal signal 打到 stderr
# 让 batch script 抓到栈而非空 30 行。
faulthandler.enable()

# Windows cmd 默认 GBK 编码，print 含 emoji（B 站 prompt 里的 🔗）或 ✓ ✗
# 这种非 GBK 字符直接 UnicodeEncodeError 让 pipeline 崩。reconfigure 为 utf-8
# + errors='replace' 兼容所有 Unicode 字符（终端可能显示乱码但不再 crash）。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from download import download_video, extract_audio, fetch_metadata
from asr import (transcribe, apply_term_corrections, dedupe_consecutive_segments,
                 _tag_for_model)
from summarize import chunk_by_chars, chunk_by_texttile, to_markdown
from summarize import summarize_chunks as summarize_chunks_extractive

OUTPUT_DIR = Path("data/outputs")
META_DIR = Path("data/raw")


# 领域关键词 → 命中即激活该 domain（可叠加多个）
# 检测面：title / uploader / description 头 200 字
_DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "network": ("计算机网络", "以太网", "TCP", "/IP", "路由", "交换机",
                "OSI", "DNS", "HTTP", "数据链路", "网络层", "网卡",
                "ARP", "VLAN", "子网", "传输层"),
    "os": ("操作系统", "进程", "线程", "信号量", "死锁", "调度",
           "虚拟内存", "并发", "PV操作", "互斥", "页表", "中断"),
    "data_structure": ("数据结构", "二叉树", "链表", "图论",
                       "动态规划", "时间复杂度", "排序算法"),
    "linear_algebra": ("线性代数", "线代", "行列式", "特征值",
                       "向量空间", "矩阵"),
    "python_lang": ("Python 基础", "python编程", "Python 教程",
                    "编程入门"),
    "claude_code": ("Claude Code", "Anthropic", "agentic"),
}

# 域 → 喂给 initial_prompt 的术语清单（限 ~12 词，预算紧）
# 选词标准：whisper 在中文域容易听错的多字术语，越具体越能 bias 出对的字
_DOMAIN_HOTWORDS: dict[str, list[str]] = {
    "network": ["数据帧", "广播帧", "目的MAC地址", "源MAC地址",
                "端口转发", "链路层", "以太网", "交换表",
                # p37 局域网体系：物理层介质 + 协议名 + 通信模式
                "双绞线", "同轴电缆", "CSMA/CD", "令牌环网",
                "半双工", "全双工", "网络适配器", "集线器"],
    "os": ["进程调度", "信号量", "死锁", "互斥锁", "PV操作",
           "虚拟内存", "页表"],
    "data_structure": ["二叉树", "链表", "时间复杂度", "递归"],
    "linear_algebra": ["矩阵", "行列式", "特征值", "特征向量",
                       "线性变换"],
    "python_lang": ["函数", "字典", "列表", "异常处理"],
    "claude_code": ["Claude Code", "提示词", "Agent"],
}

# 域 → 安全的 ASR 同音字后处理。只放歧义低的 substring，避免破坏合法用法
# （比如不直接 "针"→"帧"，因为会破坏 "指针" / "针对"）
_DOMAIN_CORRECTIONS: dict[str, dict[str, str]] = {
    "network": {
        # 计网 whisper 系统性把"帧"听成"针"：p44 (以太网交换机) 134/363 段中招
        # 实测 p44 0 个合法"针"（无指针/针对/针线），但保守起见仍用 substring 而非
        # 全局 re.sub，避免在其他计网视频里破坏"指针/针对"等合法用法
        "号针": "号帧",          # "1号针" / "6号针"
        "数据针": "数据帧",
        "广播针": "广播帧",
        "信元针": "信元帧",
        "这个针": "这个帧",
        "那个针": "那个帧",
        "一个针": "一个帧",
        "整个针": "整个帧",
        "接收针": "接收帧",
        "发送针": "发送帧",
        "转发针": "转发帧",
        "丢弃针": "丢弃帧",
        "解析针": "解析帧",
        "网针": "网帧",          # "以太网针"
        "MAC针": "MAC帧",
        "Q针": "Q帧",            # "802.1Q针"
        "把针": "把帧",          # "把针丢弃" / "把针转发"
        "到针": "到帧",          # "收到针之后" / "看到针"
        "完整的针": "完整的帧",
        "格式的针": "格式的帧",
        "发出的针": "发出的帧",
        "标准的针": "标准的帧",
        "的针": "的帧",          # cover "收到的针" / "X 的针"；"指针的" 反向不冲突
        # p37 局域网体系：物理介质 + 协议名 易听错的同音字
        "双角线": "双绞线",       # whisper 把"绞"听成"角"
        "双饺线": "双绞线",       # 备选音
        "双胶线": "双绞线",
        "双脚线": "双绞线",       # p38 实测变体
        "csma-cd": "CSMA/CD",    # whisper 倾向小写 + dash
        "CSMA-CD": "CSMA/CD",    # 不带斜杠的变体
        "csma/cd": "CSMA/CD",    # whisper 也会直接输出小写带斜杠
        "Csma/Cd": "CSMA/CD",
        "csma cd": "CSMA/CD",    # 缺连接符的变体
        "中端节点": "终端节点",   # "终" 听成 "中"
        "中端结点": "终端结点",
        # p46 (IPv4 分组) 实测：whisper 把"首"听成"手"，全文 27+ 次"手部"应为"首部"。
        # "手部" 在计网域绝无合法用法，全局替换安全（domain 限定在 network 已足够保险）
        "手部": "首部",
        # p49 (CIDR) 实测："网络前缀" 被识成"网络潜坠"，"潜坠"非常用词
        "潜坠": "前缀",
        # p50 (路由聚合) 实测："路由表项" 被识成"路由表象"，34+ 处。"表象"
        # 虽然在心理学/哲学是合法词，但计网域几乎不会用本义
        "表象": "表项",
        # p85 (TCP 拥塞控制) 实测：whisper 在"拥塞"上系统性失败，9 种错听变体
        # 总错频 109 > 正频 68。全部映射回"拥塞"——这些字组合在计网无合法义
        "拥测": "拥塞",
        "拥測": "拥塞",
        "拥色": "拥塞",
        "拥瑟": "拥塞",
        "拥舍": "拥塞",
        "拥饰": "拥塞",
        "拥侧": "拥塞",
        "拥側": "拥塞",
        "拥筛": "拥塞",
        # ACK 听成 AKK：p78 26 处 + p85 11 处。AKK 不是合法术语，全局替换安全
        "AKK": "ACK",
        # p78 (TCP 报文段) 实测："校验和" 6 处错听成"校验核"。"校验核"
        # 非术语，应回"校验和"（TCP/UDP 首部字段标准译名）
        "校验核": "校验和",
        # p85 偶发繁体（whisper 偶尔切到繁体语言模型）：報文/導致 各 1-4 次
        # 计网域没有理由用繁体，统一回简体
        "報文": "报文",
        "導致": "导致",
    },
    "os": {
        # 王道 OS p38 (管程入门) 实测：whisper 把"管程"听成"广程"，35/501 段中招
        # "广程"在中文里几乎不是常用词，全局替换安全
        "广程": "管程",
        "管成": "管程",       # 备选音
        "光程": "管程",       # 备选音
        # 信号量错字（积累自历次 OS 视频）
        "信号亮": "信号量",
        "呼吃信号量": "互斥信号量",
        "互析": "互斥",
    },
}


def _detect_domains(meta: dict | None) -> list[str]:
    if not meta:
        return []
    text = " ".join(filter(None, [meta.get("title", ""),
                                  meta.get("uploader", ""),
                                  (meta.get("description") or "")[:200]]))
    return [d for d, kws in _DOMAIN_KEYWORDS.items()
            if any(kw in text for kw in kws)]


def _detect_lang(meta: dict | None) -> str:
    """启发式判断视频语言：中文字符占比 > 15% 视为中文，否则英文。

    优先级：title > description（uploader 不参与，因为 b 站作者名常常都是中文
    即使内容是英文）。返回 'zh' 或 'en'。"""
    if not meta:
        return "zh"
    text = (meta.get("title") or "") + (meta.get("description") or "")[:300]
    if not text:
        return "zh"
    cn = sum(1 for c in text if "一" <= c <= "鿿")
    ratio = cn / max(len(text), 1)
    return "zh" if ratio > 0.15 else "en"


def _verify_lang(asr_result: dict, fallback_lang: str) -> str:
    """ASR 跑完后看实际 segment text 中英占比，覆盖 metadata-based detect。

    与 _detect_lang 用相同 15% 阈值，但 source 是真实 ASR 输出而非 metadata。
    针对"中文标题/描述 wrapper 英文 ASR 内容"这类 case（B 站搬运 YouTube 英语
    播客 / 英语听力素材），metadata 判 zh 但实际是 en，本函数从 ASR 文本反推
    覆盖，避免下游 Qwen 用错语言模板生成与内容错位的章节标题。"""
    segs = asr_result.get("segments") or []
    if not segs:
        return fallback_lang
    # 采样前 50 段足够判断主语言，避免长视频拼整串浪费
    text = "".join(s.get("text", "") for s in segs[:50])
    if not text:
        return fallback_lang
    cn = sum(1 for c in text if "一" <= c <= "鿿")
    ratio = cn / max(len(text), 1)
    return "zh" if ratio > 0.15 else "en"


def _build_asr_prompt(meta: dict, lang: str = "zh") -> str:
    """从视频 metadata 拼一段适合喂给 faster-whisper 的 initial_prompt。
    Whisper 的 initial_prompt 上限约 224 tokens，控制在 200 字以内。

    策略：
    - 标题永远塞进去（最强信号）
    - 命中 domain 时插入"涉及术语：A、B、C..."注入 hotwords bias 字形选择
      （例如 计网 域注入"数据帧"让 whisper 倾向输出"帧"而非"针"）
    - 域未命中才回退用 description 补语义；命中时 description 多半是带货噪音
    - uploader 作为补充上下文

    lang='en' 时跳过中文 hotwords 注入——中文 prompt 会污染英文 ASR 语言检测，
    导致 WSPChlfxJyA 那种 detected='zh' 但实际输出英文文本的怪异状态。
    """
    if lang == "en":
        # 英文视频：只把标题作为最小 prompt，让 whisper 自己识别
        return (meta.get("title") or "")[:200]
    parts: list[str] = []
    if meta.get("title"):
        parts.append(meta["title"])
    domains = _detect_domains(meta)
    if domains:
        seen: set[str] = set()
        hot: list[str] = []
        for d in domains:
            for w in _DOMAIN_HOTWORDS.get(d, []):
                if w not in seen:
                    seen.add(w)
                    hot.append(w)
        if hot:
            # 14 词在 200 char initial_prompt 预算内（实测 title+uploader+14术语 ≈ 170c）
            parts.append("涉及术语：" + "、".join(hot[:14]))
    elif meta.get("description"):
        parts.append(meta["description"][:120])
    if meta.get("uploader"):
        parts.append(f"作者：{meta['uploader']}")
    return "。".join(parts)[:200]


# 从 metadata 抽出来的 CamelCase / 大写专有名词，对应它最常被 ASR 听错的变体。
# 后处理用这个字典 substring replace，避免错字传到摘要。
# 已知 ASR 高频混淆：Claude → Cloud（whisper 训练语料里 cloud 频次远超 claude）。
_ASR_CONFUSIONS = {
    "Claude": ["Cloud"],  # 还可以扩 "Clone" 等，但保守一点
}


def _build_term_corrections(meta: dict) -> dict[str, str]:
    import re
    text = " ".join(filter(None, [meta.get("title"), meta.get("description") or ""]))
    # 抓 CamelCase（>=2 段） 或 全大写 / 含数字的长英文词，作为"权威术语"
    camels = set(re.findall(r"[A-Z][a-z]+(?:[A-Z][a-zA-Z0-9]+)+", text))
    # 也抓单段首字母大写的 5+ 字母词（如 "Claude"、"Anthropic"）
    words = set(re.findall(r"\b[A-Z][a-z]{4,}\b", text))
    # CamelCase 拆出首段作为单独词候选
    for camel in camels:
        m = re.match(r"([A-Z][a-z]+)", camel)
        if m:
            words.add(m.group(1))

    corrections: dict[str, str] = {}
    for term in words:
        for confused in _ASR_CONFUSIONS.get(term, []):
            corrections[confused] = term
            corrections[confused.lower()] = term.lower()
    # CamelCase 整词替换（同时处理空格变体）
    for camel in camels:
        m = re.match(r"([A-Z][a-z]+)([A-Z][a-zA-Z0-9]+)", camel)
        if not m:
            continue
        first, rest = m.group(1), m.group(2)
        for wrong_first in _ASR_CONFUSIONS.get(first, []):
            corrections[f"{wrong_first}{rest}"] = camel
            corrections[f"{wrong_first} {rest}"] = f"{first} {rest}"
            corrections[f"{wrong_first.lower()}{rest.lower()}"] = camel
            corrections[f"{wrong_first.lower()} {rest.lower()}"] = f"{first} {rest}"

    # 域级中文 ASR 同音字 corrections（initial_prompt 漏过的 safety net）
    for d in _detect_domains(meta):
        corrections.update(_DOMAIN_CORRECTIONS.get(d, {}))
    return corrections


def _output_stem(audio: Path, tag: str, summarizer: str, chunker: str,
                 chunk_chars: int = 800, keyframes: bool = False,
                 vlm_captions: bool = False) -> str:
    """统一 pipeline 输出文件 stem：`{audio.stem}.{tag}.{summarizer}[.{chunker}][.cc{N}][.mm[.vl]]`

    - chunker='chars' 是 baseline，stem 省略以保留旧文件名兼容
    - chunk_chars=800 是默认值，stem 省略；非默认加 `.cc{N}` 防多 cc 互相覆盖
    - keyframes=True 时加 `.mm` 后缀，防 mm ablation 跑覆盖纯文本路径
    - vlm_captions=True 时再加 `.vl`，让 VLM caption 跑出的不覆盖 CLIP sim 跑出的
      （§5.4 对比 sim vs VLM caption）
    """
    stem = f"{audio.stem}.{tag}.{summarizer}"
    if chunker != "chars":
        stem += f".{chunker}"
    if chunk_chars != 800:
        stem += f".cc{chunk_chars}"
    if keyframes:
        stem += ".mm"
        if vlm_captions:
            stem += ".vl"
    return stem


def _load_meta_safe(path: Path) -> dict | None:
    """读 meta JSON，文件不存在或损坏一律返回 None。pipeline 里 meta 不是必需，
    缺失只影响 ASR prompt / 术语字典 / md 标题这些 nice-to-have 字段。"""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


_AUDIO_EXTS = {".m4a", ".mp3", ".wav", ".aac", ".flac"}


def _resolve_video_for_keyframes(source: Path) -> Path | None:
    """source 是视频就直接返回；如果是纯音频（.m4a 等），
    去同目录找同前缀的视频文件。"""
    if source.suffix.lower() not in _AUDIO_EXTS:
        return source
    # B 站 yt-dlp 分流文件名形如 BVxxx_p38.f30280.m4a / BVxxx_p38.f100023.mp4，
    # 公共前缀到第一个 '.' 之前
    prefix = source.stem.split(".")[0]
    for sibling in source.parent.glob(f"{prefix}*"):
        if sibling.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov"):
            return sibling
    return None


# 视频末尾"复习/小结章"识别的 trigger 短语。讲师在 wrap-up 段反复使用其中几个。
# 触发条件：在末位章的 chunks 内累计命中 >=2 个 trigger（防误判：单 trigger 在中间章
# 也可能命中，比如 "我们介绍了 X，接下来 Y"）。
_WRAPUP_TRIGGERS = (
    # 中文 trigger
    "以上就是", "我们学习了", "我们介绍了", "我们讲解了",
    "在这个视频中", "本节课讲了", "本视频讲了",
    "重难点", "考试的重点", "考点", "回顾一下", "做个总结",
    # 英文 trigger（小写 substring 匹配；whisper 输出可能大小写）
    "in summary", "to summarize", "let's recap", "to recap", "in conclusion",
    "in this video", "we covered", "we've covered", "we learned",
    "key takeaway", "key takeaways", "wrap up", "wrapping up", "to wrap",
    "In summary", "To summarize", "Let's recap", "In conclusion",
    "In this video", "We covered", "We learned",
)


def _mark_wrapup_chapter(chapter_list: list, lang: str = "zh") -> None:
    """如果最后一章是讲师 wrap-up（短语命中 >=2 个），给 title 加 " · 本节复习" marker。
    只检最后一章——中间章节里讲师过渡用"我们介绍了"是正常叙事，不算 wrap-up。"""
    if not chapter_list:
        return
    last = chapter_list[-1]
    chunks = last.get("chunks", [])
    if not chunks:
        return
    joined = " ".join(c.get("text", "") for c in chunks)
    joined_lower = joined.lower()  # 英文 trigger 大小写不敏感匹配
    hits = sum(
        1 for t in _WRAPUP_TRIGGERS
        if (t.lower() in joined_lower if any(c.isascii() and c.isalpha() for c in t)
            else t in joined)
    )
    if hits >= 2:
        title = last.get("title", "")
        marker = " · Recap" if lang == "en" else " · 本节复习"
        if "本节复习" not in title and "Recap" not in title:  # 幂等
            last["title"] = f"{title}{marker}" if title else marker.lstrip(" ·")
            print(f"      [wrapup] 末章命中 {hits} 个 trigger，标记为复习章: "
                  f"{last['title']}", flush=True)


def _apply_chapter_abstracts(chapter_list: list, llm_chapters: bool,
                              lang: str = "zh") -> None:
    """给每章填 `abstract` 字段。`--llm-chapters` 时优先 Qwen 生成 1-2 句 prose；
    Qwen 失败 / 关闭时 fallback 到 `summarize_chapter`（拼 headlines）。
    顶层 + 子章节都处理；子章节当前用 fallback（Qwen 批量逻辑仅做顶层）。"""
    abstracts = None
    if llm_chapters:
        try:
            from segment_llm import generate_chapter_abstracts
            abstracts = generate_chapter_abstracts(chapter_list, lang=lang)
        except Exception as e:
            print(f"      [llm-chapter-abstract] 异常：{e}，fallback summarize_chapter",
                  flush=True)
    from summarize_neural import summarize_chapter
    if abstracts and len(abstracts) == len(chapter_list):
        for ch, ab in zip(chapter_list, abstracts):
            ch["abstract"] = ab
            print(f"      [chapter abstract] L1 -> {ab[:60]}", flush=True)
    else:
        for ci, ch in enumerate(chapter_list, 1):
            ch["abstract"] = summarize_chapter(ch["chunks"])
            print(f"      [chapter abstract] L1 {ci}/{len(chapter_list)} "
                  f"-> {ch['abstract'][:50]}", flush=True)
    # 子章节统一用 fallback summarize_chapter（数据少，单独发 LLM 性价比低）
    for ch in chapter_list:
        for sub in ch.get("children", []) or []:
            sub["abstract"] = summarize_chapter(sub["chunks"])


def run(source: str, is_local: bool = False, chunk_chars: int = 800,
        model_size: str = "large-v3", target_ratio: float = 0.25,
        force_asr: bool = False, summarizer: str = "extractive",
        chapters: int | None = None,
        extra_terms: dict[str, str] | None = None,
        keyframes: bool = False, mm_alpha: float = 0.3,
        chunker: str = "chars", learning_mode: bool = True,
        dedupe_asr: bool = True, llm_chapters: bool = False,
        confidence_threshold: float = 0.5,
        lang: str = "auto",
        vlm_captions: bool = False) -> Path:
    print(f"[1/4] 准备视频: {source}")
    asr_prompt = None
    meta = None
    if is_local:
        video = Path(source)
        if not video.exists():
            raise FileNotFoundError(video)
    else:
        meta = fetch_metadata(source)
        video = download_video(source)
        # 保存 metadata 方便后续展示真实标题等
        META_DIR.mkdir(parents=True, exist_ok=True)
        slim_meta = {k: meta.get(k) for k in
                     ("id", "title", "uploader", "duration", "webpage_url", "description")}
        (META_DIR / f"{video.stem}.meta.json").write_text(
            json.dumps(slim_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"      video = {video}")

    print("[2/4] 抽取音频...")
    audio = extract_audio(video)
    print(f"      audio = {audio}")

    # 本地路径模式下尝试从同名 .meta.json 拿 prompt + 术语
    meta_path = META_DIR / f"{video.stem}.meta.json"
    meta_for_terms = _load_meta_safe(meta_path) or meta

    # 语言检测：auto 模式按 meta 启发式判断；用户显式传 zh/en 时尊重
    resolved_lang = lang if lang in ("zh", "en") else _detect_lang(meta_for_terms)
    print(f"      [lang] 视频语言: {resolved_lang}" + (f" (auto-detected)" if lang == "auto" else ""))

    if meta_for_terms is not None:
        asr_prompt = _build_asr_prompt(meta_for_terms, lang=resolved_lang)

    corrections: dict[str, str] = {}
    if meta_for_terms:
        corrections.update(_build_term_corrections(meta_for_terms))
    if extra_terms:
        corrections.update(extra_terms)

    tag = _tag_for_model(model_size)
    asr_cache = OUTPUT_DIR / f"{audio.stem}.{tag}.asr.json"
    if asr_cache.exists() and not force_asr:
        print(f"[3/4] 命中 ASR 缓存: {asr_cache}")
        asr_result = json.loads(asr_cache.read_text(encoding="utf-8"))
        # 旧 cache 没 word_timestamps / confidence 字段：用户若开了 --confidence-threshold>0
        # 不会报错（render 退化），但低置信标记也不会出现。提示用户用 --force-asr 升级 cache。
        if confidence_threshold > 0 and asr_result.get("segments"):
            first = asr_result["segments"][0]
            if "confidence" not in first:
                print(f"      [hint] cache 早于 confidence 落地（无 segments[].confidence），"
                      f"--confidence-threshold={confidence_threshold} 不会有效。"
                      f"加 --force-asr 重跑 ASR 升级 cache schema（~30s/视频）")
    else:
        print("[3/4] 语音识别（首次会下载 ~3GB 模型）...")
        asr_result = transcribe(audio, model_size=model_size,
                                language=resolved_lang,
                                initial_prompt=asr_prompt)
    verified_lang = _verify_lang(asr_result, resolved_lang)
    if verified_lang != resolved_lang:
        print(f"      [lang] ASR 实际语言为 {verified_lang}，"
              f"覆盖 metadata 判断 {resolved_lang}（下游 Qwen 改用 {verified_lang} 模板）")
        resolved_lang = verified_lang
    if corrections:
        print(f"      ASR 后处理替换 {len(corrections)} 条术语: "
              f"{', '.join(list(corrections.keys())[:5])}{'...' if len(corrections) > 5 else ''}")
        asr_result = apply_term_corrections(asr_result, corrections)
    if dedupe_asr:
        asr_result, dd_stats = dedupe_consecutive_segments(asr_result)
        if dd_stats["dropped"]:
            print(f"      ASR 连续重复段去重: 丢弃 {dd_stats['dropped']} 段，"
                  f"合并 {len(dd_stats['runs'])} 个 run")
            for r in dd_stats["runs"][:3]:
                print(f"        run x{r['run_len']} @ {r['start']:.1f}s: "
                      f"{r['text']}")
    print(f"      duration={asr_result['duration']:.1f}s, "
          f"segments={len(asr_result['segments'])}")

    if chunker == "texttile":
        chunks = chunk_by_texttile(asr_result["segments"],
                                   target_chunk_chars=chunk_chars)
        chunker_desc = f"chunker=texttile target≈{chunk_chars}c"
    else:
        chunks = chunk_by_chars(asr_result["segments"], chunk_chars=chunk_chars)
        chunker_desc = f"chunker=chars chunk_chars={chunk_chars}"
    if summarizer == "neural" and llm_chapters:
        # Pegasus 输出 100% 被 Qwen 覆盖，--llm-chapters 时直接跳过节省 ~30s + ~1GB VRAM
        print(f"[4/4] {chunker_desc}, {len(chunks)} chunks + 抽取式 summary（Qwen 后生 headline）...")
        from summarize_neural import summarize_chunks_no_headline
        summaries = summarize_chunks_no_headline(chunks, target_ratio=target_ratio,
                                                  lang=resolved_lang)
    elif summarizer == "neural":
        print(f"[4/4] {chunker_desc}, {len(chunks)} chunks + 神经摘要（Pegasus-238M）...")
        from summarize_neural import summarize_chunks as summarize_chunks_neural
        summaries = summarize_chunks_neural(chunks, lang=resolved_lang)
    else:
        print(f"[4/4] {chunker_desc}, {len(chunks)} chunks + 抽取式摘要（ratio={target_ratio}）...")
        summaries = summarize_chunks_extractive(chunks, target_ratio=target_ratio,
                                                 lang=resolved_lang)

    # ===== Qwen ASR 同音字校错（chunk-level 上下文）=====
    # 跑在 headline 生成 / 章节切分前，把"双脚线→双绞线"这类隐式错字（substring
    # corrections map 救不了的）救回。需要 chunk 关键词作上下文 cue，所以放在
    # summarize 之后。Pegasus 模式也支持（不绑 llm_chapters，但 LLM 已用于章节就
    # 没有额外 VRAM 成本）。
    if llm_chapters and summarizer == "neural" and summaries and resolved_lang != "en":
        # 英文视频跳过 qwen_asr_fix（专攻中文同音字，对英文 ASR 无意义且会产生
        # 大量 false positive 被防御过滤掉，纯浪费一次 LLM 调用 ~20s）
        try:
            from segment_llm import qwen_asr_fix
            asr_fixes = qwen_asr_fix(summaries)
        except Exception as e:
            print(f"      [llm-asr-fix] 异常：{e}", flush=True)
            asr_fixes = {}
        if asr_fixes:
            # 按 key 长度降序避免短词先吃长词（与 apply_term_corrections 一致）
            items = sorted(asr_fixes.items(), key=lambda kv: -len(kv[0]))
            for chunk in summaries:
                for wrong, right in items:
                    chunk["text"] = chunk["text"].replace(wrong, right)
                    for seg in chunk.get("segments", []) or []:
                        seg["text"] = seg["text"].replace(wrong, right)
            apply_term_corrections(asr_result, asr_fixes)  # 兜底，asr_result 用于 md 原文区
            # 修后重新抽 keywords（jieba 在错字上抓的 keyword 可能误导下游 LLM 切分）
            from summarize import keywords_for
            from summarize_neural import clean_for_summary
            for chunk in summaries:
                chunk["keywords"] = keywords_for(clean_for_summary(chunk["text"]))
            print(f"      [llm-asr-fix] 应用 {len(asr_fixes)} 个错字 + 重抽关键词", flush=True)

    visual_feats = None
    if keyframes:
        from keyframe import extract_keyframes
        video_for_kf = _resolve_video_for_keyframes(video)
        if video_for_kf is None:
            print(f"      [keyframes] 跳过：找不到 {video} 对应的视频流文件")
        else:
            print(f"      [keyframes] 用视频 {video_for_kf.name} 抽帧 ...")
            # keyframes 目录与 CLIP-only / VLM 路径**共享**（同一段视频两个跑法
            # 帧本身是一样的，只是 caption 不同），所以 kf_dir 不带 .vl 后缀
            kf_dir = OUTPUT_DIR / f"{_output_stem(audio, tag, summarizer, chunker, chunk_chars, keyframes=True)}.keyframes"
            summaries, visual_feats = extract_keyframes(video_for_kf, summaries, kf_dir)
            kf_rel_prefix = f"{kf_dir.name}/"
    else:
        kf_rel_prefix = ""

    chapter_list = None
    ablation = None
    # 切分路径元数据（供论文附录 B 表用）
    seg_meta = {
        "method": None,           # llm | texttile_fallback | none
        "llm_attempts": 0,
        "llm_pass_via": None,
        "llm_repair_used": [],
        "llm_fail_reasons": [],
        "fallback_used": False,
    }

    # ===== LLM 生成/重写 chunk headline =====
    # 两种来源：(a) Pegasus 模式有初版 headline → Qwen `refine_headlines` 重写；
    # (b) 无 Pegasus 模式 headline 是空串 → Qwen `generate_headlines` 直接从原文生成。
    if llm_chapters and summarizer == "neural" and summaries:
        has_initial = any((c.get("headline") or "").strip() for c in summaries)
        try:
            if has_initial:
                print("[headlines] Qwen 重写 Pegasus 初版 chunk headline ...", flush=True)
                from segment_llm import refine_headlines
                refined = refine_headlines(summaries, lang=resolved_lang)
            else:
                print("[headlines] Qwen 从原文直接生成 chunk headline ...", flush=True)
                from segment_llm import generate_headlines
                refined = generate_headlines(summaries, lang=resolved_lang)
        except Exception as e:
            print(f"      [llm-headline] 异常：{e}，保留初版", flush=True)
            refined = None
        if refined and len(refined) == len(summaries):
            for c, new_hl in zip(summaries, refined):
                c["headline_pegasus"] = c.get("headline", "")  # 留底
                c["headline"] = new_hl
            print(f"      [llm-headline] 填充 {len(refined)} 段 headline", flush=True)

    # 多模态信号：keyframes 抽帧时，把相邻 chunk 的 CLIP 视觉相似度送给 LLM 切分
    # 作为额外提示（用作 tie-breaker，文本主题仍是主依据）
    visual_sims_for_llm = None
    if visual_feats is not None:
        from segment import visual_adjacent_distances
        v_dists = visual_adjacent_distances(visual_feats)
        visual_sims_for_llm = [(1.0 - d) if d is not None else None for d in v_dists]
        print(f"      [mm-llm] 视觉相似度 cue 启用：{sum(1 for s in visual_sims_for_llm if s is not None)}/{len(visual_sims_for_llm)} 段间隙有信号",
              flush=True)

    # ===== VLM caption（Qwen2.5-VL-7B-AWQ）：每 chunk 1 句画面描述 =====
    # 给 LLM 切分提供比浮点 sim 信息密度高 10x 的视觉 cue。需 --keyframes + --vlm-captions。
    # VRAM 占用与 Qwen2.5-7B-Instruct-AWQ 相近，跑完会 free_vl_model() 让 instruct 加载回来。
    visual_captions_for_llm = None
    vl_max_prefix_run = None  # 二次门控诊断指标
    vl_degraded_reason = None
    # 自适应规则（两层）：
    # 外层 - n_chunks ≤ 15：短/动态视频画面信息密度高，caption 切更细（OS p37 实测）
    # 外层 - n_chunks > 15：长视频画面 pattern 单一，caption 反诱发 catch-all（BV1S6kQBNEJq）
    # 内层 - caption 前缀长 run 检测：即使外层通过，若 captions 出现 ≥4 个共享 10 字
    #        前缀的连续 run 且剩余 chunks ≥ 3（p44 实测 5/9 chunks 共享"以太网交换机
    #        的自学习功能"），LLM 误以为"同主题需合并"漏 chunks；OS p37 max_run=4
    #        但 n-run=1 不触发内层，保留增益
    CAPTION_MAX_CHUNKS = 15
    CAPTION_PREFIX_K = 10
    CAPTION_PREFIX_RUN_MIN = 4
    CAPTION_OTHER_MIN = 3
    if vlm_captions and keyframes and summaries:
        try:
            from caption_vl import caption_keyframes, caption_redundancy, free_vl_model
            print("[vl-cap] Qwen2.5-VL 给关键帧生 caption ...", flush=True)
            captions = caption_keyframes(summaries, lang=resolved_lang)
            free_vl_model()
            # 把 caption 写回 chunk dict 让 summary.json / 前端 / 论文 §5.4 截图能看
            if captions and len(captions) == len(summaries):
                for c, cap in zip(summaries, captions):
                    if cap:
                        c["vlm_caption"] = cap
            # 诊断指标（仅 log，不参与判定）
            jaccard, generic = caption_redundancy(captions)
            n_cap = sum(1 for x in captions if x)
            # 计算最大前缀 run（参与内层判定）
            cur = best = 1
            for i in range(1, len(captions)):
                a = captions[i-1] or ""
                b = captions[i] or ""
                if a and b and a[:CAPTION_PREFIX_K] == b[:CAPTION_PREFIX_K]:
                    cur += 1
                    best = max(best, cur)
                else:
                    cur = 1
            vl_max_prefix_run = best
            print(f"      [vl-cap] n_cap={n_cap}, jaccard_mean={jaccard:.2f}, "
                  f"generic_ratio={generic:.2f}, max_prefix_run={best}/{len(captions)}",
                  flush=True)
            # 外层判定：n_chunks 阈值
            if len(summaries) > CAPTION_MAX_CHUNKS:
                vl_degraded_reason = "n_chunks_gt_15"
                print(f"      [vl-cap] n_chunks={len(summaries)} > "
                      f"{CAPTION_MAX_CHUNKS} → 长视频画面 pattern 易让 LLM catch-all，"
                      f"降级回 CLIP sim cue", flush=True)
                visual_captions_for_llm = None
            # 内层判定：前缀长 run + 剩余 chunks
            elif (best >= CAPTION_PREFIX_RUN_MIN
                  and len(captions) - best >= CAPTION_OTHER_MIN):
                vl_degraded_reason = "prefix_run_degenerate"
                print(f"      [vl-cap] max_prefix_run={best}, "
                      f"others={len(captions)-best} → caption 高度同质化但剩余 chunks "
                      f"足够多，易诱发 LLM 漏 chunks（p44 case），降级回 CLIP sim cue",
                      flush=True)
                visual_captions_for_llm = None
            else:
                visual_captions_for_llm = captions
                print(f"      [vl-cap] n_chunks={len(summaries)} ≤ "
                      f"{CAPTION_MAX_CHUNKS} 且 prefix_run={best} 不退化 → "
                      f"caption 用作切分主信号", flush=True)
        except Exception as e:
            print(f"      [vl-cap] 异常：{e}（跳过 caption，回退 sim cue）", flush=True)

    # ===== LLM 层级章节切分（替代 TextTiling 章节路径）=====
    if llm_chapters:
        print("[chapters] LLM 层级章节切分（Qwen2.5-7B-AWQ）...", flush=True)
        try:
            from segment_llm import segment_hierarchical
            outline = segment_hierarchical(summaries, visual_sims=visual_sims_for_llm,
                                            visual_captions=visual_captions_for_llm,
                                            lang=resolved_lang)
        except Exception as e:
            print(f"      [llm-chapters] 异常：{e}，fallback TextTiling", flush=True)
            outline = None
        # VL 救援：用了 VL caption 但 LLM 3 attempts + repair 都失败时，
        # 自动 retry 一次不带 caption（仅 sim cue）。FwOTs4UxQS4 实测 VL 让
        # mm.vl 死在 missing，mm-only 第 3 attempt 通过——caption 偶尔诱发
        # Qwen 漏 chunks 是英文短视频上的失败模式，门控 prefix-run 抓不到
        # 语义同构但前缀不同的英文 caption，所以加这层"事后救援"作 belt-and-
        # suspenders 兜底
        vl_rescue_triggered = False
        if (outline is not None
                and visual_captions_for_llm is not None
                and not outline.get("chapters")):
            print(f"      [vl-rescue] VL caption 路径 LLM 3 attempts + repair 都失败，"
                  f"自动 retry 不带 caption（仅 sim cue）...", flush=True)
            try:
                outline_rescue = segment_hierarchical(
                    summaries, visual_sims=visual_sims_for_llm,
                    visual_captions=None, lang=resolved_lang)
                if outline_rescue and outline_rescue.get("chapters"):
                    print(f"      [vl-rescue] retry 成功，VL caption 是失败原因",
                          flush=True)
                    outline = outline_rescue
                    vl_rescue_triggered = True
                    # 标记后续 ablation：vlm 被自动救援降级
                    vl_degraded_reason = "rescue_after_llm_fail"
                    visual_captions_for_llm = None
                else:
                    print(f"      [vl-rescue] retry 仍失败，问题不在 VL caption",
                          flush=True)
            except Exception as e:
                print(f"      [vl-rescue] 异常：{e}", flush=True)
        # 即便 outline 没出 chapters（LLM 失败），也读 _meta 让 ablation 准确
        # 显示"LLM 跑了 N 次 attempt 但失败 → fallback"
        if outline:
            llm_meta = outline.get("_meta") or {}
            seg_meta["llm_attempts"] = llm_meta.get("attempts_used", 0)
            seg_meta["llm_pass_via"] = llm_meta.get("pass_via")
            seg_meta["llm_repair_used"] = llm_meta.get("repair_used", [])
            seg_meta["llm_fail_reasons"] = llm_meta.get("fail_reasons", [])
            seg_meta["vl_rescue_used"] = vl_rescue_triggered
        if outline and outline.get("chapters"):
            chapter_list = outline["chapters"]
            seg_meta["method"] = "llm"
            # 补 chunks 引用，供后续 chapter abstract 用
            for ch in chapter_list:
                ch["chunks"] = [summaries[i] for i in ch["indices"]]
                for sub in ch.get("children", []):
                    sub["chunks"] = [summaries[i] for i in sub["indices"]]
            print(f"      [llm-chapters] {len(chapter_list)} 顶层 / "
                  f"{sum(len(ch.get('children', [])) for ch in chapter_list)} 子章节",
                  flush=True)
            # 章节级 abstractive 概述：llm_chapters 模式下用 Qwen 生成 prose，
            # 否则 / Qwen 失败时 fallback 到拼接式 summarize_chapter
            if summarizer == "neural":
                _apply_chapter_abstracts(chapter_list, llm_chapters, lang=resolved_lang)
            _mark_wrapup_chapter(chapter_list, lang=resolved_lang)

    if chapter_list is None and chapters is not None and chapters != 0:
        # 走 fallback TextTiling 路径（或用户没开 llm_chapters）
        if llm_chapters:
            seg_meta["fallback_used"] = True
        seg_meta["method"] = "texttile"
        from segment import segment_chunks, detect_boundaries
        n = chapters if chapters > 0 else None
        title_fn = None
        # llm_chapters 时 refine_chapter_titles 会覆盖 fallback 章标题，无需 Pegasus
        # title_fn——保留 None 走 _default_title（取首段 headline），由后续 Qwen 改写
        if summarizer == "neural" and not llm_chapters:
            # 复用 Pegasus 对整章重新生成一个更概括的标题
            from summarize_neural import (summarize_text, clean_for_summary,
                                          post_clean_headline,
                                          nominalize_title,
                                          _is_chapter_title_copy,
                                          _fallback_chapter_title)

            def title_fn(members):
                # 层次化摘要：拼接各段 headline 而非原文，避免输入超 max_input
                # 而只看到首段。短输入让 Pegasus 做高层抽象。
                headlines = [m.get("headline", "") for m in members
                             if m.get("headline")]
                if not headlines:
                    joined = "".join(clean_for_summary(m["text"]) for m in members)
                    return nominalize_title(post_clean_headline(summarize_text(joined)))
                if len(headlines) == 1:
                    return nominalize_title(headlines[0])
                joined = "。".join(headlines)
                title = post_clean_headline(summarize_text(joined))
                # Pegasus 在小输入（≤3 段 headline）上倾向退化成抄一段。大章节
                # (n≥4) 时 Pegasus 可能从多个候选中选 representative，即使 copy
                # 也是有意识选择，保留比 fallback 强（fallback 只看前 2 段会丢章中段）。
                if len(headlines) <= 3 and _is_chapter_title_copy(title, headlines):
                    title = _fallback_chapter_title(headlines)
                return nominalize_title(title)
        # ablation: 文本-only 和 多模态分别算一次，方便对比与论文分析
        text_only_bounds, text_dbg = detect_boundaries(
            summaries, num_chapters=n, return_debug=True)
        if visual_feats is not None:
            mm_bounds_idx, mm_dbg = detect_boundaries(
                summaries, num_chapters=n, visual_feats=visual_feats,
                alpha=mm_alpha, return_debug=True)
        else:
            mm_bounds_idx, mm_dbg = text_only_bounds, text_dbg
        from segment import group_into_chapters
        chapter_list = group_into_chapters(summaries, mm_bounds_idx, title_fn=title_fn)
        # B1 移植到 fallback 路径：LLM 切分失败时（如 p37 漏 chunk），TextTiling fallback
        # 出的章节也应享受"只看本章 headlines"的标题重写。条件：用户开了 --llm-chapters
        if llm_chapters and chapter_list:
            try:
                from segment_llm import refine_chapter_titles
                outline_for_titles = {"chapters": [
                    {"chunks": ch["indices"]} for ch in chapter_list]}
                refined_titles = refine_chapter_titles(outline_for_titles, summaries,
                                                        lang=resolved_lang)
            except Exception as e:
                print(f"      [llm-chapter-title-fallback] 异常：{e}", flush=True)
                refined_titles = None
            if refined_titles and len(refined_titles) == len(chapter_list):
                for ch, new_title in zip(chapter_list, refined_titles):
                    ch["title_v1"] = ch.get("title", "")
                    ch["title"] = new_title
                print(f"      [llm-chapter-title-fallback] 重写 {len(refined_titles)} 个 fallback 章标题",
                      flush=True)
        # 章节级 abstractive 概述（仅 neural 模式）
        if summarizer == "neural" and chapter_list:
            _apply_chapter_abstracts(chapter_list, llm_chapters, lang=resolved_lang)
        _mark_wrapup_chapter(chapter_list, lang=resolved_lang)
        mm_bounds = [ch["indices"][0] for ch in chapter_list[1:]]
        ablation = {
            "alpha": mm_alpha,
            "text_dists": text_dbg["text_dists"],
            "visual_dists": mm_dbg["visual_dists"],
            "fused_dists": mm_dbg["fused_dists"],
            "depth_scores": mm_dbg["depth_scores"],
            "text_only_boundaries": text_only_bounds,
            "multimodal_boundaries": mm_bounds,
        }
        if visual_feats is not None:
            print(f"      章节切分（多模态 α={mm_alpha}）: {len(chapter_list)} 章，"
                  f"边界 段{[b + 1 for b in mm_bounds]}")
            if text_only_bounds != mm_bounds:
                print(f"      ablation 对比 - 纯文本 段{[b + 1 for b in text_only_bounds]}"
                      f" → 多模态 段{[b + 1 for b in mm_bounds]}")
            else:
                print(f"      ablation - 文本与多模态边界一致")
        else:
            print(f"      章节切分（纯文本）: {len(chapter_list)} 章，边界 段"
                  f"{[b + 1 for b in mm_bounds]}")

    # ===== 双语翻译（章标题 + abstract + chunk headline） =====
    # 给前端 lang toggle 用：把每个文本字段翻译为另一种语言并存为 _zh / _en 后缀字段。
    # llm_chapters 时复用 Qwen（model 已在显存），增量 ~10-20s。
    if llm_chapters and chapter_list and resolved_lang in ("zh", "en"):
        tgt_lang = "en" if resolved_lang == "zh" else "zh"
        src_lang = resolved_lang
        try:
            from segment_llm import translate_bilingual
            # 1) 章标题
            titles = [ch.get("title", "") for ch in chapter_list]
            t_titles = translate_bilingual(titles, src_lang, tgt_lang) if any(titles) else None
            if t_titles and len(t_titles) == len(chapter_list):
                for ch, t in zip(chapter_list, t_titles):
                    ch[f"title_{src_lang}"] = ch.get("title", "")
                    ch[f"title_{tgt_lang}"] = t
            # 2) 章 abstract
            abstracts = [ch.get("abstract", "") for ch in chapter_list]
            if any(abstracts):
                t_abs = translate_bilingual(abstracts, src_lang, tgt_lang)
                if t_abs and len(t_abs) == len(chapter_list):
                    for ch, t in zip(chapter_list, t_abs):
                        ch[f"abstract_{src_lang}"] = ch.get("abstract", "")
                        ch[f"abstract_{tgt_lang}"] = t
            # 3) chunk headlines
            headlines = [c.get("headline", "") for c in summaries]
            if any(headlines):
                t_hls = translate_bilingual(headlines, src_lang, tgt_lang)
                if t_hls and len(t_hls) == len(summaries):
                    for c, t in zip(summaries, t_hls):
                        c[f"headline_{src_lang}"] = c.get("headline", "")
                        c[f"headline_{tgt_lang}"] = t
            print(f"      [bilingual] 双语字段填充完成 ({src_lang}<->{tgt_lang})", flush=True)
        except Exception as e:
            print(f"      [bilingual] 翻译异常：{e}（跳过，前端 fallback 单语）", flush=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = _output_stem(audio, tag, summarizer, chunker, chunk_chars,
                         keyframes=keyframes, vlm_captions=vlm_captions)
    (OUTPUT_DIR / f"{stem}.summary.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if chapter_list:
        # chapters 序列化时不能直接 dump（含原 chunk 引用），写一份精简版
        def _slim_ch(ch: dict) -> dict:
            s = {"title": ch["title"], "start": ch["start"], "end": ch["end"],
                 "indices": ch["indices"], "abstract": ch.get("abstract", "")}
            # 双语字段（pipeline 末段 translate_bilingual 填的；缺也兼容老 schema）
            for k in ("title_zh", "title_en", "abstract_zh", "abstract_en"):
                if ch.get(k):
                    s[k] = ch[k]
            children = ch.get("children")
            if children:
                s["children"] = [_slim_ch(sub) for sub in children]
            return s
        slim = [_slim_ch(ch) for ch in chapter_list]
        # 给 ablation 加上切分路径元数据（供 aggregate_eval.py / 论文附录 B 用）
        if ablation is None:
            ablation = {}
        ablation["seg_meta"] = seg_meta
        ablation["duration"] = asr_result.get("duration")
        ablation["n_chunks"] = len(summaries)
        ablation["lang"] = resolved_lang
        ablation["keyframes"] = keyframes  # 区分 mm vs 纯文本路径
        ablation["vlm_captions"] = vlm_captions  # 区分 VLM caption vs CLIP sim
        # 用户开了 vlm_captions 但 redundancy 太高被降级时 captions_used = False
        ablation["vlm_captions_used"] = vlm_captions and visual_captions_for_llm is not None
        # 二次门控诊断
        if vlm_captions:
            ablation["vlm_max_prefix_run"] = vl_max_prefix_run
            ablation["vlm_degraded_reason"] = vl_degraded_reason
        ablation["n_chapters"] = len(chapter_list)
        ablation["max_chunks_per_chapter"] = max(len(c["indices"]) for c in chapter_list)
        ablation["has_wrapup"] = any(
            "本节复习" in c.get("title", "") or "Recap" in c.get("title", "")
            for c in chapter_list)
        payload = {"chapters": slim, "ablation": ablation}
        (OUTPUT_DIR / f"{stem}.chapters.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2,
                       default=lambda x: float(x) if hasattr(x, "item") else None),
            encoding="utf-8"
        )
    md_path = OUTPUT_DIR / f"{stem}.md"
    md_title = stem
    md_meta = _load_meta_safe(META_DIR / f"{video.stem}.meta.json")
    if md_meta is not None:
        md_title = md_meta.get("title", stem)
    md_path.write_text(to_markdown(summaries, title=md_title, chapters=chapter_list,
                                   keyframe_rel_prefix=kf_rel_prefix,
                                   learning_mode=learning_mode,
                                   confidence_threshold=confidence_threshold,
                                   lang=resolved_lang),
                       encoding="utf-8")

    print(f"\n[OK] 完成! 笔记: {md_path}")
    return md_path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("source", help="视频 URL，或本地文件路径（搭配 --local）")
    p.add_argument("--local", action="store_true", help="source 是本地视频文件")
    p.add_argument("--chunk-chars", type=int, default=800)
    p.add_argument("--model", default="large-v3",
                   help="faster-whisper 模型：tiny/base/small/medium/large-v3")
    p.add_argument("--ratio", type=float, default=0.25,
                   help="抽取式摘要目标压缩比（摘要字数 / 原文字数）")
    p.add_argument("--force-asr", action="store_true",
                   help="忽略已有的 ASR JSON 缓存，强制重跑")
    p.add_argument("--summarizer", choices=("extractive", "neural"),
                   default="extractive",
                   help="extractive=jieba 抽取式；neural=Randeng-Pegasus 生成式")
    p.add_argument("--chapters", type=int, default=None, nargs="?", const=-1,
                   help="启用章节切分。不带值=自动决定章节数；--chapters 4=强制 4 章")
    p.add_argument("--term", action="append", default=[], metavar="WRONG=RIGHT",
                   help="ASR 后处理术语替换，可多次。例如 --term '主绘画=主会话'")
    p.add_argument("--keyframes", action="store_true",
                   help="给每段抽一张 Chinese-CLIP 关键帧，嵌入到 md")
    p.add_argument("--mm-alpha", type=float, default=0.3,
                   help="多模态章节切分中视觉权重 (0=纯文本, 1.0=纯视觉)。"
                        "默认 0.3 让视觉做 tie-breaking 但不主导。"
                        "只有 --keyframes + --chapters 同时启用时生效")
    p.add_argument("--chunker", choices=("chars", "texttile"), default="chars",
                   help="chars=按字符数硬切（baseline）；"
                        "texttile=按 segment 间隙 keyword Jaccard 找语义跳变点切")
    p.add_argument("--learning-mode", dest="learning_mode",
                   action="store_true", default=True,
                   help="md 加入顶部摘要卡 / TOC / 知识点速览 / 术语表 / 章末小结"
                        "（默认开，学习类视频专属元素）")
    p.add_argument("--no-learning-mode", dest="learning_mode",
                   action="store_false",
                   help="关闭学习类元素，输出最朴素 md")
    p.add_argument("--dedupe-asr", dest="dedupe_asr",
                   action="store_true", default=True,
                   help="去除 ASR 连续重复段（默认开，应对 whisper 长视频卡片回路）")
    p.add_argument("--no-dedupe-asr", dest="dedupe_asr",
                   action="store_false",
                   help="关闭 ASR 重复段去重（ablation/调试用）")
    p.add_argument("--confidence-threshold", type=float, default=0.5,
                   help="md 原文区给 confidence < threshold 的 segment 加 [?] 标记。"
                        "默认 0.5（影视飓风 2.9%% 段被标），0 关闭；"
                        "旧 ASR cache 没 confidence 字段，会 graceful 退化为不标")
    p.add_argument("--llm-chapters", action="store_true",
                   help="用 Qwen2.5-7B-AWQ 做层级章节切分（替代 TextTiling）。"
                        "需要 models/Qwen2.5-7B-Instruct-AWQ/，~5GB VRAM。"
                        "失败自动 fallback 到 TextTiling")
    p.add_argument("--lang", choices=("auto", "zh", "en"), default="auto",
                   help="视频语言：auto 按 meta 启发式判断，"
                        "zh/en 强制（影响 whisper ASR + Qwen prompt + 关键词提取）")
    p.add_argument("--vlm-captions", action="store_true",
                   help="--keyframes + --llm-chapters 同时启用时，先调 Qwen2.5-VL "
                        "给每个关键帧生 1 句 caption，喂 segment LLM 做更精准切分。"
                        "需要 models/Qwen2.5-VL-7B-Instruct-AWQ/（~5GB），跟 instruct "
                        "互斥占 VRAM，跑完会 free 让 instruct 加载回来。")
    args = p.parse_args()
    extra_terms = {}
    for t in args.term:
        if "=" in t:
            k, v = t.split("=", 1)
            extra_terms[k] = v
    run(args.source, is_local=args.local, chunk_chars=args.chunk_chars,
        model_size=args.model, target_ratio=args.ratio, force_asr=args.force_asr,
        summarizer=args.summarizer, chapters=args.chapters, extra_terms=extra_terms,
        keyframes=args.keyframes, mm_alpha=args.mm_alpha, chunker=args.chunker,
        learning_mode=args.learning_mode, dedupe_asr=args.dedupe_asr,
        confidence_threshold=args.confidence_threshold,
        llm_chapters=args.llm_chapters, lang=args.lang,
        vlm_captions=args.vlm_captions)


if __name__ == "__main__":
    main()
