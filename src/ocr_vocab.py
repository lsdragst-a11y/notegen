"""B 路：从 chunk 的 ocr_text 建本视频术语词表，保守模糊校正 ASR 错字。

只改 headline / keywords 里**高置信**匹配到屏上术语的 token（幻灯片写"数据链路层"、
ASR 听成"数据连络层"→改）。保守闸沿用 AK→ACK 教训：歧义/低相似不改，避免误伤。
零新依赖：jieba 抽词 + difflib 比相似度。
"""
from __future__ import annotations

import math
import re
from difflib import SequenceMatcher

# 屏上英文/符号术语：命令、flag、Ctrl+X、CamelCase、代码标识符
_EN_TERM_RE = re.compile(r"(?:/[a-zA-Z][\w-]+|--[a-zA-Z][\w-]+|Ctrl\+\w|[A-Z][a-z]+[A-Z]\w+|[a-zA-Z_][\w]{2,})")


def build_vocab(chunks: list[dict]) -> dict:
    """返回 {"cjk": set[str], "en": set[str]}。cjk 是 jieba 名词短语，en 是标识符/命令。

    除单词外，还将 ocr_text 按行拆分、对每行做连续名词 bigram/trigram 拼接，
    捕获"数据 链路层"→"数据链路层"这类跨 token 的多字术语。
    """
    import jieba.posseg as pseg
    cjk: set[str] = set()
    en: set[str] = set()
    for c in chunks:
        text = c.get("ocr_text") or ""
        if not text:
            continue
        for m in _EN_TERM_RE.findall(text):
            if len(m) >= 2:
                en.add(m)
        # 按行处理：单词 + 连续名词 bigram/trigram
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            pairs = [(w, flag) for w, flag in pseg.cut(line)]
            noun_flags = {"n", "nr", "ns", "nt", "nz", "vn"}
            buf: list[str] = []
            for w, flag in pairs:
                if not w.isascii() and (flag.startswith("n") or flag in noun_flags):
                    if len(w) >= 2:
                        cjk.add(w)
                    buf.append(w)
                else:
                    buf = []
                # bigram
                if len(buf) >= 2:
                    compound = "".join(buf[-2:])
                    if len(compound) >= 3:
                        cjk.add(compound)
                # trigram
                if len(buf) >= 3:
                    compound = "".join(buf[-3:])
                    if len(compound) >= 4:
                        cjk.add(compound)
    return {"cjk": cjk, "en": en}


def _cjk_char_diff(a: str, b: str) -> int:
    return sum(1 for x, y in zip(a, b) if x != y)


def correct_token(tok: str, vocab: dict) -> str | None:
    """tok 若高置信匹配某屏上术语则返回校正词，否则 None（不改）。保守阈值。"""
    if not tok or len(tok) < 2:
        return None
    if tok.isascii():
        # 英文：完全相同跳过；否则找同长度、ratio≥0.8 的唯一候选
        if tok in vocab["en"]:
            return None
        cands = [v for v in vocab["en"]
                 if v.lower() != tok.lower()
                 and abs(len(v) - len(tok)) <= 1
                 and SequenceMatcher(None, tok.lower(), v.lower()).ratio() >= 0.8]
        return cands[0] if len(cands) == 1 else None
    # CJK：屏上有完全相同词→已对，跳过；否则找**同长度**、仅差 1 字、ratio≥0.6 的唯一候选
    if tok in vocab["cjk"]:
        return None
    cands = []
    for v in vocab["cjk"]:
        if len(v) == len(tok) and v != tok:
            if _cjk_char_diff(tok, v) <= math.ceil(len(tok) / 3) \
               and SequenceMatcher(None, tok, v).ratio() >= 0.6:
                cands.append(v)
    return cands[0] if len(cands) == 1 else None


def correct_headline_and_keywords(chunks: list[dict], vocab: dict) -> int:
    """就地校正每个 chunk 的 headline + keywords。返回校正次数。"""
    if not (vocab.get("cjk") or vocab.get("en")):
        return 0
    import jieba
    n_fix = 0
    for c in chunks:
        hl = c.get("headline") or ""
        if hl:
            new_hl = hl
            # Pass 1: jieba token-level correction
            for tok in set(jieba.cut(hl)):
                fixed = correct_token(tok, vocab)
                if fixed:
                    new_hl = new_hl.replace(tok, fixed)
                    n_fix += 1
            # Pass 2: substring scan for multi-token CJK terms (e.g. "数据连络层"→"数据链路层"
            # where jieba splits the ASR mishearing but vocab has the correct compound form)
            for vterm in vocab["cjk"]:
                vlen = len(vterm)
                if vlen < 3:
                    continue
                for start in range(len(new_hl) - vlen + 1):
                    sub = new_hl[start:start + vlen]
                    if sub == vterm:
                        break  # already correct substring present
                    fixed = correct_token(sub, {"cjk": {vterm}, "en": set()})
                    if fixed:
                        new_hl = new_hl[:start] + fixed + new_hl[start + vlen:]
                        n_fix += 1
                        break
            c["headline"] = new_hl
        kws = c.get("keywords") or []
        if kws:
            new_kws = []
            for k in kws:
                fixed = correct_token(str(k), vocab)
                new_kws.append(fixed if fixed else k)
                if fixed:
                    n_fix += 1
            c["keywords"] = new_kws
    return n_fix
