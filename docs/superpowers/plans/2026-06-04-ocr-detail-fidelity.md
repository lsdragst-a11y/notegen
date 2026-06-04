# OCR 关键细节保真 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用已接入的 Qwen2.5-VL 读 teaching 视频屏上逐字文字，两路（Python 词表校正 + prompt 证据块）ground 章标题/abstract/recap 生成，根治"屏上独有 token 缺失→LLM 编造"的幻觉。

**Architecture:** 在现有 VL caption 驻留窗内加一个 OCR pass（每 chunk 3 帧 union 去重）→ `chunk["ocr_text"]`（落盘缓存）。B 路新模块 `ocr_vocab.py` 从 OCR 文字建本视频词表，保守模糊校正 ASR 错字写回 `headline`/`keywords`；A 路在 segment_llm 的 recap/abstract/title 三处 per-chunk body 注入【屏幕文字】证据块 + 严格反编造约束。门控 `--ocr-captions`，仅 teaching/popsci，默认 off。

**Tech Stack:** Python 3 / transformers 4.57 + Qwen2.5-VL-7B-Instruct-AWQ（复用 `caption_vl` 单例）/ OpenCV 抽帧（`keyframe.sample_frames_for_ranges`）/ jieba / difflib（零新依赖）。

> **测试约定（重要，executing agent 必读）：** 本项目**没有 pytest / 没有 `tests/` 目录**，也**不要**往脆弱的 `.venv`（torch 2.3.1 + autoawq 0.2.6 锁死）装 pytest。验证沿用项目既有约定：`scripts/_dryrun_*.py` / `scripts/compare_*.py` 风格的**可独立运行脚本** + 端到端 smoke 跑 + 人工核对输出。每个 Task 的"验证"步骤就是跑脚本/命令看输出，不是 pytest。命令一律用 `.venv/Scripts/python.exe`。频繁 commit。

> **环境约束：** 严格串行加载大模型（黑屏花屏事故后定的规矩，见 memory `feedback-serial-model-loading`），任何时刻只有一个大模型驻留。OCR 复用 caption 的 VL 驻留窗，**不并行、不二次加载**。

---

## File Structure

| 文件 | 职责 | 动作 |
|---|---|---|
| `src/ocr_vl.py` | VL OCR pass：每 chunk 抽 3 帧逐字转写 + union 去重 + 缓存 | 新建 |
| `src/ocr_vocab.py` | B 路：从 OCR 文字建词表 + 保守模糊校正 ASR 错字 | 新建 |
| `src/pipeline.py` | `--ocr-captions` flag + `ocr_captions` config + OCR stage + 校正 stage + caption stage 条件 free | 改 |
| `src/segment_llm.py` | A 路：recap / abstract / title 三处 body 注入【屏幕文字】块 + 约束 | 改 |
| `scripts/_dryrun_ocr.py` | 独立验证：单视频跑 OCR pass 看 `ocr_text` 质量 | 新建 |
| `scripts/compare_ocr_ablation.py` | 端到端对照：with/without `--ocr-captions` diff 标题/abstract/recap | 新建 |

---

## Task 1: CLI flag + config 管线

**Files:**
- Modify: `src/pipeline.py`（`PipelineConfig` dataclass，line ~708 `vlm_captions: bool = False` 附近；argparse 区 `--vlm-captions` 定义处）

- [ ] **Step 1: 给 PipelineConfig 加 ocr_captions 字段**

在 `src/pipeline.py` `PipelineConfig` 里 `vlm_captions: bool = False` 那行**下面**加：

```python
    ocr_captions: bool = False
```

- [ ] **Step 2: 加 argparse flag**

找到定义 `--vlm-captions` 的 `add_argument`（grep `vlm-captions`），在其后加：

```python
    parser.add_argument("--ocr-captions", action="store_true",
                        help="对 teaching/popsci 视频每 chunk 抽 3 帧跑 VL OCR，"
                             "屏上逐字文字 ground 章标题/abstract/recap（默认关，额外 ~3x 帧推理）")
```

- [ ] **Step 3: 把 args 传进 PipelineConfig**

找到构造 `PipelineConfig(...)` 的地方（grep `vlm_captions=args.vlm_captions` 或 `PipelineConfig(`），加：

```python
        ocr_captions=args.ocr_captions,
```

- [ ] **Step 4: 验证 flag 解析通**

