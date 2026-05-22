"""视频内容大类分类器。

输出一个枚举 category，前端据此切换 UI 模板：
  - teaching: 教学/课程/编程实操（学习类，保留全部知识点 UI）
  - popsci:   科普/解说/产品评测（去 🎯 难点 + 术语表折叠）
  - vlog:     旅游/美食/日常实拍（用时间轴亮点卡片替代知识点速览）
  - talk:     时事评论/访谈/资讯（措辞换"观点"，无术语表）

策略：纯启发式打分（uploader 白名单 + 标题触发词 + ASR 术语密度 + 时长），
不调 LLM。返回 (category, confidence, reasons) 三元组方便 audit。

打分逻辑：每条规则给 0-3 分加到对应类别桶，最高分胜出；最高分 < 2 时回落
到 "teaching"（保守 default，因学习类对前端 UI 容错最高 —— 模板里所有元素
非空就显示，不出现"硬塞"）。
"""
from __future__ import annotations

import re
from typing import Any


# 各类强信号触发词。匹配在 title / uploader / description 头 300 字。
# 选词标准：尽量歧义低，命中即强信号（3 分）。
_TEACHING_TRIGGERS = (
    "考研", "课程", "讲解", "讲完", "教程", "教学", "题解", "做题", "刷题",
    "笔记", "公开课", "公式", "定理", "算法", "代码", "编程", "实操",
    "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9",  # 王道分p
    "第一章", "第二章", "第三章", "第四章", "第五章", "第六章",
    "章", "节", "学完", "学会", "掌握", "速成", "入门", "基础",
    "tutorial", "course", "lecture", "lesson", "lessons", "learn",
    "fundamentals", "explained", "how to", "step-by-step",
)
_POPSCI_TRIGGERS = (
    "科普", "原理", "揭秘", "解密", "真相", "到底", "为什么", "为啥",
    "评测", "测评", "拆解", "对比", "vs", "横评",
    "看懂", "分钟懂", "5分钟", "10分钟",
    "what is", "explained in", "deep dive",
)
_VLOG_TRIGGERS = (
    "vlog", "日常", "打卡", "打卡了", "试吃", "试玩",
    # 美食类
    "吃了", "吃到", "吃完", "吃个", "吃货", "美食", "好吃", "难吃",
    "口感", "口味", "味道", "酥脆", "鲜美", "下饭", "嗦", "嚼",
    "探店", "踩雷", "翻车", "测评(餐|食|店)",
    # 探秘/探访模式（"探秘 XX 城市！物价多离谱"类探店 vlog 套路）
    "探秘", "探访", "寻味", "觅食", "实拍", "实地", "走访",
    # 挑战/整活
    "挑战", "随机挑战", "随机金额", "整活", "盲盒", "盲选", "盲吃",
    "暴风吸入", "炫", "干饭", "干完",
    # 玩乐
    "玩了", "玩到", "玩完", "玩转", "玩遍", "city walk", "citywalk",
    # 旅游
    "游记", "旅行", "旅游", "旅拍", "出发", "出游", "出国", "出境",
    "酒店", "景点", "民宿", "餐厅", "自助餐", "buffet",
    "迪士尼", "环球影城", "邮轮", "游轮",
    "到达", "抵达", "到了", "去了", "去过", "去哪",
    # 钱/价格 vlog（"物价"是 vlog 高频词；popsci 讲价格用"价格水平/消费水平"）
    "性价比", "划算", "回本", "贵不贵", "便宜", "穷游",
    "物价", "多少钱", "离谱", "值不值", "买一遍", "买光", "买空",
    "可口可乐", "麦当劳", "肯德基", "海底捞",
    # B 站 vlog up 主常用语（"弹幕/评论区/up" 在教学视频里也常出现，去掉避免误伤）
    "up主", "uper",
    # 英文
    "travel", "trip", "food tour", "tasting", "mukbang",
    "challenge", "review",
)
_TALK_TRIGGERS = (
    # 政治/时事
    "总统", "首相", "议会", "国会", "政策", "新闻", "时事",
    "特朗普", "懂王", "拜登", "普京", "马斯克", "扎克伯格",
    "访华", "访美", "访日", "访问", "会晤", "峰会",
    # 评论/观点
    "评论", "评议", "观点", "分析师", "点评", "锐评", "毒舌",
    "推文", "微博", "推特", "twitter", "tweet",
    "事件", "热搜", "瓜",
    # 资讯/科技新闻（保留 talk 强信号；删"今日/最新/刚刚"等 vlog/教学也用的通用词）
    "早报", "晚报", "快讯", "速报", "资讯", "速递", "速评",
    "官宣", "官方发布", "正式发布",
    "突发", "重磅",
    "breaking", "announces", "announcement",
)

