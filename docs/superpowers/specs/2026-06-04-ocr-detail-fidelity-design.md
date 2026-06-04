# 设计：OCR 关键细节保真（屏上文字 ground 生成）

日期：2026-06-04
状态：已设计，待实现（优化方向 #1「关键细节保真」的正路；接 anchor 注入实验失败之后）

## 背景与动机

学习类笔记的章标题 / abstract / recap 由 LLM 基于 **ASR 转写**生成。但转写本身
**缺屏上独有语义**：

- **终端/代码演示类**（claudecode）：讲师说"这个命令"（指示代词），真正的命令名
  （`/rewind` `/compact` `/clear` `!` 等）只在屏幕上、不在 ASR 里 → LLM 编造作用
  （ch1 `!`→「自动同意所有权限申请」、`cmd`→「进入前端设计模式」均为幻觉）。
- **PPT 教学类**（王道考研等，语料主体）：幻灯片标题是 gold-standard 章节标签，
  但 ASR 同音错字会污染章标题（"数据链路层"→"数据连络层"），而幻灯片上的准确写法
  从未进入生成链路。

**先前失败的路（2026-06-03，见 [[project-recap-anchor-experiment]]）**：从 ASR 转写
程序化抽「操作锚点」逐字注入 recap prompt。净负——ASR token 本身缺语义，把它列成清单
反而给 LLM "必须交代它"的压力，诱发更多编造。结论：真正的细节保真要靠 **OCR**，
不是在缺语义的 ASR token 上硬贴。

**本设计**：用已接入的 Qwen2.5-VL 读屏上**逐字真文字**，两路 ground 生成。与 anchor
的本质区别——OCR 给的是**画面真实可见的正确文字**（名字对的），不是 ASR 听错的 token。

## 范围与决断（经用户确认）

- **OCR 范围**：广——全 teaching/popsci（含 PPT），ground 章标题 + abstract + recap 多环节。
- **OCR 引擎**：复用 **Qwen2.5-VL-7B-Instruct-AWQ**（已接入、串行加载已解决、读字能力强、
  零新依赖、不动脆弱的 torch 2.3.1 / autoawq 0.2.6 环境）。
- **抽帧**：每 chunk 等间距 **3 帧**各跑 OCR，行级 union 去重（覆盖幻灯片切换 / 短暂命令，
  补单关键帧漏抓）。
- **grounding 策略**：**混合 C** = B（Python 词表确定性校正 ASR 错字，稳赢）+ A（prompt
  证据块 + 严格反编造约束，补屏上新术语）。
- **输出面**：仅内部 ground 进 prompt，**不上 md/web**（YAGNI，回归面最小）。

## 架构与数据流

```
pipeline (category ∈ {teaching, popsci} 且 --ocr-captions)
  └─ caption_vl.load_vl_model()            # VL 一次驻留（串行加载已解决）
       ├─ caption pass : 每 chunk 1 张 CLIP 关键帧 → 1 句 caption        [现状]
       ├─ OCR pass(新) : 每 chunk 3 帧 → 逐字 OCR → 行级 union 去重       [新增]
       └─ caption_vl.free_vl_model()
  → chunk["ocr_text"] (+ 落盘缓存)
  → B: 全 chunk OCR → 本视频词表 → Python 保守模糊校正 ASR 错字
       (headline / 章标题 / keywords)
  → A: per-chunk【屏幕文字】证据块注入 章标题 / abstract / recap prompt
```

VL 模型在同一次驻留内先做 caption（1 帧/chunk）、再做 OCR（2-3 帧/chunk），不额外
load/free。OCR 抽帧复用 `keyframe.sample_frames_for_ranges`。

## 组件

### 1. `src/ocr_vl.py`（新建）

- **复用 VL 单例**：调 `caption_vl.load_vl_model()` 拿已加载的 `(model, processor)`，
  **不二次加载**。若调用时模型未加载则触发加载（独立可用）。
- **OCR system prompt**：
  > 你是屏幕文字转写器。逐字转写画面中所有清晰可读的文字：幻灯片标题/正文/公式、
  > 代码、终端命令、菜单项、按钮文字、符号。只转写真实可见的文字，看不清/没有就
  > 返回空字符串。**绝不补全、绝不翻译、绝不解释、绝不描述画面。**
- **接口**：`ocr_chunks(chunks, video_path, lang="zh", frames_per_chunk=3) -> list[str]`，
  返回与 chunks 等长的 `ocr_text`（每段 union 去重后的多行文字，无文字 → `""`）。
- **union 去重**：3 帧各自 OCR 出的行，按归一化（去空白/小写比较）去重，保留原文；
  幻灯片渐进出现（同标题多帧重复）只留一份。
- **失败降级**：单帧打开/推理失败 → 跳过该帧 union 其余；全帧失败 → 该段 `""`。

### 2. OCR 缓存

- 按 `video_id + chunk ranges hash` 落盘（同 ASR partial cache / keyframe 体系，
  目录沿用 `data/cache` 或与 keyframes 同级）。
- pipeline 复跑命中缓存则跳过 VL OCR（OCR 是重推理，缓存是复跑下游的前提）。

### 3. B 路 — Python 词表确定性校正 `src/ocr_vocab.py`（新建）

> 单独建模块而非塞进 segment_llm（已 3814 行，过大）：词表构建 + 校正逻辑自成单元，
> segment_llm 的 `_calibrate_headline_words` 调用它。