Run: `.venv/Scripts/python.exe src/pipeline.py --help`
Expected: 输出里出现 `--ocr-captions`，无 argparse 报错。

- [ ] **Step 5: Commit**

```bash
git add src/pipeline.py
git commit -m "feat(ocr): 加 --ocr-captions flag + config 管线"
```

---

## Task 2: `src/ocr_vl.py` — VL OCR pass

**Files:**
- Create: `src/ocr_vl.py`
- Reference: `src/caption_vl.py`（VL 单例 + 推理范式）、`src/keyframe.py::sample_frames_for_ranges`

- [ ] **Step 1: 写 ocr_vl.py**

```python
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
```

- [ ] **Step 2: 语法/import 自检**

Run: `.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'src'); import ocr_vl; print('ok', ocr_vl.ocr_chunks.__doc__ is not None)"`
Expected: `ok True`，无 ImportError / SyntaxError。

- [ ] **Step 3: Commit**

```bash
git add src/ocr_vl.py
git commit -m "feat(ocr): src/ocr_vl.py VL 逐字 OCR pass（复用 caption_vl 单例 + 多帧 union）"
```

---

## Task 3: OCR 缓存（sidecar JSON）

**Files:**
- Modify: `src/ocr_vl.py`（加 load/save 缓存函数 + ocr_chunks 命中缓存跳过）

- [ ] **Step 1: 加缓存函数**

在 `src/ocr_vl.py` 末尾加：

```python
import json


def _range_key(start: float, end: float) -> str:
    return f"{round(float(start), 1)}_{round(float(end), 1)}"


def load_ocr_cache(cache_path) -> dict:
    p = Path(cache_path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_ocr_cache(cache_path, chunks: list[dict], ocr_texts: list[str]) -> None:
    data = {}
    for c, t in zip(chunks, ocr_texts):
        data[_range_key(c["start"], c["end"])] = t
    Path(cache_path).write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
```

- [ ] **Step 2: ocr_chunks 接受可选 cache_path 并命中跳过**

把 `ocr_chunks` 签名改为带 `cache_path=None`，在抽帧/推理**之前**插入命中逻辑：函数开头（拿到 `n` 之后）加——

```python
    cache = load_ocr_cache(cache_path) if cache_path else {}
    if cache:
        keys = [_range_key(c["start"], c["end"]) for c in chunks]
        if all(k in cache for k in keys):
            print(f"      [ocr] 命中缓存 {cache_path}（{n} chunks）", flush=True)
            return [cache[k] for k in keys]
```

并在签名加参数：

```python
def ocr_chunks(chunks: list[dict], video_path,
               lang: str = "zh",
               frames_per_chunk: int = 3,
               model_dir: Optional[str] = None,
               cache_path=None) -> list[str]:
```

函数 `return out` **之前**加保存：

```python
    if cache_path:
        try:
            save_ocr_cache(cache_path, chunks, out)
        except Exception as e:
            print(f"      [ocr] 缓存写入失败 {e}", flush=True)
```

- [ ] **Step 3: 缓存往返自检（不需 VL）**

Run:
```
.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'src'); import ocr_vl, tempfile, os; \
ch=[{'start':0,'end':5},{'start':5,'end':10}]; p=os.path.join(tempfile.gettempdir(),'t.ocr.json'); \
ocr_vl.save_ocr_cache(p, ch, ['行A\n行B','']); d=ocr_vl.load_ocr_cache(p); \
print(d[ocr_vl._range_key(0,5)]=='行A\n行B', d[ocr_vl._range_key(5,10)]=='')"
```
Expected: `True True`

- [ ] **Step 4: Commit**

```bash
git add src/ocr_vl.py
git commit -m "feat(ocr): OCR 结果 sidecar 缓存，按 chunk range 命中跳过重 OCR"
```

---

## Task 4: pipeline OCR stage + VL 单驻留

**Files:**
- Modify: `src/pipeline.py`（`_stage_vlm_captions` 内 `free_vl_model()` 改条件；新增 `_stage_ocr_captions`；run 顺序里注册）

- [ ] **Step 1: caption stage 条件释放 VL**

在 `src/pipeline.py::_stage_vlm_captions` 里，把 `free_vl_model()`（line ~1016）那行改为：

```python
        if not cfg.ocr_captions:
            free_vl_model()
        # else：留给 _stage_ocr_captions 复用同一驻留，由它跑完 free
```

- [ ] **Step 2: 新增 _stage_ocr_captions**

