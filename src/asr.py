"""用 faster-whisper 做带时间戳的中文 ASR。"""
from __future__ import annotations

import json
import os
from pathlib import Path

# ctranslate2 与 torch/mkl 都打包了 OpenMP，同进程加载会冲突
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from faster_whisper import WhisperModel

OUTPUT_DIR = Path("data/outputs")
MODELS_DIR = Path("models")
_MODEL: WhisperModel | None = None


def _resolve_model(model: str) -> str:
    """允许传入 size 字符串 ('small' / 'large-v3'...) 或本地目录路径。
    若 ./models/faster-whisper-<size>/ 存在则优先使用本地副本。"""
    if Path(model).exists():
        return model
    local = MODELS_DIR / f"faster-whisper-{model}"
    if local.exists():
        return str(local)
    return model


def _tag_for_model(model: str) -> str:
    return Path(model).name.removeprefix("faster-whisper-")


def get_model(model: str = "large-v3", device: str = "cuda",
              compute_type: str = "int8_float16") -> WhisperModel:
    """compute_type 默认 int8_float16：int8 量化权重 + fp16 计算，消费 GPU 上比纯
    float16 快 30-50%，质量基本无损。RTX 30/40 系列 well-supported。
    需要纯精度（如复现已有 benchmark）改回 'float16'。"""
    global _MODEL
    if _MODEL is None:
        _MODEL = WhisperModel(_resolve_model(model), device=device, compute_type=compute_type)
    return _MODEL


def dedupe_consecutive_segments(asr_result: dict, min_run: int = 3,
                                 min_chars: int = 6,
                                 prefix_chars: int = 20) -> tuple[dict, dict]:
    """合并连续重复的 ASR segments。

    动机：faster-whisper 长视频偶发 "卡片回路" —— 同一句被反复转写多次。
    王道 OS p37 在 755s 起把 "我们用这个呼吃信号量,保证了..." 重复 9 次，
    导致下游 chunker 关键词频次被自我污染，错过真实 topic boundary。

    默认 min_run=3：合并连续 3+ 次同句。设 3 是因为 2 次重复在 PPT 教学里常见
    （讲师为强调而口头重复），但 3+ 次几乎确定是 ASR 卡片回路。

    算法：在 segments 列表上扫连续相同（前 prefix_chars 字一致）的 run，
    长度 ≥ min_run 时保留首段，把后续 run 段的 end 合并到首段（保持时间连续），
    后续重复段被丢弃。短段（< min_chars）不参与去重，避免误伤"对啊/好的"。

    返回 (new_asr_result, stats)；stats = {"dropped": 丢弃段数,
    "runs": [{"start_idx", "run_len", "start", "end", "text"}, ...]}。
    """
    segs = asr_result.get("segments", [])
    if not segs:
        return asr_result, {"dropped": 0, "runs": []}

    def same_prefix(a: str, b: str) -> bool:
        """共同前缀长度（LCP）足够长。同时支持两种命中：
          (1) LCP ≥ prefix_chars —— 严格前缀匹配
          (2) LCP ≥ 85% × min(len)，且 LCP ≥ min_chars —— 一段是另一段的近似前缀
        case 2 修复了 "A...H和I," (20字) vs "A...H和I这两个节点," (25字) 这种
        whisper 卡片回路常见的"末尾追加几字"模式：第 20 字开始就不同，但前 19 字
        是 A 的 95%，应判同。
        """
        short_len = min(len(a), len(b))
        if short_len < min_chars:
            return False
        lcp = 0
        while lcp < short_len and a[lcp] == b[lcp]:
            lcp += 1
        return lcp >= prefix_chars or lcp >= short_len * 0.85

    out: list[dict] = []
    runs: list[dict] = []
    i = 0
    while i < len(segs):
        s = segs[i]
        text = s["text"].strip()
        if len(text) < min_chars:
            out.append(s)
            i += 1
            continue
        j = i + 1
        while j < len(segs):
            t2 = segs[j]["text"].strip()
            if not same_prefix(text, t2):
                break
            j += 1
        run_len = j - i
        if run_len >= min_run:
            merged = dict(s)
            merged["end"] = segs[j - 1]["end"]
            out.append(merged)
            runs.append({"start_idx": i, "run_len": run_len,
                         "start": s["start"], "end": segs[j - 1]["end"],
                         "text": text[:60]})
            i = j
        else:
            out.append(s)
            i += 1

    new_result = dict(asr_result)
    new_result["segments"] = out
    stats = {"dropped": len(segs) - len(out), "runs": runs}
    return new_result, stats


def apply_term_corrections(asr_result: dict, corrections: dict[str, str]) -> dict:
    """对 ASR 段文本做术语替换。corrections: {"错字": "正确"}.
    用 word-boundary 不实际（中文混排），所以直接 substring 替换；按 key 长度降序
    避免短词先吃掉长词。"""
    if not corrections:
        return asr_result
    items = sorted(corrections.items(), key=lambda kv: -len(kv[0]))
    for seg in asr_result.get("segments", []):
        t = seg["text"]
        for wrong, right in items:
            if wrong and wrong != right:
                t = t.replace(wrong, right)
        seg["text"] = t
    return asr_result


