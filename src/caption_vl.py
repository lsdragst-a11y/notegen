"""Qwen2.5-VL-7B-Instruct-AWQ：给每个 chunk 的关键帧生 1 句视觉 caption。

输出 chunk 维度的 captions list，由 pipeline 喂给 `segment_hierarchical` 作 visual cue
（替换/补充原 CLIP cosine 浮点 sim——caption 信息密度比浮点高 10x，LLM 能直接
"读懂"画面在讲什么，做 disambiguation）。

VRAM 管理：跟 Qwen2.5-7B-Instruct-AWQ 同显存（~6-7GB），加载前要 free 掉其它
大模型（Whisper / Pegasus / Instruct VL 的另一份）。
"""
from __future__ import annotations

import gc
from pathlib import Path
from typing import Optional

_MODEL = None
_PROCESSOR = None
_DEFAULT_MODEL_DIR = "models/Qwen2.5-VL-7B-Instruct-AWQ"


def _clear_other_models():
    """加载 VLM 前清掉其它已加载的大模型 (Whisper / Pegasus / Qwen Instruct / CLIP)。"""
    for mod_name, attr in [
        ("asr", "_MODEL"),
        ("summarize_neural", "_CACHE"),
        ("keyframe", "_CACHE"),
        ("segment_llm", "_MODEL"),
        ("segment_llm", "_TOKENIZER"),
    ]:
        try:
            mod = __import__(mod_name)
        except Exception:
            continue
        cur = getattr(mod, attr, None)
        if cur is None:
            continue
        if isinstance(cur, dict):
            cur.clear()
        else:
            setattr(mod, attr, None)
    try:
        import torch
        gc.collect()
        torch.cuda.empty_cache()
        if torch.cuda.is_available():
            free_gb = torch.cuda.mem_get_info()[0] / 1024**3
            print(f"      [vl] VRAM free after cleanup: {free_gb:.1f} GB", flush=True)
    except Exception:
        pass


def load_vl_model(model_dir: str = _DEFAULT_MODEL_DIR):
    """加载 Qwen2.5-VL-7B-Instruct-AWQ。返回 (model, processor)。
    AWQ 量化推理 ~5-6GB VRAM，加载 30-60s。"""
    global _MODEL, _PROCESSOR
    if _MODEL is not None:
        return _MODEL, _PROCESSOR
    _clear_other_models()
    # 尝试本地，不存在 fallback HF repo id
    p = Path(model_dir)
    if p.exists():
        model_path = str(p)
        print(f"      [vl] load from local: {p}", flush=True)
    else:
        model_path = "Qwen/Qwen2.5-VL-7B-Instruct-AWQ"
        print(f"      [vl] local missing, fetching from HF: {model_path}", flush=True)
    # 复用 segment_llm 的 autoawq import shim（transformers 4.57 兼容）
    try:
        import segment_llm  # noqa: ensure shim 注入
    except Exception:
        pass
    from transformers import (Qwen2_5_VLForConditionalGeneration, AutoProcessor)
    import torch
    # torch_dtype 必须显式 float16：AWQ kernel 期望 Half，"auto" 在 Qwen2.5-VL
    # 配置里是 bfloat16，跑时报 "expected scalar type Half but found BFloat16"
    _MODEL = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        model_path,
        torch_dtype=torch.float16,
        device_map="cuda" if torch.cuda.is_available() else "cpu",
    )
    _PROCESSOR = AutoProcessor.from_pretrained(model_path)
    _MODEL.eval()
    print(f"      [vl] model loaded", flush=True)
    return _MODEL, _PROCESSOR


_CAPTION_SYSTEM_ZH = (
    "你是教学视频画面描述助手。看一张视频截图，用 1 句中文（10-30 字）描述\n"
    "画面的**教学相关核心**：是 PPT 幻灯片就说屏幕主体内容（标题/公式/示意图）；\n"
    "是讲师对镜头讲话就说人物动作 + 背景元素（黑板/产品/手势）；是操作演示就说\n"
    "正在演示的工具/界面。不要描述清晰度、构图等无关美学。"
)

_CAPTION_SYSTEM_EN = (
    "You are a visual captioner for educational videos. Look at one frame and write\n"
    "ONE English sentence (10-25 words) describing the **teaching-relevant core**:\n"
    "PPT slide → main on-screen text/formula/diagram; person talking to camera →\n"
    "subject's action + background elements; demo → tool/UI being shown. Skip\n"
    "irrelevant aesthetic descriptions (lighting, sharpness, framing)."
)