在 `_stage_vlm_captions` 函数**之后**加：

```python
# ============ Stage 11b: OCR caption（Qwen2.5-VL 逐字屏上文字） ============
def _stage_ocr_captions(cfg: PipelineConfig, state: PipelineState) -> None:
    # 屏上逐字文字 ground 章标题/abstract/recap。需 --keyframes + --ocr-captions，
    # 且仅 teaching/popsci（vlog/talk 屏上无教学文字，跳过）。
    if not (cfg.ocr_captions and cfg.keyframes and state.summaries):
        return
    if state.inferred_category not in ("teaching", "popsci"):
        print(f"      [ocr] category={state.inferred_category} 非 teaching/popsci，跳过 OCR",
              flush=True)
        return
    video_for_kf = _resolve_video_for_keyframes(state.video)
    if video_for_kf is None:
        print(f"      [ocr] 找不到 {state.video} 视频流，跳过 OCR", flush=True)
        return
    try:
        import ocr_vl
        from caption_vl import free_vl_model
        cache_path = OUTPUT_DIR / f"{_output_stem(state.audio, state.tag, cfg.summarizer, cfg.chunker, cfg.chunk_chars, keyframes=True)}.ocr.json"
        print(f"[ocr] Qwen2.5-VL 逐字 OCR {len(state.summaries)} chunks（每段 3 帧 union）...",
              flush=True)
        ocr_texts = ocr_vl.ocr_chunks(
            state.summaries, video_for_kf, lang=state.resolved_lang,
            frames_per_chunk=3, cache_path=cache_path)
        free_vl_model()
        if ocr_texts and len(ocr_texts) == len(state.summaries):
            for c, t in zip(state.summaries, ocr_texts):
                c["ocr_text"] = t or ""
        n_ok = sum(1 for t in (ocr_texts or []) if t)
        print(f"      [ocr] 写回 ocr_text，{n_ok}/{len(state.summaries)} 段有屏上文字",
              flush=True)
    except Exception as e:
        print(f"      [ocr] 异常：{e}（跳过 OCR，下游自然省略证据块）", flush=True)
        try:
            from caption_vl import free_vl_model
            free_vl_model()
        except Exception:
            pass
```

- [ ] **Step 3: 注册到 run 顺序**

找到调用 `_stage_vlm_captions(cfg, state)` 的地方（pipeline 主流程，grep `_stage_vlm_captions(`），在其**下一行**加：

```python
    _stage_ocr_captions(cfg, state)
```

（必须在 `_stage_vlm_captions` 之后、LLM 章节/标题/recap 生成之前。）

- [ ] **Step 4: 端到端 smoke（命中已有 ASR cache 的视频）**

挑一个本地有 ASR cache 的 teaching 视频（如 `BV1BE411D7ii_p68_p0`，先 grep `data/outputs` 确认 cache 在）。跑：
```
.venv/Scripts/python.exe src/pipeline.py "<p68 的 url 或本地路径>" \
  --summarizer neural --chunker texttile --chapters --keyframes \
  --llm-chapters --ocr-captions --learning-mode --lang zh --quality 360p
```
Expected: 日志出现 `[ocr] Qwen2.5-VL 逐字 OCR ... chunks`、`[ocr] OCR 出文字 N/M chunks`、`free after release`；跑完 `data/outputs` 下生成 `*.ocr.json`；产物 summary 里 chunk 带 `ocr_text`。第二次同样命令应见 `[ocr] 命中缓存`。

- [ ] **Step 5: Commit**

```bash
git add src/pipeline.py
git commit -m "feat(ocr): pipeline OCR stage + VL 单驻留复用（caption 后条件 free）+ category 门控"
```

---

## Task 5: `src/ocr_vocab.py` — B 路词表 + 保守校正

**Files:**
- Create: `src/ocr_vocab.py`

- [ ] **Step 1: 写 ocr_vocab.py**

