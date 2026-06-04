"""Qwen2.5-VL-7B-Instruct-AWQ：逐字 OCR 每个 chunk 的屏上文字。

复用 caption_vl 的 VL 单例（不二次加载）。每 chunk 等间距抽 frames_per_chunk 帧
各跑一次 OCR，行级 union 去重，返回与 chunks 等长的 ocr_text（无文字→""）。

与 caption 的区别：caption 是 1 句画面描述（1 张 CLIP 关键帧）；OCR 是逐字转写
（多帧 union），用于 ground 生成、消"屏上 token 缺失→LLM 编造"幻觉。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

_OCR_SYSTEM = (
    "你是屏幕文字转写器。逐字转写画面中所有清晰可读的文字：幻灯片标题/正文/公式、\n"
    "代码、终端命令、菜单项、按钮文字、符号。只转写真实可见的文字，看不清或没有\n"
    "文字就返回空。绝不补全、绝不翻译、绝不解释、绝不描述画面内容。"
)
_OCR_USER = "逐字转写这一帧里所有清晰可读的文字，一行一项；没有文字就只回复一个减号 -。"


def _normalize_line(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


def _ocr_one_frame(image, model, processor, max_new_tokens: int = 256) -> list[str]:
    import torch
    messages = [
        {"role": "system", "content": _OCR_SYSTEM},
        {"role": "user", "content": [
            {"type": "image", "image": image},
            {"type": "text", "text": _OCR_USER},
        ]},
    ]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], images=[image], padding=True,
                       return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=max_new_tokens,
                             do_sample=False, temperature=1.0)
    gen_ids = out[0][inputs["input_ids"].shape[1]:]
    raw = processor.decode(gen_ids, skip_special_tokens=True).strip()
    lines = []
    for ln in raw.splitlines():
        ln = ln.strip().strip("-•·*").strip()
        if ln and ln != "-":
            lines.append(ln)
    return lines


def ocr_chunks(chunks: list[dict], video_path,
               lang: str = "zh",
               frames_per_chunk: int = 3,
               model_dir: Optional[str] = None) -> list[str]:
    """对每个 chunk 抽 frames_per_chunk 帧跑 OCR，union 去重。
    返回 list[str]（与 chunks 等长，无文字段填 ""）。复用 caption_vl 的 VL 单例。"""
    import caption_vl
    from keyframe import sample_frames_for_ranges

    n = len(chunks)
    if n == 0:
        return []
    if model_dir:
        model, processor = caption_vl.load_vl_model(model_dir)
    else:
        model, processor = caption_vl.load_vl_model()

    ranges = [(c["start"], c["end"]) for c in chunks]
    all_frames = sample_frames_for_ranges(video_path, ranges, n=frames_per_chunk)

    out: list[str] = []
    for i, frames in enumerate(all_frames):
        seen: set[str] = set()
        union: list[str] = []
        for _, img in frames:
            try:
                lines = _ocr_one_frame(img, model, processor)
            except Exception as e:
                print(f"      [ocr] chunk {i+1}/{n} 单帧失败 {e}", flush=True)
                continue
            for ln in lines:
                key = _normalize_line(ln)
                if key and key not in seen:
                    seen.add(key)
                    union.append(ln)
        text = "\n".join(union)
        out.append(text)
        if (i + 1) % 5 == 0 or i == n - 1:
            preview = text.replace("\n", " | ")[:60]
            print(f"      [ocr] {i+1}/{n} -> {preview}", flush=True)
    n_ok = sum(1 for t in out if t)
    print(f"      [ocr] OCR 出文字 {n_ok}/{n} chunks", flush=True)
    return out