# 价格模式 regex：数字 + (元|块) + 吃|玩|的 → 强 vlog 信号
# e.g. "69元吃菜单"、"100块玩转上海"、"9.9 块的"
_PRICE_VLOG_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:元|块|rmb)\s*(?:吃|玩|逛|游|的|挑战)")

# vlog 口语化高频词（ASR transcript 里高密度才算 vlog 信号）
# 严格选词：只放在教学视频里几乎不出现、vlog 里高频的词。
# 删除"今天/我们/挺好/真的/有点/感觉/哇"等通用口语词 — 它们在编程/PPT
# 教学讲师口语里同样高频，会误伤教学视频（python/claudecode 实测被打进 vlog）
_VLOG_TRANSCRIPT_WORDS = (
    # 美食强信号
    "好吃", "难吃", "味道", "口感", "一口", "咬", "嗦", "嚼",
    "好香", "好辣", "好甜", "好酸", "好咸", "好油",
    # 挑战/旅游强信号
    "挑战", "出发", "到了", "走着", "city walk",
    # 价格 vlog
    "划算", "性价比", "回本", "贵不贵",
)

# uploader 白名单：知名教学/科普频道，直接给目标类别加 3 分
_UPLOADER_WHITELIST: dict[str, tuple[str, int]] = {
    # 教学类
    "王道计算机教育": ("teaching", 3),
    "考研数学": ("teaching", 3),
    "小Lin说": ("popsci", 2),
    "3blue1brown": ("teaching", 3),
    "3Blue1Brown": ("teaching", 3),
    "李永乐老师": ("popsci", 3),
    "吴恩达": ("teaching", 3),
    "andrew ng": ("teaching", 3),
    "李宏毅": ("teaching", 3),
    "Mr.Beast": ("vlog", 2),  # 偶尔会带教学但主体 vlog
}


def _count_hits(text: str, triggers: tuple[str, ...]) -> tuple[int, list[str]]:
    """text 命中的触发词个数 + 命中词列表（用于 reasons audit）。"""
    t = text.lower()
    hits = []
    for kw in triggers:
        if kw.lower() in t:
            hits.append(kw)
    return len(hits), hits


def _term_density(transcript: str) -> float:
    """ASR 转写里"专业术语"密度的粗估：英文大写缩写 + 中文专业短语模式。
    返回 [0, 1] 之间的近似分数，越高越像学术/教学内容。
    """
    if not transcript:
        return 0.0
    # 英文 2-6 字母大写缩写（API/HTTP/TCP/...）。粗略但有效
    abbr = len(re.findall(r"\b[A-Z]{2,6}\b", transcript))
    # 中文"专业短语"启发：N 个汉字 + "性|度|律|论|学|算法|协议|模型|公式|定理"
    cn_terms = len(re.findall(
        r"[一-龥]{2,5}(?:性|度|律|论|学|算法|协议|模型|公式|定理|函数|变量|结构)",
        transcript))
    # 每千字符的术语数量，clip 到 [0, 1]
    per_kchar = (abbr + cn_terms) / max(len(transcript) / 1000, 0.5)
    return min(per_kchar / 25.0, 1.0)  # 25 个术语/kchar = 1.0 满分


