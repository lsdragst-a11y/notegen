"""[PROGRESS] marker：pipeline 子进程 emit、worker 解析 + 进度带插值。
marker 形如：[PROGRESS] {"stage":"asr","label":"语音识别","i":4,"n":18}
i 为 1-based stage 序号，n 为总 stage 数。"""
from __future__ import annotations

import json
from typing import Optional

_MARKER = "[PROGRESS] "

# _stage_xxx 函数名（去前缀）-> 中文展示标签
STAGE_LABELS = {
    "prepare_video": "准备视频",
    "extract_audio": "抽取音频",
    "build_asr_context": "构建 ASR 上下文",
    "asr": "语音识别",
    "chunk": "切分段落",
    "summarize": "生成摘要",
    "qwen_asr_fix": "ASR 纠错",
    "keyframes": "抽取关键帧",
    "llm_headline": "生成标题",
    "visual_sims": "视觉相似度",
    "vlm_captions": "视觉描述",
    "ocr_captions": "OCR 识别",
    "classify_category_early": "内容分类",
    "example_detection": "例子检测",
    "chapters": "章节切分",
    "bilingual": "双语生成",
    "write_outputs": "写出产物",
    "classify_category_for_meta": "分类(meta)",
    "write_md": "写笔记",
}


def emit_progress(stage: str, label: str, i: int, n: int) -> None:
    """pipeline 子进程调用：打印一行机器可读 marker 到 stdout。"""
    print(_MARKER + json.dumps(
        {"stage": stage, "label": label, "i": i, "n": n},
        ensure_ascii=False), flush=True)


def parse_progress_marker(line: str) -> Optional[dict]:
    """worker 调用：是 marker 行就返回 dict，否则 None。"""
    if not line or not line.startswith(_MARKER):
        return None
    try:
        return json.loads(line[len(_MARKER):])
    except (ValueError, TypeError):
        return None


def stage_band(i: int, n: int) -> tuple[int, int]:
    """第 i 个 stage（1-based）占的百分比带 [lo, hi]。"""
    lo = round((i - 1) / n * 100)
    hi = round(i / n * 100)
    return lo, hi


def interpolate(lo: int, hi: int, frac: float) -> int:
    """带内线性插值；frac 截断到 [0,1]。"""
    frac = max(0.0, min(1.0, frac))
    return round(lo + (hi - lo) * frac)