- **建词表**：遍历全 chunk `ocr_text` 抽候选术语——
  - CJK：jieba 名词短语（过 stopword，长度 ≥2）。
  - 英文/符号：标识符 / 命令 regex（`/[a-z]+`、`Ctrl\+\w`、CamelCase、代码 token、
    `--flag` 等）。
- **校正**：对 headline / 章标题 / keywords 中的 token，在词表里找**高相似**匹配
  （编辑距离 + CJK 同音/形近）做替换。
- **保守闸**（沿用 [[project-asr-correction-dict-expansion]] AK→ACK 锚定教训：高相似度才改、
  歧义/低置信不改，避免误伤）。扩现有 `_calibrate_headline_words` / `_DOMAIN_CORRECTIONS`
  为**按视频自动派生**而非全局静态字典。

### 4. A 路 — Prompt 证据块（segment_llm 内）

- `generate_chapter_recaps` / `generate_chapter_abstracts` / 章标题生成 的 per-chunk
  body，在 `内容: <snippet>` 后追加 `屏幕文字: <ocr_text 截断>` 行（仅该段有 OCR 时）。
- **统一约束块**（system 或 user 前缀）：
  > 【屏幕文字】是画面逐字转写，用来：(1) 校正专有名词/命令/术语的准确写法；
  > (2) 在讲解明确说明其作用时，可引用准确名称。**严禁**为屏幕文字里的 token 编造
  > 未在讲解中出现的作用/定义；与本段无关的屏幕文字忽略。
- snippet 长度复用现有 `snippet_max`（K≤8 取 200，否则 120）同量级限制，避免 prompt 膨胀。

## 门控

- **新 CLI flag**：`--ocr-captions`（独立于 `--vlm-captions`，因 OCR 是额外 ~3x 帧推理成本，
  用户应能单独开关）。
- **category-gate**：仅 `category ∈ {teaching, popsci}` 生效；vlog/talk 即使 flag on 也跳过
  （recap/OCR 概念在 vlog 上无意义，同现有 recap 门控）。
- **默认 off**：起步同 `--vlm-captions`（探索期默认关），验证有正收益后再在 web 默认链路开。

## 错误处理与边界

- OCR 全失败 / flag off / 非 teaching → `ocr_text` 全空 → B 跳过校正、A 不注入证据块
  → 行为 == 现状，**零回归**。
- VL OCR 自身可能误读（VL 非专用 OCR）：B 的保守闸拦低置信校正；A 的反编造约束限制
  误读 token 被当真。误读文字最坏情况是"多一条无用证据"，不强制使用。
- 抽帧失败（转场黑帧 / cv2 读不到）：union 其余帧；复用 `sample_frames` 已跳首尾边界逻辑。
- 缓存键含 chunk ranges：分段变了缓存自然失效重算，不会串旧结果。

## 测试与验收

- **单元**：`ocr_vl.ocr_chunks` 在 1 个终端类 + 1 个 PPT 类视频上跑通，人工核 union 去重、
  空段降级。
- **校正闸**：B 在已知 ASR 错字案例（数据链路层 / AK→ACK 类）上验证「该改的改、歧义的不改」。
- **端到端对照（核心验收）**：选 3 视频跑 with/without `--ocr-captions`，diff 章标题 /
  abstract / recap——
  - **claudecode**（终端命令）：命令名是否正确、`!`/`cmd` 幻觉是否消。
  - **一个王道 PPT**（如 p68 中断系统 / p93 万维网）：幻灯片标题是否 ground 章标题、
    ASR 同音错字是否被校正。
  - **一个英文视频**（EH5jx5qPabU）：英文屏上 token 是否正确、布局不崩。
- `scan_recap_misalign.py` + `scan_en_leak.py` 做回归 sanity check。
- **判定**：按 [[feedback-iteration-style]] 先精后广——若对照下增益 marginal，干净标记
  「已尝试 OCR，收益不足」并回退，不硬扛。

## 非目标（YAGNI）

- 不引专用 OCR 引擎（PaddleOCR/EasyOCR/Tesseract）——避免破坏 torch/autoawq 环境。
- OCR 文字不上 md/web（仅内部 ground）。
- 不做跨视频全局 OCR 词表沉淀（每视频自建词表即可）。
- 不 ground vlog/talk 类。
- 不改 keyframe 抽取 / 多模态切分 / 数据 schema 对外契约（仅给 chunk 加 `ocr_text` 内部字段）。

## 关联

- [[project-recap-anchor-experiment]]：anchor 注入失败 → 认定 OCR 是正路（本设计直接承接）。
- [[project-vlm-caption]]：复用 Qwen2.5-VL caption 基础设施（同一 VL 驻留加 OCR pass）。
- [[feedback-serial-model-loading]]：VL 串行加载约束已由 caption_vl 解决，OCR 同窗复用。
- [[feedback-prompt-vs-python]]：B 路把名词校正搬 Python（确定性）> 让模型自己 NLP 判定。
- [[project-asr-correction-dict-expansion]]：B 的保守校正闸沿用 AK→ACK 锚定教训。
- [[feedback-iteration-style]]：marginal 增益直接放弃的验收判定。
- [[project-chapter-title-calibration]]：现有 `_calibrate_headline_words` 是 B 的扩展点。