def caption_keyframes(chunks: list[dict], lang: str = "zh",
                      model_dir: str = _DEFAULT_MODEL_DIR,
                      max_new_tokens: int = 80,
                      ) -> list[Optional[str]]:
    """给 chunks 里每个有 keyframe 的段调 VLM 出 1 句 caption。
    返回与 chunks 等长 list[str|None]；无 keyframe 的段填 None。

    串行调用（VL 推理 batch 化复杂，单图一次 ~1-2s on 12GB 4080）。
    """
    n = len(chunks)
    if n == 0:
        return []
    model, processor = load_vl_model(model_dir)
    import torch
    from PIL import Image
    system_prompt = _CAPTION_SYSTEM_ZH if lang == "zh" else _CAPTION_SYSTEM_EN
    user_text = "用中文描述这一帧的教学内容核心。" if lang == "zh" \
                 else "Describe the teaching-relevant core of this frame in one English sentence."

    captions: list[Optional[str]] = []
    for i, c in enumerate(chunks):
        kf = c.get("keyframe") or {}
        img_path = kf.get("path")
        if not img_path or not Path(img_path).exists():
            captions.append(None)
            continue
        try:
            image = Image.open(img_path).convert("RGB")
        except Exception as e:
            print(f"      [vl-cap] chunk {i+1}/{n} 图打开失败 {e}", flush=True)
            captions.append(None)
            continue
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": user_text},
            ]},
        ]
        text = processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(
            text=[text], images=[image],
            padding=True, return_tensors="pt"
        ).to(model.device)
        with torch.no_grad():
            out = model.generate(
                **inputs, max_new_tokens=max_new_tokens,
                do_sample=False, temperature=1.0,
            )
        gen_ids = out[0][inputs["input_ids"].shape[1]:]
        cap = processor.decode(gen_ids, skip_special_tokens=True).strip()
        # 清掉可能的换行 / 引号
        cap = cap.replace("\n", " ").strip().strip("\"'`")
        captions.append(cap)
        if (i + 1) % 5 == 0 or i == n - 1:
            print(f"      [vl-cap] {i+1}/{n} -> {cap[:60]}", flush=True)
    n_ok = sum(1 for x in captions if x)
    print(f"      [vl-cap] captioned {n_ok}/{n} keyframes", flush=True)
    return captions


# 长教程视频 caption 高频出现的"画面以人讲为主"通用描述词。命中比例高时表明
# 视觉信号没区分度（画面都是"讲师在讲 X"），LLM 看 caption 会误把"画面在讲 = 同一章"
# 触发 catch-all。这种情况下应该降级回 sim cue。
_GENERIC_TEACHING_WORDS = {
    # 中文
    "讲师", "讲解", "讨论", "介绍", "解释", "分析", "说明", "演示",
    "解读", "阐述", "描述", "提到", "强调", "展示", "举例",
    # 英文
    "explains", "discusses", "introduces", "demonstrates", "talks",
    "presenter", "speaker", "instructor", "lecturer",
    "showing", "explaining", "describing", "discussing",
}


def caption_redundancy(captions: list[Optional[str]]) -> tuple[float, float]:
    """诊断 caption 是否冗余。返回 (jaccard_mean, generic_ratio)：

    1. jaccard_mean: 相邻 caption pair 的 token Jaccard 均值
       - 字面层面是否重复 (BV1S6kQBNEJq 实测 0.08——caption 文本 unique
         但 LLM 还是 catch-all，说明字面 unique 不等于视觉有区分度)
    2. generic_ratio: caption 含通用教学动词 (讲师/讨论/演示/...) 的占比
       - 高比例 → 画面是"人讲" pattern，视觉对切分无信息量
       - BV1S6kQBNEJq AI Agent 教程实测 generic_ratio 高
       - OS p37 哲学家黑板示意图 caption 含"哲学家/筷子/筷子盘子"等具体名词，
         generic_ratio 低

    pipeline 用 generic_ratio 主判（比 jaccard 更精准抓"教学独白"模式）。
    """
    valid = [c for c in captions if c]
    if len(valid) < 2:
        return 0.0, 0.0
    # 1) jaccard 字面相似度
    def toks(s: str) -> set[str]:
        s = s.lower().strip()
        out: set[str] = set()
        for w in s.split():
            if all(ord(ch) < 128 for ch in w):
                if len(w) >= 2:
                    out.add(w)
            else:
                for i in range(len(w) - 1):
                    out.add(w[i:i + 2])
        return out
    pairs = []
    for i in range(len(valid) - 1):
        a, b = toks(valid[i]), toks(valid[i + 1])
        if not a or not b:
            continue
        pairs.append(len(a & b) / len(a | b))
    jaccard_mean = sum(pairs) / max(len(pairs), 1)
    # 2) generic teaching words 比例
    n_generic = 0
    for cap in valid:
        low = cap.lower()
        if any(w in low for w in _GENERIC_TEACHING_WORDS):
            n_generic += 1
    generic_ratio = n_generic / len(valid)
    return jaccard_mean, generic_ratio


def free_vl_model():
    """卸载 VLM 让 Qwen Instruct 等其它模型有空间加载回来。"""
    global _MODEL, _PROCESSOR
    _MODEL = None
    _PROCESSOR = None
    try:
        import torch
        gc.collect()
        torch.cuda.empty_cache()
        if torch.cuda.is_available():
            free_gb = torch.cuda.mem_get_info()[0] / 1024**3
            print(f"      [vl] VRAM free after release: {free_gb:.1f} GB", flush=True)
    except Exception:
        pass