def _vlog_lex_density(transcript: str) -> float:
    """vlog 口语化高频词密度。学习视频里这些词偶尔出现；vlog 里密度极高。
    返回每千字符的命中词数（一般 vlog 4-8，教学 <2）。"""
    if not transcript:
        return 0.0
    hits = 0
    for w in _VLOG_TRANSCRIPT_WORDS:
        hits += transcript.count(w)
    return hits / max(len(transcript) / 1000, 0.5)


def _uploader_vlog_hint(uploader: str) -> bool:
    """uploader 名字模式启发：「一只XX/XX 君/XX 酱/XX 仔/小 X 哥」等多见于个人 vlog up。
    避免误伤教学（"X 老师"/"XX 教育"/"考研 XX"明确排除）。"""
    if not uploader:
        return False
    u = uploader.lower()
    # 明确排除：含这些字串基本是教学/科普 channel
    if any(x in u for x in ("老师", "教育", "考研", "教学", "学院", "学堂",
                             "学习", "课堂", "课程", "academy")):
        return False
    # 个人 vlog up 主常见后缀/前缀
    suffixes = ("君", "酱", "仔", "妹", "哥", "姐", "侠", "猫", "鼠",
                 "Q", "菌", "鹿")
    prefixes = ("一只", "小小", "胖胖", "饿了的", "贪吃的")
    if any(uploader.endswith(s) for s in suffixes):
        return True
    if any(uploader.startswith(p) for p in prefixes):
        return True
    return False


def classify_category(meta: dict[str, Any] | None,
                      transcript: str = "",
                      keywords: list[str] | None = None,
                      duration_sec: float | None = None,
                      ) -> dict[str, Any]:
    """返回 {category, confidence, scores, reasons}.

    Args:
      meta: meta.json dict（title/uploader/description）
      transcript: ASR 全文拼接（前 5000 字够用，太长不必）
      keywords: 抽取式关键词列表（备用，目前未单独打分）
      duration_sec: 时长（短视频偏 vlog/popsci）
    """
    meta = meta or {}
    title = str(meta.get("title", ""))
    uploader = str(meta.get("uploader", ""))
    description = str(meta.get("description", ""))[:300]
    tu_text = f"{title}\n{uploader}\n{description}"

    scores = {"teaching": 0, "popsci": 0, "vlog": 0, "talk": 0}
    reasons: list[str] = []

    # 1. uploader 白名单
    if uploader:
        for u, (cat, w) in _UPLOADER_WHITELIST.items():
            if u.lower() in uploader.lower():
                scores[cat] += w
                reasons.append(f"uploader『{uploader}』→ {cat} +{w}")
                break
        # 个人 vlog up 主名字模式（排除教学频道后才生效）
        if _uploader_vlog_hint(uploader):
            scores["vlog"] += 1
            reasons.append(f"uploader『{uploader}』名字模式 → vlog +1")

    # 2. 触发词命中
    for cat, triggers in (
        ("teaching", _TEACHING_TRIGGERS),
        ("popsci", _POPSCI_TRIGGERS),
        ("vlog", _VLOG_TRIGGERS),
        ("talk", _TALK_TRIGGERS),
    ):
        n, hits = _count_hits(tu_text, triggers)
        if n:
            # 触发词分数：1 个 = 1 分，2 个 = 2 分，>=3 个 = 3 分
            w = min(n, 3)
            scores[cat] += w
            reasons.append(f"title/uploader 命中 {cat} 触发词 {hits[:3]}{'…' if n>3 else ''} +{w}")

    # 2b. 价格 vlog 模式（"N 元吃/玩"等数字模式，标题里的极强信号）
    if _PRICE_VLOG_RE.search(tu_text):
        scores["vlog"] += 2
        m = _PRICE_VLOG_RE.search(tu_text)
        reasons.append(f"价格模式『{m.group()}』→ vlog +2")

    # 3. ASR 术语密度（教学加分）
    if transcript:
        d = _term_density(transcript)
        if d >= 0.6:
            scores["teaching"] += 2
            reasons.append(f"术语密度 {d:.2f} 高 → teaching +2")
        elif d >= 0.3:
            scores["teaching"] += 1
            scores["popsci"] += 1
            reasons.append(f"术语密度 {d:.2f} 中 → teaching/popsci +1")

    # 3b. vlog 口语化高频词密度（与术语密度独立，不互斥）
    # 但当 teaching 触发词强命中（>= 2 个 → +2/+3 分）时，口语化信号封顶 +1，
    # 避免教学视频里讲师说"好吃/一口/挑战"等也被推到 vlog（python 实测）
    if transcript:
        v = _vlog_lex_density(transcript)
        teaching_strong = scores["teaching"] >= 2
        if v >= 4:
            w = 1 if teaching_strong else 3
            scores["vlog"] += w
            reasons.append(f"口语化词密度 {v:.1f}/kchar 极高 → vlog +{w}"
                          f"{'（teaching 强命中已封顶）' if teaching_strong else ''}")
        elif v >= 2:
            w = 1 if teaching_strong else 2
            scores["vlog"] += w
            reasons.append(f"口语化词密度 {v:.1f}/kchar 高 → vlog +{w}"
                          f"{'（teaching 强命中已封顶）' if teaching_strong else ''}")
        elif v >= 1:
            if not teaching_strong:
                scores["vlog"] += 1
                reasons.append(f"口语化词密度 {v:.1f}/kchar 中 → vlog +1")

    # 4. 时长信号：极短（<5min）偏 popsci/vlog；极长（>30min）偏 teaching
    if duration_sec is not None:
        if duration_sec < 300:
            scores["popsci"] += 1
            scores["vlog"] += 1
            reasons.append(f"时长 {duration_sec:.0f}s < 5min → popsci/vlog +1")
        elif duration_sec > 1800:
            scores["teaching"] += 1
            reasons.append(f"时长 {duration_sec:.0f}s > 30min → teaching +1")

    # 选最高分；scores 全 0 才 fallback teaching；否则用最高分（哪怕只 1 分）
    best_cat = max(scores, key=scores.get)
    best_score = scores[best_cat]
    sorted_scores = sorted(scores.values(), reverse=True)
    margin = sorted_scores[0] - sorted_scores[1] if len(sorted_scores) >= 2 else 0

    if best_score == 0:
        best_cat = "teaching"
        confidence = "low"
        reasons.append("所有 scores=0 → fallback teaching")
    elif best_score >= 3 and margin >= 2:
        confidence = "high"
    elif best_score >= 2 and margin >= 1:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "category": best_cat,
        "confidence": confidence,
        "scores": scores,
        "reasons": reasons,
    }


