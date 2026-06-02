"""端到端：URL or 本地视频 → Markdown 笔记。

结构：
  run() 是 orchestrator，按顺序串 18 个 _stage_xxx(cfg, state) 阶段。
  PipelineConfig 是不可变入参（dataclass）；PipelineState 是 rolling 状态。
  各 stage 互相不传参数，只通过 state.* 读写共享变量。
"""
from __future__ import annotations

import argparse
import faulthandler
import json
import sys
from dataclasses import dataclass, field
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
from summarize import chunk_by_chars, chunk_by_texttile, split_oversize_chunks, to_markdown
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
    # 王道计组系列（BV1BE411D7ii）：IO 控制方式 / 中断系统 / DMA 等
    "computer_org": ("计算机组成原理", "计组", "中断系统", "DMA",
                     "IO接口", "I/O接口", "IO控制", "总线",
                     "存储器层次", "微指令", "Cache", "高速缓存",
                     "指令系统", "CPU时钟"),
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
    "computer_org": ["中断", "中断系统", "中断向量", "DMA",
                     "存储器", "高速缓存", "微指令", "总线",
                     "程序查询", "中断服务程序"],
}

# 全局 ASR 后处理：所有中文视频都 apply（whisper 偶发繁体输出，跨 domain 通用）
# 7 视频通查发现繁体字大面积渗入（議=20/個=11/機=10/絡=6/協=4 等）
# 这些字简体里有等价单字，全局替换安全（不会破坏简体合法用法）
_GLOBAL_CORRECTIONS: dict[str, str] = {
    "報文": "报文",
    "導致": "导致",
    "網": "网",     # "网" 单字
    "議": "议",     # 協議 / 议题
    "協": "协",
    "絡": "络",     # 网络 / 联络
    "個": "个",
    "機": "机",     # 机器 / 主机
    "電": "电",
    "腦": "脑",
    "邊": "边",     # 边界 / 一边
    "會": "会",
    "經": "经",
    "過": "过",
    "間": "间",
    "為": "为",
    "當": "当",
    "應": "应",
    "對": "对",
    "單": "单",
    "說": "说",
    "實": "实",
    "進": "进",
    "處": "处",
    "從": "从",
    "結": "结",
    "與": "与",
    "構": "构",
    "稱": "称",
    "時": "时",
    "資": "资",
    "訊": "讯",
    "確": "确",   # p81 实测"確認"→"确认"漏，4 次
    "釈": "释",   # p81 "解釈"→"解释"
    # 2026-05-26 leakage 扫描发现的 unambiguous patterns（中文里几乎不构词）
    # 这些 char 组合在所有 domain 都是 ASR 错字，全局安全替换：
    "中斷": "中断",   # 繁体残留 (王道计组 p68 实测 50+ 次)
    "中斩": "中断",   # 同音字 (p70 实测 19 次)
    "中斧": "中断",   # 同音字
    "中斜": "中断",   # 同音字
    "程庇": "程序",   # 同音字，不构词
    "双脚线": "双绞线",  # 计网 p38 实测 69 次，meta 缺时 fallback
    "屏屏": "屏蔽",   # 王道 OS 实测
    "介绅": "介绍",   # 同音字
    "地坝": "地址",   # 计网 p51/p72/p93 + 计组 p66/p68 跨域出现，不构词 safe
    # 注意：曾尝试 "服务程"→"服务程序"，但会把已正确的"服务程序"扩成
    # "服务程序序"（非幂等）。改用具体 ASR 错字变体（见 computer_org 域字典）
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
        # ACK 也常被识成裸 "AK"：p80 "AK段"×3 / "AK等于1"、p79 "有AK,SYN和FIN"
        # （列举 ACK/SYN/FIN 三个标志位）。裸 "AK" 用 plain-substring 替换会误伤
        # PEAK/BREAK（"峰值速率 peak"）等英文词，故锚定到带中文/标志名的右邻上下文：
        # "AK段"/"AK等于" 含中文字符，英文词不可能含；"AK,SYN" 是 ACK,SYN 标志列举
        # 习语，无英文词含此串。idempotent: 三个 wrong 均非各自 right 的连续子串
        "AK段": "ACK段",
        "AK等于": "ACK等于",
        "AK,SYN": "ACK,SYN",
        # p78 (TCP 报文段) 实测："校验和" 6 处错听成"校验核"。"校验核"
        # 非术语，应回"校验和"（TCP/UDP 首部字段标准译名）
        "校验核": "校验和",
        # p85 偶发繁体（whisper 偶尔切到繁体语言模型）：報文/導致 各 1-4 次
        # 计网域没有理由用繁体，统一回简体
        # 注：繁简字符映射已搬到 _GLOBAL_CORRECTIONS（always apply）；这里
        # 保留 multi-char 网络专属繁简映射以便维护
        "网路": "网络",
        "網路": "网络",
        "網絡": "网络",
        # p64 OSPF / p65 链路状态：路由协议族系统性 ASR 错字
        # 实测 p64 红犯=13 / p65 红犯=9：whisper 把"洪泛"(flooding)听成"红犯"
        # "红犯"在中文非常用词，全局替换安全
        "红犯": "洪泛",
        # 实测 p64 全值=22 / p65 全值=7 / p57 全值=3：whisper 把"权值"(link cost)
        # 听成"全值"。"全值"在计网域无合法义（路由全是"权值/代价/带宽"）
        "全值": "权值",
        # 实测 p65 临接=6 / p64 临接=3：whisper 把"邻接"(adjacency)听成"临接"
        # OSPF/路由协议域"临接"无合法义，"邻接表/邻接路由器"是标准术语
        "临接": "邻接",
        # 实测 p58 协定=6 / p64 协定=4：whisper/Qwen 偶把"协议"(protocol)写成"协定"
        # 计网域虽然"协定"勉强可解但标准译名是"协议"，统一回 "协议"
        # 注意：限定计网域字典里，避免破坏"国际协定/贸易协定"等合法用法
        "协定": "协议",
        # p65 实测：whisper 偶发繁体字（"探測" 5+ 次）+ "探策" 错听 → 应为"探测"
        "探測": "探测",
        "探策": "探测",
        # p65 实测："路由器" 被识成"陆游器"（"陆游" + "器"）3+ 次。"陆游器"
        # 非术语，"路由器" 是计网标准词
        "陆游器": "路由器",
        "路後": "路由",         # "最矮的路後" → "最短的路由"
        # 2026-05-25 8 视频通查: "路由" 还有 6 种 ASR 变体，每种 2-15 次
        # "路游"=28 / "路有"=17 / "路约"=2 / "路渥"=1 / "路坠"=1 / "路秒"=1
        # 这些 2-char 组合在中文里几乎不是常用词，全局替换安全
        "路游": "路由",
        "路有": "路由",
        "路约": "路由",
        "路渥": "路由",
        "路坠": "路由",
        "路秒": "路由",
        # "报文" 也偶发错听成"报闻"(p60=3)。"报闻"非常用词
        "报闻": "报文",
        # p81 (TCP 可靠传输) 实测：whisper 把"数据"听成"数捷/数损"，"可靠"
        # 听成"可革/可靡/可靴"，"接收方"听成"接收房"，"缓冲区"听成"缓充区"
        # 这些都非中文常用词，计网域全局替换安全
        "数捷": "数据",
        "数损": "数据",
        "可革": "可靠",
        "可靡": "可靠",   # LLM-asr-fix 也能抓但作 substring 兜底
        "可靴": "可靠",
        "接收房": "接收方",
        "缓充区": "缓冲区",
        "缓冲": "缓冲",   # 占位，确保 "缓充" 不会被吃成 "缓冲"
        # "流浪控制" 是 TCP "流量控制" 错听（p81 实测）
        "流浪控制": "流量控制",
        # p65 实测：whisper 把"自治系统"听成"自制系统" 4+ 次。"自制系统"是合法
        # 词（"自制产品/自制零件"），但 OSPF/路由域里讲的是 Autonomous System
        # → 标准译名"自治系统"
        "自制系统": "自治系统",
        "自制": "自治",         # 限定计网域字典，不影响普通"自制"用法
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
    "computer_org": {
        # 王道计组 BV1BE411D7ii p68 (中断系统, 35 chunks) 实测：whisper 把
        # "中断"听成"中段"。p68 ch4 章标题"向量与中段处理"渗透。
        # 裸"中段→中断"会破坏合法用法（"文章中段/比赛中段"），所以用带上下文
        # 的 substring（"中段处理/中段服务"等组合在合法中文里不出现）
        "中段处理": "中断处理",
        "中段服务": "中断服务",
        "中段请求": "中断请求",
        "中段响应": "中断响应",
        "中段向量": "中断向量",
        "中段优先级": "中断优先级",
        "中段系统": "中断系统",
        "中段引指令": "中断引指令",
        "中段元": "中断源",      # "中断源" 也常被听成"中段元"
        "中断元": "中断源",      # "源"→"元"
        "内中段": "内中断",
        "外中段": "外中断",
        "硬中段": "硬中断",
        "软中段": "软中断",
        "多重中段": "多重中断",
        "屏蔽中段": "屏蔽中断",
        "关中段": "关中断",      # "关中断" 是 CPU 状态切换标准操作
        "开中段": "开中断",
        # p67 (IO 控制方式) 实测：whisper 把"传输"听成"传书" (chunk 0/15 中招)，
        # 跟 network 域里的 "传书" 冲突，已在 network 同条目；这里复用计组语境
        # 防 detect_domains 命中 network 之外 + 计组场景漏掉
        "数据传书": "数据传输",
        "传书速率": "传输速率",
        # p70 (DMA) 偶发：whisper 把"DMA"听成"DM 啊"或"D M A"，标准化
        "DM啊": "DMA",
        "D M A": "DMA",
        # 2026-05-26 leakage 扫描发现：计组域 ASR 系统性把"中断"听成"中段"
        # p68 53 次、p70 7 次、p66 10 次、p69 4 次 — 全部需要修
        # 已有变体 "中段处理/中段服务/..." 不够，因为还有"中段的/中段时"等更长
        # 上下文形式。在 computer_org 域里"中段"无合法用法（不讨论文章中段），
        # 直接裸替换 safe
        "中段": "中断",
        # 王道 OS P/V 操作场景：whisper 把 "PP" 听成"屁屁"
        # 注：屁屁 也是儿语词，限定 computer_org/os 域 safe；不放 _GLOBAL
        "屁屁": "PP",
        "屁屁操作": "PV操作",  # 偶发整词错听
        # 计组 p68 实测："中断服务程序" 系列尾字错听变体（4 字一致后只末字异）
        # "服务程序" 23 次正确不动；下面是具体错字 → 修
        # 不放 _GLOBAL 因为"服务程" 在其他域可能合法（虽然罕见）
        "服务程庇": "服务程序",   # p68 实测 4 次
        "服务程庆": "服务程序",
        "服务程庫": "服务程序",
        "服务程庈": "服务程序",
        # p68 实测：whisper 把"任务"听成"任劳"（6 处），上下文如
        # "这两个任劳基本上是同时完成的" / "第三个任劳就是引出中断服务程序"
        # 注意：会同时把"任劳任怨"成语吃成"任务任怨"。current corpus 0 出现
        # 该成语；若未来计组讲师引用，需在 apply_term_corrections 加 idiom
        # 两遍保护（sentinel pre/post-pass），目前 trade-off 接受
        "任劳": "任务",
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

    # 全局繁简字符映射（任何中文视频都 apply）
    corrections.update(_GLOBAL_CORRECTIONS)
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
                              lang: str = "zh",
                              category: str = "teaching") -> None:
    """给每章填 `abstract` 字段。`--llm-chapters` 时优先 Qwen 生成 1-2 句 prose；
    Qwen 失败 / 关闭时 fallback 到 `summarize_chapter`（拼 headlines）。
    顶层 + 子章节都处理；子章节当前用 fallback（Qwen 批量逻辑仅做顶层）。

    category=vlog/talk 时切到 vlog 简介 prompt（"本段..."开头），其它走教学版"本章..."。"""
    abstracts = None
    if llm_chapters:
        try:
            from segment_llm import generate_chapter_abstracts
            abstracts = generate_chapter_abstracts(chapter_list, lang=lang,
                                                    category=category)
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


def _apply_chapter_recaps(chapter_list: list, llm_chapters: bool,
                          lang: str = "zh",
                          category: str = "teaching") -> None:
    """给每章填 `recap` 字段（3-5 条 markdown bullet 复习要点）。

    仅对 teaching / popsci 类视频生成（vlog/talk 上 recap 无意义）。
    失败/关闭时不填，summarize.to_markdown 会 fallback 到抽取式 chapter_recap。
    """
    if not llm_chapters:
        return
    if category in ("vlog", "talk"):
        return
    try:
        from segment_llm import generate_chapter_recaps
        recaps = generate_chapter_recaps(chapter_list, lang=lang)
    except Exception as e:
        print(f"      [llm-chapter-recap] 异常：{e}，回退抽取式 recap",
              flush=True)
        return
    if recaps and len(recaps) == len(chapter_list):
        for ch, rc in zip(chapter_list, recaps):
            ch["recap"] = rc
            first_line = rc.split("\n", 1)[0][:60]
            print(f"      [chapter recap] L1 -> {first_line}", flush=True)
    elif recaps:
        # len mismatch: 之前 silent drop 让 BV19E411D78Q_p81 整批无 recap 但
        # 跑批 stdout 看不到原因。明确报出来，下次定位 generate_chapter_recaps
        # 哪步漏数（_parse_titles_array 截断 / I7 fallback per 计算 / LLM 漏章）
        print(f"      [llm-chapter-recap] ⚠️ len mismatch: 拿到 {len(recaps)} "
              f"个 recap vs {len(chapter_list)} 章，整批丢弃 → fallback 抽取式",
              flush=True)
    else:
        # recaps is None/empty — generate_chapter_recaps 内部已 print parse 失败 raw
        print(f"      [llm-chapter-recap] ⚠️ 返回空，fallback 抽取式",
              flush=True)


def _apply_chapter_quizzes(chapter_list: list, llm_chapters: bool,
                           lang: str = "zh",
                           category: str = "teaching") -> None:
    """给每章填 `quiz` 字段（2-3 道自测题 dict 列表）。

    仅对 teaching / popsci 类视频生成（vlog/talk 上 quiz 概念无意义）。
    失败/关闭时不填，summarize.to_markdown 见 quiz=None 跳过 quiz 区块。
    """
    if not llm_chapters:
        return
    if category in ("vlog", "talk"):
        return
    try:
        from segment_llm import generate_chapter_quizzes
        quizzes = generate_chapter_quizzes(chapter_list, lang=lang)
    except Exception as e:
        print(f"      [llm-chapter-quiz] 异常：{e}，跳过 quiz", flush=True)
        return
    if quizzes and len(quizzes) == len(chapter_list):
        for ch, qz in zip(chapter_list, quizzes):
            ch["quiz"] = qz  # {"questions": [...]}
            nq = len(qz.get("questions", []))
            print(f"      [chapter quiz] {nq} questions", flush=True)


def _apply_doc_overview(chapter_list: list, llm_chapters: bool,
                        video_title: str = "",
                        lang: str = "zh",
                        category: str = "teaching") -> dict | None:
    """生成文档级「全文总结」（散文概览 + 你将学到要点），喂各章 title+abstract。

    仅对 teaching / popsci 类视频生成（vlog/talk 上整篇 takeaways 无意义）。
    失败/关闭时返回 None，前端无 overview 时不渲染 hero。"""
    if not llm_chapters:
        return None
    if category in ("vlog", "talk"):
        return None
    try:
        from segment_llm import generate_doc_overview
        ov = generate_doc_overview(chapter_list, video_title=video_title, lang=lang)
    except Exception as e:
        print(f"      [doc-overview] 异常：{e}，跳过全文总结", flush=True)
        return None
    if ov and ov.get("summary"):
        nt = len(ov.get("takeaways", []))
        print(f"      [doc-overview] summary {len(ov['summary'])} 字 / "
              f"{nt} takeaways", flush=True)
        return ov
    print(f"      [doc-overview] ⚠️ 返回空，跳过全文总结", flush=True)
    return None


@dataclass
class PipelineConfig:
    """run() 的 17 个入参拢成一个不可变 record，避免到处传 kw。"""
    source: str
    is_local: bool = False
    chunk_chars: int = 800
    model_size: str = "large-v3"
    target_ratio: float = 0.25
    force_asr: bool = False
    summarizer: str = "extractive"
    chapters: int | None = None
    extra_terms: dict[str, str] | None = None
    keyframes: bool = False
    mm_alpha: float = 0.3
    chunker: str = "chars"
    learning_mode: bool = True
    dedupe_asr: bool = True
    llm_chapters: bool = False
    confidence_threshold: float = 0.5
    lang: str = "auto"
    vlm_captions: bool = False
    quality: str = "best"
    force_outline: str | None = None


@dataclass
class PipelineState:
    """阶段函数间共享的 rolling 状态。"""
    video: Path | None = None
    audio: Path | None = None
    meta: dict | None = None
    meta_for_terms: dict | None = None
    resolved_lang: str = "zh"
    asr_prompt: str | None = None
    corrections: dict[str, str] = field(default_factory=dict)
    asr_result: dict | None = None
    tag: str = ""
    chunks: list | None = None
    chunker_desc: str = ""
    summaries: list | None = None
    visual_feats: object = None
    kf_rel_prefix: str = ""
    visual_sims_for_llm: list | None = None
    visual_captions_for_llm: list | None = None
    vl_max_prefix_run: int | None = None
    vl_generic_ratio: float | None = None
    vl_degraded_reason: str | None = None
    inferred_category: str = "teaching"
    chapter_list: list | None = None
    doc_overview: dict | None = None
    ablation: dict | None = None
    seg_meta: dict = field(default_factory=lambda: {
        "method": None,
        "llm_attempts": 0,
        "llm_pass_via": None,
        "llm_repair_used": [],
        "llm_fail_reasons": [],
        "fallback_used": False,
    })
    md_meta: dict | None = None
    md_path: Path | None = None


# ============ Stage 1: 准备视频（[1/4] 下载或定位本地文件） ============
def _stage_prepare_video(cfg: PipelineConfig, state: PipelineState) -> None:
    print(f"[1/4] 准备视频: {cfg.source}")
    if cfg.is_local:
        video = Path(cfg.source)
        if not video.exists():
            raise FileNotFoundError(video)
    else:
        state.meta = fetch_metadata(cfg.source)
        video = download_video(cfg.source, quality=cfg.quality)
        # 保存 metadata 方便后续展示真实标题等
        META_DIR.mkdir(parents=True, exist_ok=True)
        slim_meta = {k: state.meta.get(k) for k in
                     ("id", "title", "uploader", "duration", "webpage_url", "description")}
        (META_DIR / f"{video.stem}.meta.json").write_text(
            json.dumps(slim_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    state.video = video
    print(f"      video = {video}")


# ============ Stage 2: 抽音频（[2/4]） ============
def _stage_extract_audio(cfg: PipelineConfig, state: PipelineState) -> None:
    print("[2/4] 抽取音频...")
    assert state.video is not None
    state.audio = extract_audio(state.video)
    print(f"      audio = {state.audio}")


# ============ Stage 3: 构建 ASR 上下文（lang/prompt/术语校正） ============
def _stage_build_asr_context(cfg: PipelineConfig, state: PipelineState) -> None:
    assert state.video is not None
    meta_path = META_DIR / f"{state.video.stem}.meta.json"
    state.meta_for_terms = _load_meta_safe(meta_path) or state.meta

    # 语言检测：auto 模式按 meta 启发式判断；用户显式传 zh/en 时尊重
    state.resolved_lang = (cfg.lang if cfg.lang in ("zh", "en")
                           else _detect_lang(state.meta_for_terms))
    print(f"      [lang] 视频语言: {state.resolved_lang}"
          + (f" (auto-detected)" if cfg.lang == "auto" else ""))

    if state.meta_for_terms is not None:
        state.asr_prompt = _build_asr_prompt(state.meta_for_terms,
                                              lang=state.resolved_lang)

    if state.meta_for_terms:
        state.corrections.update(_build_term_corrections(state.meta_for_terms))
    if cfg.extra_terms:
        state.corrections.update(cfg.extra_terms)


# ============ Stage 4: ASR + 术语校正 + dedupe ============
def _stage_asr(cfg: PipelineConfig, state: PipelineState) -> None:
    assert state.audio is not None
    state.tag = _tag_for_model(cfg.model_size)
    asr_cache = OUTPUT_DIR / f"{state.audio.stem}.{state.tag}.asr.json"
    if asr_cache.exists() and not cfg.force_asr:
        print(f"[3/4] 命中 ASR 缓存: {asr_cache}")
        asr_result = json.loads(asr_cache.read_text(encoding="utf-8"))
        # 旧 cache 没 word_timestamps / confidence 字段：用户若开了 --confidence-threshold>0
        # 不会报错（render 退化），但低置信标记也不会出现。提示用户用 --force-asr 升级 cache。
        if cfg.confidence_threshold > 0 and asr_result.get("segments"):
            first = asr_result["segments"][0]
            if "confidence" not in first:
                print(f"      [hint] cache 早于 confidence 落地（无 segments[].confidence），"
                      f"--confidence-threshold={cfg.confidence_threshold} 不会有效。"
                      f"加 --force-asr 重跑 ASR 升级 cache schema（~30s/视频）")
    else:
        print("[3/4] 语音识别（首次会下载 ~3GB 模型）...")
        asr_result = transcribe(state.audio, model_size=cfg.model_size,
                                language=state.resolved_lang,
                                initial_prompt=state.asr_prompt)
    verified_lang = _verify_lang(asr_result, state.resolved_lang)
    if verified_lang != state.resolved_lang:
        print(f"      [lang] ASR 实际语言为 {verified_lang}，"
              f"覆盖 metadata 判断 {state.resolved_lang}（下游 Qwen 改用 {verified_lang} 模板）")
        state.resolved_lang = verified_lang
    if state.corrections:
        print(f"      ASR 后处理替换 {len(state.corrections)} 条术语: "
              f"{', '.join(list(state.corrections.keys())[:5])}"
              f"{'...' if len(state.corrections) > 5 else ''}")
        asr_result = apply_term_corrections(asr_result, state.corrections)
    if cfg.dedupe_asr:
        asr_result, dd_stats = dedupe_consecutive_segments(asr_result)
        if dd_stats["dropped"]:
            print(f"      ASR 连续重复段去重: 丢弃 {dd_stats['dropped']} 段，"
                  f"合并 {len(dd_stats['runs'])} 个 run")
            for r in dd_stats["runs"][:3]:
                print(f"        run x{r['run_len']} @ {r['start']:.1f}s: "
                      f"{r['text']}")
    print(f"      duration={asr_result['duration']:.1f}s, "
          f"segments={len(asr_result['segments'])}")
    state.asr_result = asr_result


# ============ Stage 5: chunk + 超长硬切 ============
def _stage_chunk(cfg: PipelineConfig, state: PipelineState) -> None:
    assert state.asr_result is not None
    if cfg.chunker == "texttile":
        chunks = chunk_by_texttile(state.asr_result["segments"],
                                   target_chunk_chars=cfg.chunk_chars)
        chunker_desc = f"chunker=texttile target≈{cfg.chunk_chars}c"
    else:
        chunks = chunk_by_chars(state.asr_result["segments"],
                                chunk_chars=cfg.chunk_chars)
        chunker_desc = f"chunker=chars chunk_chars={cfg.chunk_chars}"

    # 后处理：硬切超长 chunk（vlog/talk 类视频 chunker 不敏感时兜底）
    # 阈值 120s — 教学视频 cc=400/600 公式下几乎不会触发，vlog 触发率高
    n_before = len(chunks)
    chunks, split_log = split_oversize_chunks(chunks, max_dur_sec=120.0,
                                              min_split_chars=400)
    if len(chunks) > n_before:
        kept = [s for s in split_log if not s.get("skipped")]
        print(f"      [split] 硬切超长 chunk: {n_before} → {len(chunks)} chunks "
              f"({len(kept)} 刀)", flush=True)
        for s in kept[:5]:
            print(f"        chunk #{s['idx']} dur={s['orig_dur']}s "
                  f"chars={s['orig_chars']} → 切在 {s['split_at']}s "
                  f"({s['left_dur']}s | {s['right_dur']}s)", flush=True)
    state.chunks = chunks
    state.chunker_desc = chunker_desc


# ============ Stage 6: summarize chunks（neural vs extractive） ============
def _stage_summarize(cfg: PipelineConfig, state: PipelineState) -> None:
    assert state.chunks is not None
    if cfg.summarizer == "neural" and cfg.llm_chapters:
        # Pegasus 输出 100% 被 Qwen 覆盖，--llm-chapters 时直接跳过节省 ~30s + ~1GB VRAM
        print(f"[4/4] {state.chunker_desc}, {len(state.chunks)} chunks + 抽取式 summary（Qwen 后生 headline）...")
        from summarize_neural import summarize_chunks_no_headline
        summaries = summarize_chunks_no_headline(state.chunks,
                                                  target_ratio=cfg.target_ratio,
                                                  lang=state.resolved_lang)
    elif cfg.summarizer == "neural":
        print(f"[4/4] {state.chunker_desc}, {len(state.chunks)} chunks + 神经摘要（Pegasus-238M）...")
        from summarize_neural import summarize_chunks as summarize_chunks_neural
        summaries = summarize_chunks_neural(state.chunks, lang=state.resolved_lang)
    else:
        print(f"[4/4] {state.chunker_desc}, {len(state.chunks)} chunks + 抽取式摘要（ratio={cfg.target_ratio}）...")
        summaries = summarize_chunks_extractive(state.chunks,
                                                 target_ratio=cfg.target_ratio,
                                                 lang=state.resolved_lang)
    state.summaries = summaries


# ============ Stage 7: Qwen ASR 同音字校错（chunk-level 上下文） ============
def _stage_qwen_asr_fix(cfg: PipelineConfig, state: PipelineState) -> None:
    # 跑在 headline 生成 / 章节切分前，把"双脚线→双绞线"这类隐式错字（substring
    # corrections map 救不了的）救回。需要 chunk 关键词作上下文 cue，所以放在
    # summarize 之后。Pegasus 模式也支持（不绑 llm_chapters，但 LLM 已用于章节就
    # 没有额外 VRAM 成本）。
    if not (cfg.llm_chapters and cfg.summarizer == "neural"
            and state.summaries and state.resolved_lang != "en"):
        return
    # 英文视频跳过 qwen_asr_fix（专攻中文同音字，对英文 ASR 无意义且会产生
    # 大量 false positive 被防御过滤掉，纯浪费一次 LLM 调用 ~20s）
    try:
        from segment_llm import qwen_asr_fix
        asr_fixes = qwen_asr_fix(state.summaries)
    except Exception as e:
        print(f"      [llm-asr-fix] 异常：{e}", flush=True)
        asr_fixes = {}
    if asr_fixes:
        # 按 key 长度降序避免短词先吃长词（与 apply_term_corrections 一致）
        items = sorted(asr_fixes.items(), key=lambda kv: -len(kv[0]))
        for chunk in state.summaries:
            for wrong, right in items:
                chunk["text"] = chunk["text"].replace(wrong, right)
                for seg in chunk.get("segments", []) or []:
                    seg["text"] = seg["text"].replace(wrong, right)
        apply_term_corrections(state.asr_result, asr_fixes)  # 兜底，asr_result 用于 md 原文区
        # 修后重新抽 keywords（jieba 在错字上抓的 keyword 可能误导下游 LLM 切分）
        from summarize import keywords_for
        from summarize_neural import clean_for_summary
        for chunk in state.summaries:
            chunk["keywords"] = keywords_for(clean_for_summary(chunk["text"]))
        print(f"      [llm-asr-fix] 应用 {len(asr_fixes)} 个错字 + 重抽关键词", flush=True)


# ============ Stage 8: keyframes 抽帧 + visual_feats ============
def _stage_keyframes(cfg: PipelineConfig, state: PipelineState) -> None:
    if not cfg.keyframes:
        state.kf_rel_prefix = ""
        return
    from keyframe import extract_keyframes
    video_for_kf = _resolve_video_for_keyframes(state.video)
    if video_for_kf is None:
        print(f"      [keyframes] 跳过：找不到 {state.video} 对应的视频流文件")
        state.kf_rel_prefix = ""
        return
    print(f"      [keyframes] 用视频 {video_for_kf.name} 抽帧 ...")
    # keyframes 目录与 CLIP-only / VLM 路径**共享**（同一段视频两个跑法
    # 帧本身是一样的，只是 caption 不同），所以 kf_dir 不带 .vl 后缀
    kf_dir = OUTPUT_DIR / f"{_output_stem(state.audio, state.tag, cfg.summarizer, cfg.chunker, cfg.chunk_chars, keyframes=True)}.keyframes"
    state.summaries, state.visual_feats = extract_keyframes(
        video_for_kf, state.summaries, kf_dir)
    state.kf_rel_prefix = f"{kf_dir.name}/"


# ============ Stage 9: LLM 重写/生成 chunk headline ============
def _stage_llm_headline(cfg: PipelineConfig, state: PipelineState) -> None:
    # 两种来源：(a) Pegasus 模式有初版 headline → Qwen `refine_headlines` 重写；
    # (b) 无 Pegasus 模式 headline 是空串 → Qwen `generate_headlines` 直接从原文生成。
    if not (cfg.llm_chapters and cfg.summarizer == "neural" and state.summaries):
        return
    has_initial = any((c.get("headline") or "").strip() for c in state.summaries)
    try:
        if has_initial:
            print("[headlines] Qwen 重写 Pegasus 初版 chunk headline ...", flush=True)
            from segment_llm import refine_headlines
            refined = refine_headlines(state.summaries, lang=state.resolved_lang)
        else:
            print("[headlines] Qwen 从原文直接生成 chunk headline ...", flush=True)
            from segment_llm import generate_headlines
            refined = generate_headlines(state.summaries, lang=state.resolved_lang)
    except Exception as e:
        print(f"      [llm-headline] 异常：{e}，保留初版", flush=True)
        refined = None
    if refined and len(refined) == len(state.summaries):
        for c, new_hl in zip(state.summaries, refined):
            c["headline_pegasus"] = c.get("headline", "")  # 留底
            c["headline"] = new_hl
        print(f"      [llm-headline] 填充 {len(refined)} 段 headline", flush=True)


# ============ Stage 10: 视觉相似度 cue（CLIP）→ LLM 切分 ============
def _stage_visual_sims(cfg: PipelineConfig, state: PipelineState) -> None:
    # 多模态信号：keyframes 抽帧时，把相邻 chunk 的 CLIP 视觉相似度送给 LLM 切分
    # 作为额外提示（用作 tie-breaker，文本主题仍是主依据）
    if state.visual_feats is None:
        return
    from segment import visual_adjacent_distances
    v_dists = visual_adjacent_distances(state.visual_feats)
    sims = [(1.0 - d) if d is not None else None for d in v_dists]
    state.visual_sims_for_llm = sims
    print(f"      [mm-llm] 视觉相似度 cue 启用："
          f"{sum(1 for s in sims if s is not None)}/{len(sims)} 段间隙有信号",
          flush=True)


# ============ Stage 11: VLM caption（Qwen2.5-VL） ============
def _stage_vlm_captions(cfg: PipelineConfig, state: PipelineState) -> None:
    # 给 LLM 切分提供比浮点 sim 信息密度高 10x 的视觉 cue。需 --keyframes + --vlm-captions。
    # VRAM 占用与 Qwen2.5-7B-Instruct-AWQ 相近，跑完会 free_vl_model() 让 instruct 加载回来。
    if not (cfg.vlm_captions and cfg.keyframes and state.summaries):
        return
    # 自适应规则（三层）：
    # 外层 - n_chunks ≤ 15：短/动态视频画面信息密度高，caption 切更细（OS p37 实测）
    # 外层 - n_chunks > 15：长视频画面 pattern 单一，caption 反诱发 catch-all（BV1S6kQBNEJq）
    # 中层 - generic_ratio ≥ 阈值：caption 多为"讲师/讨论/演示/explains"等通用动词，
    #        前缀不同但语义都是"画面在讲 X"，LLM 易合并漏 chunks（BV1S6kQBNEJq AI Agent
    #        教程实测高 generic_ratio + vl-rescue 命中）；提前抓住可省一次 LLM attempt
    # 内层 - caption 前缀长 run 检测：即使前两层通过，若 captions 出现 ≥4 个共享 10 字
    #        前缀的连续 run 且剩余 chunks ≥ 3（p44 实测 5/9 chunks 共享"以太网交换机
    #        的自学习功能"），LLM 误以为"同主题需合并"漏 chunks；OS p37 max_run=4
    #        但 n-run=1 不触发内层，保留增益
    CAPTION_MAX_CHUNKS = 15
    CAPTION_PREFIX_K = 10
    CAPTION_PREFIX_RUN_MIN = 4
    CAPTION_OTHER_MIN = 3
    CAPTION_GENERIC_MAX = 0.65  # generic 动词占比 ≥ 此值 → 降级
    try:
        from caption_vl import caption_keyframes, caption_redundancy, free_vl_model
        print("[vl-cap] Qwen2.5-VL 给关键帧生 caption ...", flush=True)
        captions = caption_keyframes(state.summaries, lang=state.resolved_lang)
        free_vl_model()
        # 把 caption 写回 chunk dict 让 summary.json / 前端 / 论文 §5.4 截图能看
        if captions and len(captions) == len(state.summaries):
            for c, cap in zip(state.summaries, captions):
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
        state.vl_max_prefix_run = best
        print(f"      [vl-cap] n_cap={n_cap}, jaccard_mean={jaccard:.2f}, "
              f"generic_ratio={generic:.2f}, max_prefix_run={best}/{len(captions)}",
              flush=True)
        # 记录 generic_ratio 供 ablation/§5.4 用
        state.vl_generic_ratio = generic
        # 外层判定：n_chunks 阈值
        if len(state.summaries) > CAPTION_MAX_CHUNKS:
            state.vl_degraded_reason = "n_chunks_gt_15"
            print(f"      [vl-cap] n_chunks={len(state.summaries)} > "
                  f"{CAPTION_MAX_CHUNKS} → 长视频画面 pattern 易让 LLM catch-all，"
                  f"降级回 CLIP sim cue", flush=True)
            state.visual_captions_for_llm = None
        # 中层判定：generic_ratio（通用动词占比）
        elif generic >= CAPTION_GENERIC_MAX:
            state.vl_degraded_reason = "generic_ratio_high"
            print(f"      [vl-cap] generic_ratio={generic:.2f} ≥ "
                  f"{CAPTION_GENERIC_MAX} → caption 多为'讲师讲解/演示'通用句式无"
                  f"区分度，LLM 易 catch-all，降级回 CLIP sim cue", flush=True)
            state.visual_captions_for_llm = None
        # 内层判定：前缀长 run + 剩余 chunks
        elif (best >= CAPTION_PREFIX_RUN_MIN
              and len(captions) - best >= CAPTION_OTHER_MIN):
            state.vl_degraded_reason = "prefix_run_degenerate"
            print(f"      [vl-cap] max_prefix_run={best}, "
                  f"others={len(captions)-best} → caption 高度同质化但剩余 chunks "
                  f"足够多，易诱发 LLM 漏 chunks（p44 case），降级回 CLIP sim cue",
                  flush=True)
            state.visual_captions_for_llm = None
        else:
            state.visual_captions_for_llm = captions
            print(f"      [vl-cap] n_chunks={len(state.summaries)} ≤ "
                  f"{CAPTION_MAX_CHUNKS}, generic_ratio={generic:.2f} < "
                  f"{CAPTION_GENERIC_MAX}, prefix_run={best} 不退化 → "
                  f"caption 用作切分主信号", flush=True)
    except Exception as e:
        print(f"      [vl-cap] 异常：{e}（跳过 caption，回退 sim cue）", flush=True)


# ============ Stage 12: 内容大类轻量分类（早期，给 LLM 切分用） ============
def _stage_classify_category_early(cfg: PipelineConfig, state: PipelineState) -> None:
    # 提到 LLM 章节切分前，让切分用对应 category 的 prompt（vlog/talk 章节更碎）。
    # 末段还会再算一次（用相同 transcript）回写 meta.json，结果一致。
    assert state.video is not None
    _meta_for_cat = _load_meta_safe(META_DIR / f"{state.video.stem}.meta.json") or {}
    try:
        from classify_category import classify_category
        cat_transcript = " ".join((c.get("text") or "")[:600] for c in state.summaries[:10])[:5000]
        cat_keywords_flat = [kw for c in state.summaries for kw in (c.get("keywords") or [])]
        _cat_result = classify_category(
            _meta_for_cat, transcript=cat_transcript,
            keywords=cat_keywords_flat,
            duration_sec=state.asr_result.get("duration"))
        state.inferred_category = _cat_result["category"]
        print(f"      [category-early] {state.inferred_category} "
              f"({_cat_result['confidence']}) → LLM 切分用 {state.inferred_category} prompt",
              flush=True)
    except Exception as e:
        print(f"      [category-early] 分类异常：{e}，按 teaching 走", flush=True)


# ============ Stage 13: 例题段标记（is_example）============
def _stage_example_detection(cfg: PipelineConfig, state: PipelineState) -> None:
    # I4-d: chunk 级例题标记 — 教学/科普类视频跑 Python 正则识别题目讲解段，
    # 把 is_example=True 写到 chunk dict，md 渲染时加 📝 例题 badge
    # 不改 chapter 切分结构，保留 LLM 的大段判断
    if not (state.summaries and state.inferred_category in ("teaching", "popsci")):
        return
    from segment_llm import _detect_example_chunks
    ex_idxs = _detect_example_chunks(state.summaries)
    for i in ex_idxs:
        if 0 <= i < len(state.summaries):
            state.summaries[i]["is_example"] = True
    if ex_idxs:
        print(f"      [example] 识别例题段 {len(ex_idxs)} 个 chunks: {ex_idxs}",
              flush=True)


# ============ Stage 14: 章节切分（LLM or TextTiling fallback）============
def _stage_chapters(cfg: PipelineConfig, state: PipelineState) -> None:
    if cfg.llm_chapters:
        _do_llm_chapters(cfg, state)
    if state.chapter_list is None and cfg.chapters is not None and cfg.chapters != 0:
        _do_texttile_chapters(cfg, state)


def _load_forced_outline(path: str, summaries: list[dict]) -> dict:
    """从 JSON 读人工指定的章节 partition，构造成 segment_hierarchical 同形的 outline。
    JSON 格式：list of {"title": str, "indices": [chunk_idx, ...]}（每章连续区间）。
    start/end 由各章首末 chunk 的时间填，children 留空（顶层切分由人工负责）。
    """
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    n = len(summaries)
    chapters = []
    for c in spec:
        idx = [int(i) for i in c["indices"]]
        if not idx or min(idx) < 0 or max(idx) >= n:
            raise ValueError(f"force-outline 章 {c.get('title')!r} 的 indices {idx} 越界（n={n}）")
        chapters.append({
            "title": c["title"],
            "indices": idx,
            "start": summaries[idx[0]]["start"],
            "end": summaries[idx[-1]]["end"],
            "children": [],
        })
    return {"chapters": chapters,
            "_meta": {"attempts_used": 0, "pass_via": "forced_outline",
                      "repair_used": [], "fail_reasons": []}}


def _do_llm_chapters(cfg: PipelineConfig, state: PipelineState) -> None:
    """LLM 层级章节切分（替代 TextTiling 章节路径）。失败时不写 state.chapter_list。"""
    if cfg.force_outline:
        outline = _load_forced_outline(cfg.force_outline, state.summaries)
        print(f"[chapters] 人工固定 partition：{len(outline['chapters'])} 章"
              f"（--force-outline，跳过 LLM 自动分段）", flush=True)
        state.seg_meta["forced_outline"] = True
    else:
        print("[chapters] LLM 层级章节切分（Qwen2.5-7B-AWQ）...", flush=True)
        try:
            from segment_llm import segment_hierarchical
            outline = segment_hierarchical(state.summaries,
                                            visual_sims=state.visual_sims_for_llm,
                                            visual_captions=state.visual_captions_for_llm,
                                            lang=state.resolved_lang,
                                            category=state.inferred_category)
        except Exception as e:
            print(f"      [llm-chapters] 异常：{e}，fallback TextTiling", flush=True)
            outline = None
    # VL 救援：用了 VL caption 但 LLM 3 attempts + repair 都失败时，
    # 自动 retry 一次不带 caption（仅 sim cue）。
    vl_rescue_triggered = False
    if (outline is not None
            and state.visual_captions_for_llm is not None
            and not outline.get("chapters")):
        print(f"      [vl-rescue] VL caption 路径 LLM 3 attempts + repair 都失败，"
              f"自动 retry 不带 caption（仅 sim cue）...", flush=True)
        try:
            outline_rescue = segment_hierarchical(
                state.summaries, visual_sims=state.visual_sims_for_llm,
                visual_captions=None, lang=state.resolved_lang,
                category=state.inferred_category)
            if outline_rescue and outline_rescue.get("chapters"):
                print(f"      [vl-rescue] retry 成功，VL caption 是失败原因",
                      flush=True)
                outline = outline_rescue
                vl_rescue_triggered = True
                state.vl_degraded_reason = "rescue_after_llm_fail"
                state.visual_captions_for_llm = None
            else:
                print(f"      [vl-rescue] retry 仍失败，问题不在 VL caption",
                      flush=True)
        except Exception as e:
            print(f"      [vl-rescue] 异常：{e}", flush=True)
    # 即便 outline 没出 chapters（LLM 失败），也读 _meta 让 ablation 准确
    # 显示"LLM 跑了 N 次 attempt 但失败 → fallback"
    if outline:
        llm_meta = outline.get("_meta") or {}
        state.seg_meta["llm_attempts"] = llm_meta.get("attempts_used", 0)
        state.seg_meta["llm_pass_via"] = llm_meta.get("pass_via")
        state.seg_meta["llm_repair_used"] = llm_meta.get("repair_used", [])
        state.seg_meta["llm_fail_reasons"] = llm_meta.get("fail_reasons", [])
        state.seg_meta["vl_rescue_used"] = vl_rescue_triggered
    if outline and outline.get("chapters"):
        chapter_list = outline["chapters"]
        state.seg_meta["method"] = "llm"
        # 补 chunks 引用，供后续 chapter abstract 用
        for ch in chapter_list:
            ch["chunks"] = [state.summaries[i] for i in ch["indices"]]
            for sub in ch.get("children", []):
                sub["chunks"] = [state.summaries[i] for i in sub["indices"]]
        print(f"      [llm-chapters] {len(chapter_list)} 顶层 / "
              f"{sum(len(ch.get('children', [])) for ch in chapter_list)} 子章节",
              flush=True)
        # 章节级 abstractive 概述：llm_chapters 模式下用 Qwen 生成 prose
        if cfg.summarizer == "neural":
            _apply_chapter_abstracts(chapter_list, cfg.llm_chapters,
                                     lang=state.resolved_lang,
                                     category=state.inferred_category)
            _apply_chapter_recaps(chapter_list, cfg.llm_chapters,
                                  lang=state.resolved_lang,
                                  category=state.inferred_category)
            _apply_chapter_quizzes(chapter_list, cfg.llm_chapters,
                                   lang=state.resolved_lang,
                                   category=state.inferred_category)
            state.doc_overview = _apply_doc_overview(
                chapter_list, cfg.llm_chapters,
                video_title=(state.meta_for_terms or {}).get("title", ""),
                lang=state.resolved_lang,
                category=state.inferred_category)
        _mark_wrapup_chapter(chapter_list, lang=state.resolved_lang)
        state.chapter_list = chapter_list


def _do_texttile_chapters(cfg: PipelineConfig, state: PipelineState) -> None:
    """TextTiling fallback 路径（llm 失败或没开 llm_chapters 但开了 --chapters）。"""
    if cfg.llm_chapters:
        state.seg_meta["fallback_used"] = True
    state.seg_meta["method"] = "texttile"
    from segment import detect_boundaries, group_into_chapters
    n = cfg.chapters if cfg.chapters > 0 else None
    title_fn = None
    # llm_chapters 时 refine_chapter_titles 会覆盖 fallback 章标题
    if cfg.summarizer == "neural" and not cfg.llm_chapters:
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
            # Pegasus 在小输入（≤3 段 headline）上倾向退化成抄一段
            if len(headlines) <= 3 and _is_chapter_title_copy(title, headlines):
                title = _fallback_chapter_title(headlines)
            return nominalize_title(title)
    # ablation: 文本-only 和 多模态分别算一次
    text_only_bounds, text_dbg = detect_boundaries(
        state.summaries, num_chapters=n, return_debug=True)
    if state.visual_feats is not None:
        mm_bounds_idx, mm_dbg = detect_boundaries(
            state.summaries, num_chapters=n, visual_feats=state.visual_feats,
            alpha=cfg.mm_alpha, return_debug=True)
    else:
        mm_bounds_idx, mm_dbg = text_only_bounds, text_dbg
    chapter_list = group_into_chapters(state.summaries, mm_bounds_idx,
                                       title_fn=title_fn)
    # B1 移植到 fallback 路径：LLM 切分失败时（如 p37 漏 chunk），TextTiling fallback
    # 出的章节也应享受"只看本章 headlines"的标题重写
    if cfg.llm_chapters and chapter_list:
        try:
            from segment_llm import refine_chapter_titles
            outline_for_titles = {"chapters": [
                {"chunks": ch["indices"]} for ch in chapter_list]}
            refined_titles = refine_chapter_titles(outline_for_titles, state.summaries,
                                                    lang=state.resolved_lang,
                                                    category=state.inferred_category)
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
    if cfg.summarizer == "neural" and chapter_list:
        _apply_chapter_abstracts(chapter_list, cfg.llm_chapters,
                                 lang=state.resolved_lang,
                                 category=state.inferred_category)
        _apply_chapter_recaps(chapter_list, cfg.llm_chapters,
                              lang=state.resolved_lang,
                              category=state.inferred_category)
        _apply_chapter_quizzes(chapter_list, cfg.llm_chapters,
                               lang=state.resolved_lang,
                               category=state.inferred_category)
        state.doc_overview = _apply_doc_overview(
            chapter_list, cfg.llm_chapters,
            video_title=(state.meta_for_terms or {}).get("title", ""),
            lang=state.resolved_lang,
            category=state.inferred_category)
    _mark_wrapup_chapter(chapter_list, lang=state.resolved_lang)
    mm_bounds = [ch["indices"][0] for ch in chapter_list[1:]]
    state.ablation = {
        "alpha": cfg.mm_alpha,
        "text_dists": text_dbg["text_dists"],
        "visual_dists": mm_dbg["visual_dists"],
        "fused_dists": mm_dbg["fused_dists"],
        "depth_scores": mm_dbg["depth_scores"],
        "text_only_boundaries": text_only_bounds,
        "multimodal_boundaries": mm_bounds,
    }
    if state.visual_feats is not None:
        print(f"      章节切分（多模态 α={cfg.mm_alpha}）: {len(chapter_list)} 章，"
              f"边界 段{[b + 1 for b in mm_bounds]}")
        if text_only_bounds != mm_bounds:
            print(f"      ablation 对比 - 纯文本 段{[b + 1 for b in text_only_bounds]}"
                  f" → 多模态 段{[b + 1 for b in mm_bounds]}")
        else:
            print(f"      ablation - 文本与多模态边界一致")
    else:
        print(f"      章节切分（纯文本）: {len(chapter_list)} 章，边界 段"
              f"{[b + 1 for b in mm_bounds]}")
    state.chapter_list = chapter_list


# ============ Stage 15: 双语翻译（title + abstract + headline） ============
def _stage_bilingual(cfg: PipelineConfig, state: PipelineState) -> None:
    # 给前端 lang toggle 用：把每个文本字段翻译为另一种语言并存为 _zh / _en 后缀字段。
    # llm_chapters 时复用 Qwen（model 已在显存），增量 ~10-20s。
    if not (cfg.llm_chapters and state.chapter_list
            and state.resolved_lang in ("zh", "en")):
        return
    tgt_lang = "en" if state.resolved_lang == "zh" else "zh"
    src_lang = state.resolved_lang
    try:
        from segment_llm import translate_bilingual
        # 1) 章标题
        titles = [ch.get("title", "") for ch in state.chapter_list]
        t_titles = translate_bilingual(titles, src_lang, tgt_lang) if any(titles) else None
        if t_titles and len(t_titles) == len(state.chapter_list):
            for ch, t in zip(state.chapter_list, t_titles):
                ch[f"title_{src_lang}"] = ch.get("title", "")
                ch[f"title_{tgt_lang}"] = t
        # 2) 章 abstract
        abstracts = [ch.get("abstract", "") for ch in state.chapter_list]
        if any(abstracts):
            t_abs = translate_bilingual(abstracts, src_lang, tgt_lang)
            if t_abs and len(t_abs) == len(state.chapter_list):
                for ch, t in zip(state.chapter_list, t_abs):
                    ch[f"abstract_{src_lang}"] = ch.get("abstract", "")
                    ch[f"abstract_{tgt_lang}"] = t
        # 3) chunk headlines
        headlines = [c.get("headline", "") for c in state.summaries]
        if any(headlines):
            t_hls = translate_bilingual(headlines, src_lang, tgt_lang)
            if t_hls and len(t_hls) == len(state.summaries):
                for c, t in zip(state.summaries, t_hls):
                    c[f"headline_{src_lang}"] = c.get("headline", "")
                    c[f"headline_{tgt_lang}"] = t
        # 4) 文档级全文总结（summary 散文 + takeaways 要点）
        ov = state.doc_overview
        if ov and ov.get("summary"):
            t_sum = translate_bilingual([ov["summary"]], src_lang, tgt_lang)
            if t_sum and len(t_sum) == 1:
                ov[f"summary_{src_lang}"] = ov["summary"]
                ov[f"summary_{tgt_lang}"] = t_sum[0]
            tk = ov.get("takeaways") or []
            if tk:
                t_tk = translate_bilingual(tk, src_lang, tgt_lang)
                ov[f"takeaways_{src_lang}"] = list(tk)
                if t_tk and len(t_tk) == len(tk):
                    ov[f"takeaways_{tgt_lang}"] = t_tk
        print(f"      [bilingual] 双语字段填充完成 ({src_lang}<->{tgt_lang})", flush=True)
    except Exception as e:
        print(f"      [bilingual] 翻译异常：{e}（跳过，前端 fallback 单语）", flush=True)


# ============ Stage 16: 写 summary.json + chapters.json ============
def _stage_write_outputs(cfg: PipelineConfig, state: PipelineState) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = _output_stem(state.audio, state.tag, cfg.summarizer, cfg.chunker,
                         cfg.chunk_chars, keyframes=cfg.keyframes,
                         vlm_captions=cfg.vlm_captions)
    (OUTPUT_DIR / f"{stem}.summary.json").write_text(
        json.dumps(state.summaries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if state.chapter_list:
        # chapters 序列化时不能直接 dump（含原 chunk 引用），写一份精简版
        def _slim_ch(ch: dict) -> dict:
            s = {"title": ch["title"], "start": ch["start"], "end": ch["end"],
                 "indices": ch["indices"], "abstract": ch.get("abstract", "")}
            # 学习类专属 (teaching/popsci)：LLM 生成的章末复习要点 + 自测题
            if ch.get("recap"):
                s["recap"] = ch["recap"]
            if ch.get("quiz"):
                s["quiz"] = ch["quiz"]
            # 双语字段
            for k in ("title_zh", "title_en", "abstract_zh", "abstract_en"):
                if ch.get(k):
                    s[k] = ch[k]
            children = ch.get("children")
            if children:
                s["children"] = [_slim_ch(sub) for sub in children]
            return s
        slim = [_slim_ch(ch) for ch in state.chapter_list]
        # 给 ablation 加上切分路径元数据（供 aggregate_eval.py / 论文附录 B 用）
        if state.ablation is None:
            state.ablation = {}
        state.ablation["seg_meta"] = state.seg_meta
        state.ablation["duration"] = state.asr_result.get("duration")
        state.ablation["n_chunks"] = len(state.summaries)
        state.ablation["lang"] = state.resolved_lang
        state.ablation["keyframes"] = cfg.keyframes
        state.ablation["vlm_captions"] = cfg.vlm_captions
        # 用户开了 vlm_captions 但 redundancy 太高被降级时 captions_used = False
        state.ablation["vlm_captions_used"] = (
            cfg.vlm_captions and state.visual_captions_for_llm is not None)
        # 二次门控诊断
        if cfg.vlm_captions:
            state.ablation["vlm_max_prefix_run"] = state.vl_max_prefix_run
            state.ablation["vlm_generic_ratio"] = (
                round(state.vl_generic_ratio, 3)
                if state.vl_generic_ratio is not None else None)
            state.ablation["vlm_degraded_reason"] = state.vl_degraded_reason
        state.ablation["n_chapters"] = len(state.chapter_list)
        state.ablation["max_chunks_per_chapter"] = max(
            len(c["indices"]) for c in state.chapter_list)
        state.ablation["has_wrapup"] = any(
            "本节复习" in c.get("title", "") or "Recap" in c.get("title", "")
            for c in state.chapter_list)
        payload = {"chapters": slim, "ablation": state.ablation}
        if state.doc_overview and state.doc_overview.get("summary"):
            payload["overview"] = state.doc_overview
        (OUTPUT_DIR / f"{stem}.chapters.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2,
                       default=lambda x: float(x) if hasattr(x, "item") else None),
            encoding="utf-8"
        )
    state.md_path = OUTPUT_DIR / f"{stem}.md"
    # md_meta 给后续 stage 17/18 用
    meta_path = META_DIR / f"{state.video.stem}.meta.json"
    state.md_meta = _load_meta_safe(meta_path)


# ============ Stage 17: 内容大类回写 meta（拿 confidence 字段）============
def _stage_classify_category_for_meta(cfg: PipelineConfig, state: PipelineState) -> None:
    # 写入 raw/{stem}.meta.json，server._publish_to_web 会 copy 到 web/public。
    # 前端据此切换 UI 模板（vlog 不显示术语表 / 知识点速览改时间轴等）。
    # 与 stage 12 [category-early] 同输入同结果（纯启发式，毫秒级）；重算只为
    # 拿 confidence 字段写 meta，category 用 inferred_category 保证 md 与 meta 一致
    if state.md_meta is None:
        return
    meta_path = META_DIR / f"{state.video.stem}.meta.json"
    try:
        from classify_category import classify_category
        transcript = " ".join((c.get("text") or "")[:600] for c in state.summaries[:10])[:5000]
        keywords_flat: list[str] = []
        for c in state.summaries:
            for kw in (c.get("keywords") or []):
                keywords_flat.append(kw)
        cat_result = classify_category(
            state.md_meta, transcript=transcript,
            keywords=keywords_flat,
            duration_sec=state.asr_result.get("duration"))
        state.md_meta["category"] = cat_result["category"]
        state.md_meta["category_confidence"] = cat_result["confidence"]
        meta_path.write_text(
            json.dumps(state.md_meta, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"      [category] {cat_result['category']} "
              f"({cat_result['confidence']}) scores={cat_result['scores']}",
              flush=True)
    except Exception as e:
        print(f"      [category] 分类异常：{e}（meta 不写 category 字段）",
              flush=True)


# ============ Stage 18: 写 md ============
def _stage_write_md(cfg: PipelineConfig, state: PipelineState) -> None:
    assert state.md_path is not None
    md_title = state.md_meta.get("title", state.md_path.stem) if state.md_meta else state.md_path.stem
    state.md_path.write_text(
        to_markdown(state.summaries, title=md_title, chapters=state.chapter_list,
                    keyframe_rel_prefix=state.kf_rel_prefix,
                    learning_mode=cfg.learning_mode,
                    confidence_threshold=cfg.confidence_threshold,
                    lang=state.resolved_lang,
                    category=state.inferred_category),
        encoding="utf-8")
    print(f"\n[OK] 完成! 笔记: {state.md_path}")


_STAGES = [
    _stage_prepare_video,
    _stage_extract_audio,
    _stage_build_asr_context,
    _stage_asr,
    _stage_chunk,
    _stage_summarize,
    _stage_qwen_asr_fix,
    _stage_keyframes,
    _stage_llm_headline,
    _stage_visual_sims,
    _stage_vlm_captions,
    _stage_classify_category_early,
    _stage_example_detection,
    _stage_chapters,
    _stage_bilingual,
    _stage_write_outputs,
    _stage_classify_category_for_meta,
    _stage_write_md,
]


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
        vlm_captions: bool = False,
        quality: str = "best",
        force_outline: str | None = None) -> Path:
    """Orchestrator：把 17 个 kwarg 装进 PipelineConfig，依次跑 18 个 stage。"""
    cfg = PipelineConfig(
        source=source, is_local=is_local, chunk_chars=chunk_chars,
        model_size=model_size, target_ratio=target_ratio, force_asr=force_asr,
        summarizer=summarizer, chapters=chapters, extra_terms=extra_terms,
        keyframes=keyframes, mm_alpha=mm_alpha, chunker=chunker,
        learning_mode=learning_mode, dedupe_asr=dedupe_asr,
        llm_chapters=llm_chapters, confidence_threshold=confidence_threshold,
        lang=lang, vlm_captions=vlm_captions, quality=quality,
        force_outline=force_outline)
    state = PipelineState()
    for stage in _STAGES:
        stage(cfg, state)
    assert state.md_path is not None
    return state.md_path
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
    p.add_argument("--quality", default="best",
                   help="下载画质（仅 URL 模式）。'best' 或 'NNNp'（任意 height，如 "
                        "1080p / 720p / 480p）。ASR/VL caption 不依赖画质，720p 够用。")
    p.add_argument("--vlm-captions", action="store_true",
                   help="--keyframes + --llm-chapters 同时启用时，先调 Qwen2.5-VL "
                        "给每个关键帧生 1 句 caption，喂 segment LLM 做更精准切分。"
                        "需要 models/Qwen2.5-VL-7B-Instruct-AWQ/（~5GB），跟 instruct "
                        "互斥占 VRAM，跑完会 free 让 instruct 加载回来。")
    p.add_argument("--force-outline", default=None, metavar="PATH",
                   help="人工修订分段用：从 JSON 读固定章节 partition（list of "
                        "{\"title\", \"indices\": [chunk_idx...]}），跳过 LLM 自动分段，"
                        "其余章节内容（abstract/recap/quiz/双语）仍由 LLM 重新生成。"
                        "需配合 --llm-chapters。")
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
        vlm_captions=args.vlm_captions, quality=args.quality,
        force_outline=args.force_outline)


if __name__ == "__main__":
    main()