```python
"""B 路：从 chunk 的 ocr_text 建本视频术语词表，保守模糊校正 ASR 错字。

只改 headline / keywords 里**高置信**匹配到屏上术语的 token（幻灯片写"数据链路层"、
ASR 听成"数据连络层"→改）。保守闸沿用 AK→ACK 教训：歧义/低相似不改，避免误伤。
零新依赖：jieba 抽词 + difflib 比相似度。
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

# 屏上英文/符号术语：命令、flag、Ctrl+X、CamelCase、代码标识符
_EN_TERM_RE = re.compile(r"(?:/[a-zA-Z][\w-]+|--[a-zA-Z][\w-]+|Ctrl\+\w|[A-Z][a-z]+[A-Z]\w+|[a-zA-Z_][\w]{2,})")


def build_vocab(chunks: list[dict]) -> dict:
    """返回 {"cjk": set[str], "en": set[str]}。cjk 是 jieba 名词短语，en 是标识符/命令。"""
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
        for w, flag in pseg.cut(text):
            if len(w) >= 2 and not w.isascii() and (flag.startswith("n") or flag == "nz"):
                cjk.add(w)
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
            if _cjk_char_diff(tok, v) <= max(1, len(tok) // 3) \
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
            for tok in set(jieba.cut(hl)):
                fixed = correct_token(tok, vocab)
                if fixed:
                    new_hl = new_hl.replace(tok, fixed)
                    n_fix += 1
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
```

- [ ] **Step 2: 单元自检（不需模型）**

Run:
```
.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'src'); import ocr_vocab as o; \
ch=[{'ocr_text':'数据链路层\n透明传输','headline':'数据连络层与透明传输','keywords':['数据连络层']}]; \
v=o.build_vocab(ch); print('链路' in ''.join(v['cjk']) or '数据链路层' in v['cjk']); \
n=o.correct_headline_and_keywords(ch, v); print(n>=1, ch[0]['headline'], ch[0]['keywords'])"
```
Expected: 第一行 `True`；第二行 `True 数据链路层与透明传输 ['数据链路层']`（"连络"被校正回"链路"）。

- [ ] **Step 3: 反向自检——歧义不改**

Run:
```
.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'src'); import ocr_vocab as o; \
print(o.correct_token('完全无关词', {'cjk':{'某个术语','另个术语'},'en':set()}) is None)"
```
Expected: `True`（无高置信唯一候选 → 不改）。

- [ ] **Step 4: Commit**

```bash
git add src/ocr_vocab.py
git commit -m "feat(ocr): src/ocr_vocab.py B 路词表 + 保守模糊校正 ASR 错字（零新依赖）"
```

---

## Task 6: pipeline 接入 B 路校正 stage

**Files:**
- Modify: `src/pipeline.py`（`_stage_ocr_captions` 写回 `ocr_text` 之后，立即建词表 + 校正）

- [ ] **Step 1: 在 OCR stage 末尾追加校正**

在 `src/pipeline.py::_stage_ocr_captions` 里，`for c, t in zip(...) c["ocr_text"]=...` 写回循环**之后**、`print(f"      [ocr] 写回 ocr_text...")` 之前，加：

```python
            try:
                import ocr_vocab
                vocab = ocr_vocab.build_vocab(state.summaries)
                n_fix = ocr_vocab.correct_headline_and_keywords(state.summaries, vocab)
                print(f"      [ocr-vocab] 词表 cjk={len(vocab['cjk'])} en={len(vocab['en'])}，"
                      f"校正 headline/keywords {n_fix} 处", flush=True)
            except Exception as e:
                print(f"      [ocr-vocab] 校正异常：{e}（跳过 B 路，保留原 headline）",
                      flush=True)
```

- [ ] **Step 2: 端到端 smoke（复用 Task 4 的 OCR 缓存，秒级）**

重跑 Task 4 的命令（OCR 命中缓存，只跑下游）。
Expected: 日志出现 `[ocr-vocab] 词表 cjk=... en=...，校正 headline/keywords N 处`；若该视频有 ASR 同音错字且屏上有正确写法，N>0；无错字 N=0 也正常（不报错）。

- [ ] **Step 3: Commit**

```bash
git add src/pipeline.py
git commit -m "feat(ocr): pipeline 接入 B 路——OCR 词表校正 headline/keywords"
```

---

## Task 7: A 路 — segment_llm 三处注入【屏幕文字】证据块

**Files:**
- Modify: `src/segment_llm.py`（`generate_chapter_recaps` ~2899-2919；`_run_title_one` ~1894-1897；`generate_chapter_abstracts` ~2666+ 的 per-chunk body 循环）

> 三处都是在 `内容: {snippet}` 行**之后**追加 `屏幕文字: {ocr}` 行（仅该 chunk 有 ocr_text 时），并在各自 prompt 加统一约束子句。OCR snippet 截断到 ≤120 字避免 prompt 膨胀。