if __name__ == "__main__":
    # CLI 自测：python -m classify_category <meta.json path>
    import json, sys
    if len(sys.argv) < 2:
        # 内置 demo cases
        cases = [
            ({"title": "20分钟学完一遍python基础", "uploader": "__阿岳__"},
             "Python 是一种高级编程语言 函数 变量 列表 字典 异常处理"),
            ({"title": "世界最大迪士尼游轮！5天到底吃什么？玩什么？",
              "uploader": "元气八眉菌"},
             "我们今天来到了迪士尼游轮 这个自助餐厅 这个味道真的很不错"),
            ({"title": "懂王一到轰20就起飞？？懂王访华前连发10多条推文",
              "uploader": "士口加I"},
             "特朗普最近又发了好几条推文 说要访华 这个事情非常的有意思"),
            ({"title": "5分钟看懂深度学习", "uploader": "AI 解说"},
             "深度学习是一种人工神经网络 backpropagation SGD 模型 算法"),
        ]
        for meta, tr in cases:
            r = classify_category(meta, tr, duration_sec=600)
            print(f"\n=== {meta['title'][:40]} ===")
            print(f"  → {r['category']} ({r['confidence']})  scores={r['scores']}")
            for line in r["reasons"]:
                print(f"  · {line}")
    else:
        with open(sys.argv[1], encoding="utf-8") as f:
            meta = json.load(f)
        r = classify_category(meta)
        print(json.dumps(r, ensure_ascii=False, indent=2))
