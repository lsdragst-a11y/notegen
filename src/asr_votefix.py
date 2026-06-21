"""ASR 视频内频率投票修复——P0 字符级损坏的第三道防线。纯函数，无 GPU。

失败模式（2026-06-12 实测）：faster-whisper 在个别音频上把同一领域词
高置信地解码成多种近形错字（数据→数捷/数损/数搯/数捐…，结构→结枯/结枸，
声旁对、形旁错），avg_logprob 正常（-0.21）——
  防线1 置信度掩码：不触发（置信度高）；
  防线2 静态术语词典：拦不住（错字组合非确定，词典是静态映射）。

第三道防线（确定性、零模型、视频内自举）：
  1. jieba 全文分词，统计 2~4 字纯中文 token 频次；
  2. 候选错词 = 不在 jieba 词典的 token（数捷/结枯 不是词；数组/数学 是词，天然免疫）；
  3. 目标词 = 与候选同长、恰差一字的词典词，且本视频内频次 ≥ max(3, 候选频次×3)
     ——错字变体各自低频、正确词一家独大，频次比是核心安全闸：
     真领域新词（不在词典但全片一致高频）不会满足比值，不会被误改；
  4. 多目标竞争取最高频；平局放弃（保守）；
  5. 映射应用回全部 segment 文本。

在 pipeline _stage_asr 的 dedupe 之后调用；平台字幕路径不需要（已提前 return）。
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

MIN_TARGET_FREQ = 3     # 目标词至少出现 3 次才有投票资格
FREQ_RATIO = 3.0        # 目标词频次须 ≥ 候选 × 此比值（防误伤真新词）
MAX_SUSPECT_FREQ = 10   # 候选自身频次超过此值视为"全片一致"的真词，不动


def _is_zh_token(t: str) -> bool:
    return 2 <= len(t) <= 4 and all("一" <= c <= "鿿" for c in t)


def _in_dict(t: str) -> bool:
    import jieba
    if not jieba.dt.initialized:
        jieba.initialize()
    return jieba.dt.FREQ.get(t, 0) > 0


def _one_char_diff(a: str, b: str) -> bool:
    if len(a) != len(b) or a == b:
        return False
    return sum(1 for x, y in zip(a, b) if x != y) == 1


def build_vote_corrections(texts: list[str],
                           min_target_freq: int = MIN_TARGET_FREQ,
                           ratio: float = FREQ_RATIO,
                           dict_fn=None) -> dict[str, str]:
    """从全文 token 频次构造 错词→正词 映射。dict_fn 可注入（单测不依赖 jieba 词典）。"""
    if dict_fn is None:
        dict_fn = _in_dict
    import jieba
    counts: Counter = Counter()
    for txt in texts:
        for t in jieba.lcut(txt or ""):
            if _is_zh_token(t):
                counts[t] += 1

    in_dict_cache: dict[str, bool] = {}

    def known(t: str) -> bool:
        if t not in in_dict_cache:
            in_dict_cache[t] = bool(dict_fn(t))
        return in_dict_cache[t]

    suspects = [t for t, c in counts.items()
                if c <= MAX_SUSPECT_FREQ and not known(t)]
    targets = {t: c for t, c in counts.items() if c >= min_target_freq and known(t)}

    mapping: dict[str, str] = {}
    for s in suspects:
        cands = [(t, c) for t, c in targets.items()
                 if _one_char_diff(s, t) and c >= max(min_target_freq,
                                                      counts[s] * ratio)]
        if not cands:
            continue
        cands.sort(key=lambda x: -x[1])
        if len(cands) > 1 and cands[0][1] == cands[1][1]:
            continue   # 两个同频目标，无法仲裁，放弃（保守）
        mapping[s] = cands[0][0]
    return mapping


def apply_vote_corrections(asr_result: dict, mapping: dict[str, str]) -> dict:
    """把映射应用回 segments（原地）。长词优先，避免子串交叠。"""
    if not mapping:
        return asr_result
    ordered = sorted(mapping.items(), key=lambda kv: -len(kv[0]))
    for seg in asr_result.get("segments") or []:
        t = seg.get("text") or ""
        for wrong, right in ordered:
            if wrong in t:
                t = t.replace(wrong, right)
        seg["text"] = t
    return asr_result


def vote_fix(asr_result: dict,
             dict_fn=None) -> tuple[dict, dict[str, tuple[str, int]]]:
    """一站式：构造映射 + 应用。返回 (asr_result, stats)，
    stats = {错词: (正词, 替换次数)}，空 dict 表示本视频干净。"""
    segs = asr_result.get("segments") or []
    texts = [s.get("text") or "" for s in segs]
    mapping = build_vote_corrections(texts, dict_fn=dict_fn)
    if not mapping:
        return asr_result, {}
    stats: dict[str, tuple[str, int]] = {}
    joined = "\n".join(texts)
    for wrong, right in mapping.items():
        n = joined.count(wrong)
        if n:
            stats[wrong] = (right, n)
    apply_vote_corrections(asr_result, mapping)
    return asr_result, stats