- [ ] **Step 1: 加共享约束常量**

在 `src/segment_llm.py` 顶部常量区（其它 `_*_CLAUSE` / SYSTEM 附近）加：

```python
_OCR_EVIDENCE_CLAUSE = (
    "\n【屏幕文字】是画面逐字转写，用来：(1) 校正专有名词/命令/术语的准确写法；"
    "(2) 在讲解明确说明其作用时可引用准确名称。**严禁**为屏幕文字里的 token 编造"
    "未在讲解中出现的作用/定义；与本段无关的屏幕文字忽略。\n")


def _ocr_line(chunk: dict, max_len: int = 120) -> str:
    """chunk 有 ocr_text 时返回 '    屏幕文字: ...' 行（截断），否则空串。"""
    import re as _re
    t = (chunk.get("ocr_text") or "").strip()
    if not t:
        return ""
    t = _re.sub(r"\s+", " ", t)[:max_len]
    return f"\n    屏幕文字: {t}"
```

- [ ] **Step 2: recap 注入**

在 `generate_chapter_recaps` 的 per-chunk 循环里（`lines.append(f"    内容: {snippet}")` 之后，grep 定位），加：

```python
            ocr_ln = _ocr_line(sub_c)
            if ocr_ln:
                lines.append(ocr_ln.lstrip("\n"))
```

并把 recap 的 `user_prompt` 拼接里加上约束：找到 `f"{titles_clause}{drop_clause}\n{body}\n\n"`，改为：

```python
                   f"{titles_clause}{drop_clause}{_OCR_EVIDENCE_CLAUSE}\n{body}\n\n"
```

- [ ] **Step 3: title 注入**

在 `_run_title_one` 里（`lines.append(f"    内容: {snippet}")` 之后，line ~1897），加：

```python
        ocr_ln = _ocr_line(c)
        if ocr_ln:
            lines.append(ocr_ln.lstrip("\n"))
```

并在 `user_prompt` 的 `{drop_clause}{dup_headline_clause}\n` 后插入 `{_OCR_EVIDENCE_CLAUSE}`：

```python
        f"{drop_clause}{dup_headline_clause}{_OCR_EVIDENCE_CLAUSE}\n"
```

- [ ] **Step 4: abstract 注入**

abstract 的 per-chunk body 在 **`_run_abstract_batch`**（line ~2598），不是外层 `generate_chapter_abstracts`。在 `_run_abstract_batch` 里 `lines.append(f"    内容: {snippet}")`（line ~2631）**之后**加：

```python
            ocr_ln = _ocr_line(sub_c)
            if ocr_ln:
                lines.append(ocr_ln.lstrip("\n"))
```

并把该函数 user_prompt 里的 `f"{drop_clause}\n{body}\n\n"`（line ~2645）改为：

```python
                   f"{drop_clause}{_OCR_EVIDENCE_CLAUSE}\n{body}\n\n"
```

（chunk 变量是 `sub_c`、行列表是 `lines`，与 recap 一致。）

- [ ] **Step 5: 语法自检**

Run: `.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'src'); import segment_llm; print('ok')"`
Expected: `ok`，无 SyntaxError。

- [ ] **Step 6: 端到端 smoke（OCR 缓存命中，看证据块进 prompt）**

重跑 Task 4 命令（带 `--ocr-captions`）。
Expected: recap/abstract/title LLM 调用正常完成，无 parse 报错；产物章标题/abstract/recap 仍合法（不退化、不出现把"屏幕文字:"字面写进结果）。

- [ ] **Step 7: Commit**

```bash
git add src/segment_llm.py
git commit -m "feat(ocr): A 路——recap/abstract/title 注入【屏幕文字】证据块 + 反编造约束"
```

---

## Task 8: 验证 harness + 决策 gate

**Files:**
- Create: `scripts/_dryrun_ocr.py`（单视频看 OCR 质量）
- Create: `scripts/compare_ocr_ablation.py`（with/without 对照）

- [ ] **Step 1: 写 _dryrun_ocr.py**

