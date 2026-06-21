"""平台元数据白捡层：CC/创作者字幕 → 跳过 ASR；创作者章节 → 锚定切分。
纯 stdlib，无 GPU 依赖，全部可单测。

字幕：download_video 已带 --write-subs/--write-auto-subs --convert-subs vtt，
字幕文件落在视频旁（{video_stem}.{lang}.vtt）。本模块负责挑轨道 + 解析 vtt
+ 拼成与 asr.transcribe 同形的 result dict。

策略（pipeline.py _stage_asr 调 load_platform_subtitle）：
  - 创作者手传字幕（meta.subtitle_langs 内、且 lang code 不带 ai- 前缀）→ 默认采用
  - 自动/AI 字幕（automatic_captions 或 ai-* code）→ 默认忽略（whisper large-v3
    通常更准），--use-auto-subs 显式打开
  - 解析结果过 sanity check（段数/覆盖率）不达标 → 回落 whisper

章节：yt-dlp info["chapters"]（B 站分段 / YouTube chapters，创作者手填）→
platform_chapter_outline 把 chunk 按时间中点归入章节，构造 segment_hierarchical
同形 outline（顶层锚定，children 留空），LLM 只做章内摘要/quiz/recap。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

# ---------------- vtt 解析 ----------------

_TS_RE = re.compile(
    r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[.,](\d{3})")
_CUE_LINE_RE = re.compile(
    r"^\s*(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[.,](\d{3})\s*-->\s*"
    r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[.,](\d{3})")
_TAG_RE = re.compile(r"<[^>]+>")


def _ts(h: Optional[str], m: str, s: str, ms: str) -> float:
    return (int(h or 0) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0)


def parse_vtt(text: str) -> list[dict]:
    """WEBVTT → [{start, end, text, confidence: None, words: []}]。
    兼容 srt 风格逗号毫秒；剥 <c>/<v> 标签；连续重复行去重（rolling caption）。"""
    segs: list[dict] = []
    cur: Optional[dict] = None
    for raw in text.splitlines():
        line = raw.strip("﻿").rstrip()
        m = _CUE_LINE_RE.match(line)
        if m:
            if cur and cur["text"]:
                segs.append(cur)
            cur = {"start": _ts(m.group(1), m.group(2), m.group(3), m.group(4)),
                   "end": _ts(m.group(5), m.group(6), m.group(7), m.group(8)),
                   "text": "", "confidence": None, "words": []}
            continue
        if cur is None:
            continue            # header / NOTE / cue id 在首个时间行前
        if not line.strip():
            if cur["text"]:
                segs.append(cur)
            cur = None
            continue
        if line.strip().isdigit() and not cur["text"]:
            continue            # srt 序号行
        t = _TAG_RE.sub("", line).replace("&nbsp;", " ").strip()
        if not t:
            continue
        cur["text"] = (cur["text"] + " " + t).strip() if cur["text"] else t
    if cur and cur["text"]:
        segs.append(cur)

    # rolling caption 去重：上一段文本是当前段前缀（或相等）时合并
    out: list[dict] = []
    for s in segs:
        if out and (s["text"] == out[-1]["text"]
                    or s["text"].startswith(out[-1]["text"])):
            out[-1]["text"] = s["text"]
            out[-1]["end"] = s["end"]
        else:
            out.append(s)
    return out


# ---------------- 轨道挑选 ----------------

_LANG_PREF = {
    "zh": ("zh-hans", "zh-cn", "zh", "zh-hant", "zh-tw", "zh-hk"),
    "en": ("en", "en-us", "en-gb", "en-orig"),
}


def _lang_matches(code: str, lang: str) -> bool:
    c = code.lower().lstrip(".")
    if c.startswith("ai-"):          # B 站 AI 字幕 code 带 ai- 前缀
        c = c[3:]
    return c.startswith(lang)


def _is_auto_code(code: str, manual_langs: list[str], auto_langs: list[str]) -> bool:
    """ai-* 一律算自动（B 站把 AI 字幕也塞 subtitles dict）；
    其余看出现在哪个 dict（都没出现按 auto 保守处理）。"""
    c = code.lower()
    if c.startswith("ai-"):
        return True
    if code in (manual_langs or []):
        return False
    return True


def pick_subtitle_file(video: Path, lang: str,
                       manual_langs: Optional[list] = None,
                       auto_langs: Optional[list] = None,
                       use_auto: bool = False) -> Optional[tuple]:
    """在视频旁找 {stem}.{code}.vtt，返回 (path, code, kind) 或 None。
    优先创作者轨道、语言偏好序靠前者优先；自动轨仅 use_auto 时考虑。"""
    manual_langs = list(manual_langs or [])
    auto_langs = list(auto_langs or [])
    cands = []
    for f in sorted(video.parent.glob(f"{video.stem}.*.vtt")):
        code = f.name[len(video.stem) + 1:-len(".vtt")]
        if not code or not _lang_matches(code, lang):
            continue
        auto = _is_auto_code(code, manual_langs, auto_langs)
        if auto and not use_auto:
            continue
        pref = _LANG_PREF.get(lang, (lang,))
        try:
            rank = pref.index(code.lower().removeprefix("ai-"))
        except ValueError:
            rank = len(pref)
        cands.append((auto, rank, f, code))
    if not cands:
        return None
    cands.sort(key=lambda x: (x[0], x[1]))   # 手传优先，再按语言偏好
    auto, _, f, code = cands[0]
    return f, code, ("auto" if auto else "manual")


def subtitle_sanity_ok(segs: list[dict], video_duration: float) -> bool:
    """段数 ≥5 且字幕时间覆盖 ≥40% 视频时长（披头盖脸只有开头几句的废轨拒掉）。
    duration 未知（0）时只查段数。"""
    if len(segs) < 5:
        return False
    if video_duration and video_duration > 0:
        covered = sum(max(0.0, s["end"] - s["start"]) for s in segs)
        if covered / video_duration < 0.4:
            return False
    return True


def load_platform_subtitle(video: Path, meta: Optional[dict], lang: str,
                           use_auto: bool = False) -> Optional[dict]:
    """一站式：挑轨 → 解析 → sanity → 拼 asr_result 同形 dict。不可用返回 None。"""
    meta = meta or {}
    picked = pick_subtitle_file(
        video, lang,
        manual_langs=meta.get("subtitle_langs"),
        auto_langs=meta.get("auto_caption_langs"),
        use_auto=use_auto)
    if picked is None:
        return None
    path, code, kind = picked
    try:
        segs = parse_vtt(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    duration = float(meta.get("duration") or 0)
    if not subtitle_sanity_ok(segs, duration):
        return None
    return {
        "language": lang,
        "duration": duration or (segs[-1]["end"] if segs else 0.0),
        "segments": segs,
        "source": "platform_subtitle",
        "subtitle_lang": code,
        "subtitle_kind": kind,
    }


# ---------------- 创作者章节 → outline ----------------

def platform_chapter_outline(meta_chapters: Optional[list],
                             summaries: list[dict]) -> Optional[dict]:
    """yt-dlp info["chapters"]（[{start_time, end_time, title}]）→
    segment_hierarchical 同形 outline。chunk 按时间中点归章；空章丢弃；
    有效章 <2 或数据不合格返回 None（让上层走 LLM）。"""
    if not meta_chapters or not summaries:
        return None
    chs = []
    for c in meta_chapters:
        try:
            st = float(c["start_time"])
            title = str(c.get("title") or "").strip()
        except (KeyError, TypeError, ValueError):
            return None
        if not title:
            return None
        chs.append({"start_time": st, "title": title})
    if len(chs) < 2:
        return None
    chs.sort(key=lambda c: c["start_time"])

    buckets: list[list[int]] = [[] for _ in chs]
    for i, s in enumerate(summaries):
        mid = (float(s.get("start") or 0) + float(s.get("end") or 0)) / 2
        # 找最后一个 start_time <= mid 的章
        j = 0
        for k, c in enumerate(chs):
            if c["start_time"] <= mid:
                j = k
            else:
                break
        buckets[j].append(i)

    chapters = []
    for c, idx in zip(chs, buckets):
        if not idx:
            continue
        chapters.append({
            "title": c["title"],
            "indices": idx,
            "start": summaries[idx[0]]["start"],
            "end": summaries[idx[-1]]["end"],
            "children": [],
        })
    if len(chapters) < 2:
        return None
    return {"chapters": chapters,
            "_meta": {"attempts_used": 0, "pass_via": "platform_chapters",
                      "repair_used": [], "fail_reasons": []}}