def transcribe(audio_path: Path | str, model_size: str = "large-v3",
               language: str = "zh", initial_prompt: str | None = None) -> dict:
    audio_path = Path(audio_path)
    model = get_model(model_size)
    if initial_prompt:
        print(f"      ASR prompt: {initial_prompt[:60]}{'...' if len(initial_prompt) > 60 else ''}",
              flush=True)
    print(f"      model loaded, transcribing ...", flush=True)

    segments, info = model.transcribe(
        str(audio_path),
        language=language,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
        initial_prompt=initial_prompt,
        word_timestamps=True,
        # 切断跨段上下文携带：长视频末尾的 hallucination loop 会让 whisper
        # 一直生成超出音频末尾的字幕，最终触发 ctranslate2 内部 abort
        # (STATUS_FATAL_APP_EXIT 0xC0000409)。p78 在 2027s 音频上跑到 2099s 后崩。
        condition_on_previous_text=False,
        no_repeat_ngram_size=3,
        # 2026-05-21 BV1q6ozBmE8z vlog 1542s/1564s 再次 native abort：教学视频
        # condition_on_previous_text + no_repeat_ngram=3 已不够，vlog 末尾"那么"
        # "好吃"等高频短词触发的 loop 用 faster-whisper 1.x 官方 hallucination
        # gate 兜底。
        hallucination_silence_threshold=2.0,
        # 默认 2.4。loop 段往往 compression_ratio 极高（同字符高重复 → 高压缩比），
        # 收紧到 2.0 让 whisper 自身在 fallback 温度阶梯触发时丢弃这些 segment。
        compression_ratio_threshold=2.0,
    )

    # 进度分母用原始 info.duration——faster-whisper segment.end 是原始音频时间轴
    # （VAD 前），若分母用 duration_after_vad 进度会超 100%（实测长视频偏 1.2~1.5x）
    total_dur = (info.duration or getattr(info, "duration_after_vad", None) or 0.0)
    last_progress_emit = 0.0  # 上次播报的音频处理位置（s），用于节流

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = _tag_for_model(model_size)
    out_path = OUTPUT_DIR / f"{audio_path.stem}.{tag}.asr.json"

    def _dump(seg_list: list, last_end: float, partial: bool) -> None:
        """Atomic write 增量 ASR cache。崩了下次 pipeline 跑能拿到已落盘部分。"""
        payload = {
            "audio": audio_path.name,
            "language": info.language,
            # partial 时 duration 用 last segment end 而非 info.duration，让下游
            # progress 分母逻辑仍 sensible（虽然 partial 时 chunker 会少处理末段内容）
            "duration": info.duration if not partial else last_end,
            "segments": seg_list,
            "partial": partial,
        }
        tmp = out_path.with_suffix(".asr.json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(out_path)

    seg_list = []
    last_end = 0.0
    # 2026-05-21 BV1q6 ASR 第 2 次在 1544s/1564s native abort：ctranslate2 内部
    # buffer 边界 bug，hallucination_silence_threshold 救不了。Native abort 在
    # Python 之外，try/finally 抓不住——必须流式增量落盘。每 50 段 atomic write
    # 一次正式 ASR JSON（带 "partial": True），崩了下次跑 pipeline 看到 cache 跳过 ASR
    # 阶段直接走下游。代价：一次 ASR 多写 ~30 次小 IO，对 26min vlog 不到 1s 总开销。
    INCREMENTAL_DUMP_EVERY = 50
    for s in segments:
        words = []
        if s.words:
            for w in s.words:
                # faster-whisper Word.probability ∈ [0,1]，token 后验
                words.append({
                    "start": round(w.start, 2),
                    "end": round(w.end, 2),
                    "word": w.word,
                    "prob": round(w.probability, 3),
                })
        # 段落级置信度：word probability 加权平均，权重 = word 时长
        if words:
            words_dur = sum(max(w["end"] - w["start"], 0.001) for w in words)
            conf = sum(w["prob"] * max(w["end"] - w["start"], 0.001)
                       for w in words) / words_dur
        else:
            conf = None
        seg_list.append({
            "start": round(s.start, 2),
            "end": round(s.end, 2),
            "text": s.text.strip(),
            "avg_logprob": round(s.avg_logprob, 3) if s.avg_logprob is not None else None,
            "confidence": round(conf, 3) if conf is not None else None,
            "words": words,
        })
        last_end = s.end
        # 进度播报：每处理 30s 音频或每 20 段汇报一次（server.py 解析这行推 percent）
        # 长视频 ASR 是黑盒 5-10min，没这行用户看不到任何中间状态
        if total_dur > 0 and (s.end - last_progress_emit >= 30 or len(seg_list) % 20 == 0):
            print(f"      [asr] {s.end:.1f}s / {total_dur:.1f}s", flush=True)
            last_progress_emit = s.end
        # 增量落盘
        if len(seg_list) % INCREMENTAL_DUMP_EVERY == 0:
            _dump(seg_list, last_end, partial=True)

    # 正常完成：最终一次性写入 partial=False
    result = {
        "audio": audio_path.name,
        "language": info.language,
        "duration": info.duration,
        "segments": seg_list,
        "partial": False,
    }
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # 显式释放 whisper + CUDA。否则进程退出阶段 ctranslate2 析构偶发触发 Windows
    # STATUS_FATAL_APP_EXIT (rc=0xC0000409)，前若干视频成功后中间崩。提前释放把
    # 风险窗口从"整个 pipeline 余下时间"收窄到"transcribe 退出瞬间"。
    global _MODEL
    _MODEL = None
    try:
        import gc
        import torch
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass

    return result


if __name__ == "__main__":
    import sys
    res = transcribe(sys.argv[1])
    print(f"duration={res['duration']:.1f}s, segments={len(res['segments'])}")
    for s in res["segments"][:5]:
        print(f"  [{s['start']:.1f}-{s['end']:.1f}] {s['text']}")