```python
"""单视频跑 OCR pass，打印每 chunk 的 ocr_text，人工核质量。
用法: .venv/Scripts/python.exe scripts/_dryrun_ocr.py <summary.json 路径> <视频路径>
summary.json 里要有带 start/end/keyframe 的 chunks。"""
import sys, json
sys.path.insert(0, "src")
import ocr_vl

chunks = json.loads(open(sys.argv[1], encoding="utf-8").read())
if isinstance(chunks, dict):
    chunks = chunks.get("chunks") or chunks.get("summary") or []
texts = ocr_vl.ocr_chunks(chunks, sys.argv[2], frames_per_chunk=3)
for i, (c, t) in enumerate(zip(chunks, texts)):
    print(f"\n=== chunk {i+1} [{c.get('start')}-{c.get('end')}] hl={c.get('headline','')[:30]}")
    print(t or "(无屏上文字)")
```

- [ ] **Step 2: 跑 dryrun（claudecode 或 p68）**

Run（路径按实际 summary.json + 视频替换）:
```
.venv/Scripts/python.exe scripts/_dryrun_ocr.py "<summary.json>" "<video.mp4>"
```
Expected: 终端类视频应 OCR 出命令名（`/rewind` `/compact` `!` 等）；PPT 类应 OCR 出幻灯片标题。人工判：屏上文字是否被逐字读对、有无明显幻觉。

- [ ] **Step 3: 写 compare_ocr_ablation.py**

```python
"""对照 with/without OCR：读两个 chapters.json，diff 章标题/abstract/recap。
用法: .venv/Scripts/python.exe scripts/compare_ocr_ablation.py <base_chapters.json> <ocr_chapters.json>"""
import sys, json

def load(p):
    d = json.loads(open(p, encoding="utf-8").read())
    return d.get("chapters") or d

base = load(sys.argv[1]); ocr = load(sys.argv[2])
for i, (b, o) in enumerate(zip(base, ocr)):
    bt, ot = b.get("title",""), o.get("title","")
    if bt != ot:
        print(f"[ch{i+1} 标题] base: {bt}\n           ocr : {ot}")
    ba, oa = (b.get("abstract") or "")[:120], (o.get("abstract") or "")[:120]
    if ba != oa:
        print(f"[ch{i+1} abstract] base: {ba}\n               ocr : {oa}")
```

- [ ] **Step 4: 端到端对照三视频**

对 **claudecode**（终端命令）、**一个王道 PPT**（p68 中断系统 或 p93 万维网）、**英文 EH5jx5qPabU** 各跑两遍：一遍不带 `--ocr-captions`（产物存到 A 目录），一遍带（存到 B 目录），用 `compare_ocr_ablation.py` diff。
人工评估三条：
1. claudecode：`!`/`cmd`/命令名幻觉是否消、命令名是否正确。
2. PPT：幻灯片标题是否 ground 章标题、ASR 同音错字是否被 B 路校正。
3. 英文：屏上 token 是否读对、布局不崩。
回归 sanity：`.venv/Scripts/python.exe scripts/scan_recap_misalign.py` 与 `scripts/scan_en_leak.py` 不新增命中。

- [ ] **Step 5: 决策 gate（按 feedback-iteration-style）**

- **有清晰增益**（命令名正确化、幻觉减少、PPT 标题被 ground）→ 保留，进收尾（更新 memory、考虑 web 默认链路是否开 `--ocr-captions`）。
- **marginal / 净负**（同 anchor 实验）→ 干净标记"已尝试 OCR，收益不足，原因 XX"，回退代码改动，**不硬扛**。

- [ ] **Step 6: Commit 验证脚本**

```bash
git add scripts/_dryrun_ocr.py scripts/compare_ocr_ablation.py
git commit -m "test(ocr): OCR dryrun + with/without 对照验证脚本"
```

---

## Self-Review 备注

- **Spec 覆盖**：范围(广/teaching)→Task4 category 门控；引擎(VL 复用)→Task2；3 帧 union→Task2；混合 C 的 B 路→Task5/6、A 路→Task7；门控/缓存→Task1/3/4；内部 ground 不上 web→全程不碰 web/md；验收→Task8。全覆盖。
- **无 pytest**：已在 header 显式说明，验证走 dryrun/smoke/compare 脚本。
- **类型一致**：`ocr_chunks(chunks, video_path, lang, frames_per_chunk, model_dir, cache_path)`、`build_vocab→{"cjk","en"}`、`correct_token`/`correct_headline_and_keywords`、`_ocr_line`/`_OCR_EVIDENCE_CLAUSE` 跨 Task 命名一致。
- **零回归保证**：flag off / 非 teaching / OCR 全失败 → `ocr_text` 全空 → B 跳过、A 不注入 → 行为同现状。
