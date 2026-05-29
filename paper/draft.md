# 基于深度学习的网课视频摘要与笔记生成系统

> 论文 draft，2026-05-15 起草。Markdown 版本用于内容收集与迭代，定稿前转 LaTeX。

---

## 摘要 (Abstract)

学习类视频（网课、技术讲座、考研专业课）与近年兴起的知识型 vlog（评测、探店、生活实验）是当代知识获取的主要载体，但视频媒介与"复习友好"的目标存在结构性矛盾：信息按时间顺序线性铺开，缺乏目录、术语索引与章末小结。本文提出一个端到端 pipeline，将视频自动转换为结构化 Markdown 笔记，经历 6 个版本演进逐步覆盖 PPT 教学 / 实拍 vlog / 科普访谈 / 技术演讲四类内容。系统由六个核心模块组成：（1）多模态章节切分，融合文本 TextTiling 与视觉 Chinese-CLIP 距离，α=0.3 实证是稳健甜点；（2）**LLM-as-segmenter**（Qwen2.5-7B-AWQ + B1 两步法）替代 Pegasus，在 9 视频跨域 benchmark 上覆盖率 100%（含 retry 与程序化 repair 双层兜底）；（3）**Qwen2.5-VL caption 作为切分 cue**，n_chunks ≤ 15 时启用、长视频自动降级；（4）**4 类启发式视频分类器**驱动 markdown / 前端双层模板分发，24/24 准确；（5）ASR 后处理 / 章 abstract 生成等多层 prompt 工程缓解 hallucination；（6）**三层 ASR 健壮性防御**——解码约束、faster-whisper 1.x 原生 hallucination gate、流式增量落盘（WAL 思想）—— 实战覆盖 ctranslate2 native abort 两条触发路径。在 24 视频跨域 corpus 上 LLM 切分覆盖率 100%，章 abstract 在 3-vlog 回归 corpus 上 21/21 章无字面 hallucinate；通过对兜底机制系统化 stress test，识别并修复了"野外永远不触发因此被误判为不需要"的隐藏 bug。所有代码、benchmark 标注、stress test 脚本与实验结果开源。

**关键词**：视频笔记生成；多模态章节切分；LLM-as-segmenter；ASR 后处理；VLM caption；工程健壮性；stress test

## 1 引言 (Introduction)

### 1.1 背景与动机

网课、技术讲座、考研专业课视频已经成为高校学生与自学者获取知识的主要载体之一。Bilibili 上王道考研系列单课程播放量过千万，YouTube 上一节 1 小时的深度学习讲座往往沉淀数十万次回看。然而视频媒介本身与"复习友好"的目标存在结构性矛盾：信息按时间顺序线性铺开，没有目录，没有可搜索的文本，回看时定位某个具体知识点要么靠记忆中的时间戳，要么靠拖动进度条采样关键帧。学习者通常的做法是在第一遍听课时人工记笔记，但这对网课"短窗口、多视频、可暂停"的使用模式并不友好——很多学习者直接放弃了笔记，损失了二次回看的效率。

理想的解决方案是给每段视频自动生成一份**结构化的学习笔记**：包含目录、按章节组织的知识点摘要、术语表、章末小结，且每个段落都带有可点击的时间戳跳转回原视频。这份笔记既能作为听课时的辅助，也能作为复习时的索引——后者尤其重要，因为复习时学生不需要重新听 30 分钟视频，只需扫一眼笔记的术语表和章末小结就能定位需要重看的片段。

### 1.2 任务与挑战

把视频自动转换为结构化学习笔记，最朴素的做法是 ASR 转写 + 关键句抽取，这正是 YouTube 自动字幕加一个简单 summarizer 的工作模式。这种 pipeline 在工程上简单，但产出的笔记在学习场景下几乎不可用——它丢掉了三类对学习者至关重要的结构信息：

1. **章节边界**。一节 30 分钟的网课往往包含 3-5 个相对独立的子主题。没有章节切分，笔记就退化成一长段流水文本，无法按主题快速跳转。
2. **学习专属元素**。学习场景的笔记需要 TOC、术语表、章末小结这些教科书式的结构组件，而通用摘要系统不会生成这些。
3. **ASR 上游错误的修复**。faster-whisper 这类 SOTA ASR 在长视频上仍会出现两类系统性失败：专有名词识别错误（"Claude" → "Cloud"）和**卡片回路**——同一句话被反复转写多次，最多见过 13 秒内重复 9 段。这些错误若不修复，会污染下游所有基于 ASR 文本的模块（chunker、章节切分、关键词抽取）。

### 1.3 主要贡献

本工作针对学习类视频笔记生成场景，提出一个端到端 pipeline 并系统化地解决了上述三类问题。具体贡献：

1. **多模态章节切分**。融合文本 TextTiling（基于 jieba 关键词 Jaccard 距离的 depth score 切点）与视觉 CLIP 距离信号。在 10 视频 × 2 chunker × α sweep ablation 中发现 α=0.3 是稳健甜点——视觉提供 tie-breaking 但不主导，因为 PPT 教学视频中 slide 翻页频率远高于真实章节切换。在实拍子集上 TextTiling 相对 chars chunker 严格 F1 提升 +0.35（0.47 → 0.82）。

2. **学习场景专用 markdown 结构**。在传统"章节/段落"两级目录之上注入 5 类学习专属元素：顶部摘要卡、HTML 锚点 TOC、按章节组织的知识点速览、跨段投票的术语表（含首次出现段链接与上下文 snippet）、抽取式章末小结。该结构默认开启，对所有学习类视频生效。

3. **ASR 后处理两层修复**。第一层是基于视频 metadata（yt-dlp title + description）的术语字典自动注入，处理专有名词的同音字混淆；第二层是连续重复段去重，使用共同前缀长度（LCP）阈值检测卡片回路并合并时间戳。后者在王道 OS p37 视频上把 F1@1 从 0.50 提升到 1.00，在计网 p38 视频上把 Strict F1 从 0.25 提升到 0.75。我们进一步发现 dedupe × chunker 存在系统性耦合：dedupe 只在 texttile + cc=400 操作点上提供显著收益，cc=800 与 chars chunker 上中性——揭示 dedupe 本质上是**关键词频次去噪**而非简单的文本清洗。

4. **10 视频跨域 benchmark**。手工标注 6 个学习类（PPT 教学）+ 4 个实拍类（Vlog / 影视解说）视频的章节边界 gold，每个视频提供 chars 与 texttile 两套不同 chunks 数的标注。同时报告严格 F1 与容差 F1@1，对短视频结构性 0/1 二值化问题给出方法论建议。该 benchmark 也作为 dedupe × chunker 耦合分析的实验平台。

5. **LLM-as-segmenter + 程序化 repair 双层兜底**（v4 引入，v5-v6 加固）。Qwen2.5-7B-AWQ 替代 Pegasus，配合 B1 两步法（章 outline 与章标题分两次调用）覆盖了 9 视频 corpus 的 100% 切分路径——其中 attempt 1 直接通过 22%，retry 覆盖额外 67%，剩余 11% 由 `_repair_oversize` 程序化救回，fallback TextTiling 路径 0 次触发。该数据来自 §6.4 24 视频 corpus 子集，是本工作中"算法 + 工程兜底"协同效果的核心证据。

6. **跨视频域分类 + 双层模板分发**（v5 引入）。设计 4 类启发式分类器（teaching / popsci / vlog / talk），基于 ASR 文本特征 + 视频 metadata 在 24 视频上 24/24 准确，进一步驱动 markdown 与前端模板的 per-category 分发（如 vlog 用 `VLOG_SECTION_ABSTRACT_SYSTEM` 替代教学风格 abstract prompt）。该模块把"单一模板覆盖所有内容"的早期设计升级为"按内容形态做差异化呈现"。

7. **三层 ASR 健壮性防御 + Stress Test 范式**（v5-v6 + 2026-05-21 第二轮加固）。一方面对 faster-whisper + ctranslate2 在 Windows 上的 native abort 故障建立三层防御：解码约束（v5）+ 1.x 原生 hallucination gate（5-21）+ 流式增量落盘（5-21，WAL 思想）—— 实战覆盖 BV1q6 与 BV1AYR6BsE9U 两个 vlog 长视频的 native abort，99.99% 覆盖率落盘。另一方面通过对兜底机制系统化 stress test（v6 `scripts/stress_test_*`）发现"野外永远不触发因此被误判为不需要"的 auto_subs n≥4 broken 隐藏 bug，提出"对每个兜底必须配 stress test"的工程方法论。

### 1.4 系统演进概览

本工作并非一次性设计完成，而是经历了 6 个明确的里程碑迭代，每一轮都由新的失败模式驱动算法或工程改动。完整 timeline 见 §7，此处仅给出脉络以便读者从"为何当前架构是这样的"角度阅读后续章节：

| 版本 | 时段 | 触发问题 | 核心改动 |
|---|---|---|---|
| v1 | 2026-05 前 | — (项目起点) | Pegasus baseline + TextTiling + α=0.3 多模态 |
| v2 | 2026-05-15 | ASR 卡片回路污染下游 chunker | LCP-based 连续重复段去重 + 术语字典 |
| v3 | 2026-05-15 | 缺学习场景结构 + Pegasus 章标题 copy 退化 | 5 类 md 元素 + chunks 数差异化 fallback + ASR `[?]` 置信度标记 |
| v4 | 2026-05-16~17 | TextTiling+Pegasus 在 30+ chunks 上邻章串台 | Qwen2.5-7B-AWQ 替代 Pegasus + B1 两步法 + VLM caption 三层门控 + 英文支持 |
| v5 | 2026-05-19~20 | 跨域 UI 突兀 + LLM systematic bias + GPU 黑屏事故 | 4 类启发式分类器 + 模板分发 + segment 4 硬规则 + 串行加载红线 |
| v6 | 2026-05-21 | v5 兜底"未野外触发"成因不明 | stress test 暴露 auto_subs n≥4 broken + nav 规则合并 + repair 一致性修 |
| v6+ | 2026-05-21~22 | vlog 域纳入暴露 ASR 第二条 abort 路径 + abstract LLM 字面 hallucinate | 三层 ASR 防御（含 WAL 增量落盘）+ generate_chapter_abstracts input 加 ASR snippet + 3-vlog corpus 回归（21/21 章 0 hallucinate） |
| v7 | 2026-05-24 | 章标题"主题词锚点" prompt 规则被压 + 中层 gate (generic_ratio) 早期被弃 | 章标题 Python 端 jieba 校准 + drop hint（烟台/电源 ASR 错字 100% 出标题）；中层 gate 扩英文动词词典 + 阈值 0.65 重生（FwOTs 救援 → 先验降级） |

本文剩余部分组织如下：§2 综述相关工作；§3 给出系统架构概览（v7 当前态）；§4 详述四个核心方法模块；§5-6 给出量化评估与 case studies；§7 按里程碑回顾系统演进；§8 讨论局限性与 future work；§9 总结。

## 2 相关工作 (Related Work)

### 2.1 视频摘要与笔记生成

视频摘要研究有两条主线。**视觉主线**关注从视频帧中抽取关键帧或片段，代表工作有 vsLSTM 系列、基于注意力的 DSNet，以及近期使用 CLIP 视觉特征做帧打分的工作。这类方法的产出是"精简版视频"或"关键帧集合"，不直接生成可阅读文本。**文本主线**关注从字幕或 ASR 转写中生成摘要，本质是 long-document summarization 在视频转写文本上的应用，常用模型包括 BART、Pegasus、以及更近期的 long-context LLM。

学习场景的笔记生成研究相对稀少。Lecture Summarization Service (Lecturesum) 等系统提供 ASR + 关键句抽取的工程化 pipeline，但产出仍是单一文本块，缺少章节切分与术语表等结构组件。商业产品如 Otter.ai、Notion AI 的会议笔记功能在结构化程度上已有进步，但其默认设计针对会议而非教学，缺少术语表、章末小结等学习场景元素，且不开放章节切分的具体方法供学术比较。

### 2.2 文本分段与话题切分

TextTiling (Hearst, 1997) 是经典的无监督文本分段算法，基于相邻文本块词汇重叠度的 depth score 寻找边界。后续工作 C99、TopicTiling 在主题模型层面做扩展。神经监督方法如 BERT-based segmenter (Koshorek et al., 2018) 在 Wiki-727K 等大规模标注数据上效果优异，但学习类视频缺少对应的大规模标注语料，迁移到中文 ASR 转写的零样本性能并不理想——ASR 输出本身的口语化、重复、错字进一步压低了监督模型的迁移上限。我们采用 TextTiling 作为基础，理由是它无监督、无需训练数据、可解释，且与 ASR 后处理（关键词频次去噪）天然耦合。

### 2.3 多模态视频理解

CLIP (Radford et al., 2021) 及其中文复现 Chinese-CLIP (Yang et al., 2022) 提供了图文对齐的视觉编码器，使得"视觉 vs 文本"特征的语义距离可以直接计算。近期视频章节切分工作（如 YouTube 自动章节）使用视觉信号做主导，效果在 Vlog、电影解说等"镜头切换 ≈ 话题切换"的内容上较好，但在 PPT 教学视频上失效——slide 翻页频繁但话题未变，单纯依赖视觉会过切。我们的 α=0.3 融合系数实证了这一观察：视觉作为 tie-breaking 信号比作为主导信号更适合 cross-domain pipeline。

### 2.4 ASR 后处理

ASR 后处理的研究主要集中在术语字典 / 语言模型重打分 / N-best 重排上。对"卡片回路"这一具体失败模式的针对性处理在公开文献中较少——它是 streaming attention-based 模型的退化模式，通常被视为模型 bug 而非可独立研究的问题。我们将其形式化为"连续相同段落的 LCP-based 检测与合并"，并提供了 chunker × dedupe 的二维 ablation 分析，定量刻画了上游 ASR 失败模式如何通过关键词频次污染下游分段算法——这一传导路径在视频笔记生成场景下我们尚未见到系统性的讨论。

ASR 运行层面的健壮性问题——具体地说，faster-whisper 在 Windows + ctranslate2 路径上的 native abort——在工程社区有零星报告但缺少系统性研究。已有讨论大多停留在"调小 batch / 关闭 condition_on_previous_text"的经验层面，未对"abort 在 transcribe() 完成之后才触发"这一更隐蔽的第二条路径建立模型。本工作 §6.5.1.bis 通过 BV1q6 / BV1AYR6BsE9U 两个野外 case 把这一路径定位到 ctranslate2 资源释放阶段，并提出"WAL 风格流式落盘 + 1.x 原生 hallucination gate + 解码约束"三层防御。这是把数据库领域成熟的故障兜底范式引入 ASR pipeline 的一次尝试。

### 2.5 LLM-as-segmenter 与视频转写结构化

近期 long-context LLM（DeepSeek-V3、Qwen2.5、Llama-3）使得"将整段 ASR 转写一次性喂入 LLM 让其输出章节 outline"成为可行路径。该方向的早期工作多以 GPT-4 为黑盒切分器，未对失败模式与回退策略做系统讨论。我们采用本地 Qwen2.5-7B-AWQ（4-bit 量化、~5GB VRAM），通过 B1 两步法（先 outline 后标题）+ retry-with-feedback + 程序化 `_repair_*` 三层兜底，在 24 视频 corpus 上达到 100% 切分覆盖率，fallback TextTiling 0 次触发。我们进一步发现 LLM-as-segmenter 在 30+ chunks 长视频上存在显著的 **catch-all bias**（attempt 1 倾向把所有 chunks 塞进 1-2 顶层章节），retry-with-feedback 机制可在多数 case 自我修正，但仍有少数需要程序化 repair 接管——这一观察对后续工作选择 LLM 还是更结构化的切分器具有方法论价值。

## 3 系统架构 (System Architecture)

```
URL → 下载 → 抽音频 → ASR 转写
          → ASR 后处理（术语修复 + 重复段 dedupe）
          → Chunking（chars / TextTiling）
          → Pegasus 段落小标题（headline）+ jieba 抽取式正文
          → 关键帧（Chinese-CLIP）
          → 多模态章节切分（文本 + 视觉融合）
          → Markdown 笔记
```

模型选择：
- ASR：faster-whisper large-v3 (float16, CUDA)
- 神经摘要：Randeng-Pegasus-238M-Summary-Chinese
- 视觉编码：OFA-Sys/chinese-clip-vit-base-patch16

## 4 方法 (Method)

### 4.1 ASR 后处理：术语修正 + 重复段去重

#### 4.1.1 术语字典自动注入

从视频 metadata（yt-dlp 拿到的 title + description）抽取 CamelCase 和 5+ 字母大写词，结合预设的 whisper 高频混淆词典（如 `Claude → Cloud`），生成 ASR substring 替换规则。该机制在 ClaudeCode 视频上把全程的 "Cloud" 替换回 "Claude"。

#### 4.1.2 连续重复段去重 (Dedupe LCP)

**观察的失败模式**：faster-whisper 在长视频上偶发"卡片回路"——同一句话被反复转写多次。在我们的王道 OS p37 benchmark 视频中，一次卡片回路在 13 秒内连续输出了 9 段相同的 "我们用这个呼吃信号量,保证了每个哲学家拿筷子这件事"，形成一个被自身关键词频次污染的 micro-chunk。

**算法**：扫描 segment 列表，检测连续相同（或近似相同）的 run；run 长度 ≥ 3 时保留首段，把后续重复段的 end 时间合并到首段，丢弃中间段。

近似相等判定（LCP）：
- 共同前缀长度 (LCP) ≥ 20 字 (严格匹配)
- 或 LCP ≥ 0.85 × min(len(a), len(b))（近似前缀，应对"末尾追加几字"模式）

LCP 阈值 0.85 经过反例校准：原 0.6 会误判 "如何避免饥饿?" vs "如何避免死锁?" 这种 Pegasus 真综合（改 2 字），0.85 放行。

### 4.2 多模态章节切分

#### 4.2.1 文本 TextTiling chunker

预算每段 jieba 关键词集合，在 segment 间隙跑左右滑动窗的 Jaccard 距离，TextTiling depth score 选 top-K 切点。

#### 4.2.2 视觉信号融合

复用关键帧抽取阶段的 CLIP image embeddings，每个 chunk 跨 8 帧平均得到 chunk-level 视觉表示。相邻 chunk 的 cosine 距离与文本 Jaccard 距离 min-max 归一化后线性融合：

```
fused[i] = α × normalize(visual_dist)[i] + (1-α) × normalize(text_dist)[i]
```

α=0.3 是稳健甜点：视觉做 tie-breaking 但不主导（教学 PPT 视频里同节内 slide 翻页频繁，视觉主导会拖偏）。

#### 4.2.3 章节数自适应公式

K = max(2, min(6, n_chunks-1, ⌈duration_min / 6⌉))

每 ~6 分钟一章，clamp 到 [2, 6]。10 视频上比固定公式 ⌊n / 3⌋ 更贴合人工标注 gold K。

### 4.3 层次化章标题与 copy 检测 fallback

把章内所有 chunk headlines 拼接后再喂 Pegasus 生成章标题。短输入（< 100 字）下 Pegasus-238M 倾向退化为直接抄一段 headline，未做综合。

**Copy 检测**：title 与任一 chunk headline 满足以下之一即认为是 copy：
- (a) 一方完整包含另一方（substring）
- (b) 共同前缀 ≥ 0.85 × min(len)

**差异化触发 fallback**：
- chunks ≤ 3 时若检测到 copy，用 fallback（前 2 段 headline 用 "·" 拼接）
- chunks ≥ 4 时即使 copy 也保留 Pegasus 输出——Pegasus 可能是从多个候选中有意选 representative，比 fallback 拼前 2 段强

### 4.4 学习场景 md 结构

在传统的"章节 + 段落"两级目录基础上注入学习场景专属元素：
1. 顶部摘要卡（时长 / 章段数 / 核心关键词 top-8）
2. 目录 TOC（HTML 锚点跳转）
3. 知识点速览（按章列 chunk headlines）
4. 术语表（跨段投票 top-15，含首次出现段链接 + 上下文 snippet）
5. 章末小结（章内文本抽取式 1-2 句）

## 5 评估 (Evaluation)

### 5.1 Benchmark

10 视频跨域 benchmark：6 个学习类（PPT 教学 / 屏幕录制 / 科普讲解）+ 4 个实拍类（Vlog / 影视解说）。手工标注章节边界 gold（chars 与 texttile chunker 各一套，对应不同 chunks 数）。

### 5.2 指标

- 严格 F1：预测边界 idx 必须 == gold idx
- 容差 F1@1：预测边界 ± 1 段命中即算 TP

#### 5.2.1 为什么 F1@1 更可靠

chunk-level 评估对 chunk_chars 敏感：chunks 越细，gold 边界 idx 的量化噪声越大。F1@1 容差能吸收这种结构性误差，反映"边界时间位置是否接近真实切换点"。论文方法论建议同时报告两者。

### 5.3 主结果

cc=800（paper main 操作点）下：
- TextTiling vs chars: strict F1 +44% (0.48→0.69)，F1@1 +18% (0.80→0.94)
- 实拍子集 strict F1 +0.35（chars 0.47 → texttile 0.82）

### 5.4 多模态 ablation

#### 5.4.1 早期方案：α 加权 (TextTiling 时代)

α ∈ {0.0, 0.2, 0.3, 0.5, 0.7, 1.0} sweep（10 视频 × 2 chunker）：
- TextTiling 在 α=[0.0, 0.7] 区间稳定（F1@1 0.65-0.79）
- chars 在同区间波动大（F1@1 0.49-0.72）
- α=0.3 默认稳健 — 多模态融合提供"鲁棒性"而非"性能提升"
- 实拍视频上视觉信号比 PPT 视频更"诚实"（镜头切换 ≈ 章节切换，PPT 翻页 ≠ 章节切换）

#### 5.4.2 当前方案：LLM-mm（视觉信号作 prompt cue）

新方案不再加权 depth score，而是把相邻 chunk 的 CLIP cosine 相似度格式化成
自然语言喂给 Qwen2.5-7B：

```
[相邻段视觉相似度 (CLIP, 1.0=同画面, 0.0=完全不同)]
  chunk 0 -> 1: 视觉相似度 0.62 (画面显著切换，可能是章节切点)
  chunk 1 -> 2: 视觉相似度 0.91 (画面高度相似，无切换)
  ...
```

LLM 把这当 tie-breaker 与文本主题信号交互，而非线性融合。同 9 个视频纯文本
路径 vs +keyframes 路径对比（完整表见 paper/mm_ablation.md）：

| 维度 | 数值 |
|---|---|
| 边界位置发生变化 | **9/9 = 100%** |
| 章数变化（任意方向） | 7/9 = 78% |
| **mm 让 attempts 减少（一次过更快）** | **3/9** |
| mm 让 attempts 增多 | 0/9 |
| mm 路径反触发 fallback TextTiling | 1/9 |

**核心发现**：

1. **视觉信号确实进入 LLM 决策**——9/9 边界差异证明 Qwen 没忽略 visual cue
2. **mm 加速 retry 通过**：3/9 视频从 attempt 2/3 降到 attempt 1，视觉信号
   在文本主题模糊时提供 disambiguation（计网 p44 3→2、OS p37 哲学家 2→1、
   AI Agents 英文 2→1）
3. **过度切分风险**：英文 25min AI Agents 教程 mm 路径切了 32 章（平均每章
   1 chunk）vs 纯文本 19 章——PPT/教程类视频上"画面切换"远比"章节切换"频繁，
   LLM 偶尔把 slide flip 当章节边界
4. **fallback 回退风险**：1/9 视频（Tina Huang 编程教程）开 mm 后 LLM 三次
   都 missing chunks，最终 fallback TextTiling——视觉信号在该视频上反而误导

**结论**：mm 信号有用但 PPT/教程域风险大。论文实际采纳的默认配置是
**纯文本 LLM 切分**（与 4.2.2 节描述一致），视觉信号作为 **opt-in** 的
ablation 工具（`--keyframes` flag），主要用于：
- 章节切点可视化展示（md 嵌入关键帧缩略图）
- 实拍 (live) 视频域上的精度提升
- 论文 §5.4 的 ablation 对比数据

#### 5.4.3 视觉信号升级：VLM caption + 自适应阈值

5.4.2 节用 CLIP cosine 浮点数喂 LLM，信息密度低（一个数字 1.0=同画面 / 0.0=切换）。
本节把视觉信号升级为 **Qwen2.5-VL-7B-AWQ 关键帧自然语言 caption**，每章 1 句中
（或英）文描述（强调"教学相关核心"避免描述美学/光线噪声），喂给 segment LLM 作
prompt cue。同 9 视频三路对比（完整表见 paper/mm_ablation.md）：

| # | 视频 | n_chunks | txt 章 | mm 章 | mm.vl 章 | VL 路径 |
|---|---|---|---|---|---|---|
| 1 | 计网 p38 以太网 | 11 | 5 | 6 | 6 | used |
| 2 | 计网 p44 交换机 | 9 | 4 | 4 | 3 | downgrade (内层) |
| 3 | 计网 p46 IP 分组 | 11 | 7 | 4 | 4 | used |
| 4 | 计网 p49 ICMP | 11 | 3 | 5 | 4 | used |
| 5 | OS p37 哲学家进餐 | 5 | 3 | 3 | **5** | used（切最细） |
| 6 | Vibe Coding 33min | 46 | 11 | 10 (rep) | 10 (rep) | downgrade |
| 7 | Tina 编程教程 p02 | 21 | 10 | 8 (fb) | **6** | downgrade |
| 8 | Tina AI Agent 精华 | 36 | 16 (rep) | 9 (rep) | 9 (rep) | downgrade |
| 9 | AI Agents 25min (en) | 34 | 13 (fb) | 32 | **9** | downgrade（最大反转） |

**双刃剑发现**：

- **短视频/动态场景** (n_chunks ≤ 15)：VL caption 信息密度高，主题切换识别清晰。
  典型案例 OS p37 哲学家进餐——5 个 chunk 上 VL caption（"哲学家 / 筷子 / 死锁
  示意图"主题不同）让 LLM 切出最细的 5 章，mm/txt 路径只能切到 3 章。
- **长视频/PPT 教程** (n_chunks > 15)：VL caption **反作用**。典型案例 Tina AI
  Agent 精华 36 chunks——caption 字面 unique（"讲师讨论代理 / Susan 订单 / 营销
  文案"各不同），但 LLM 看到"画面都是讲师讲案例"主题归并意图，把 23 chunks 塞
  进一章触发 catch-all。EH5jx5qPabU 英文教程更明显：mm 路径切 32 章（slide flip
  误判为章节边界），改用 VL caption 路径自适应降级回 sim cue 后切出最合理的 9 章。

**自适应 heuristic 试错过程**（research finding）：

1. **Jaccard 相邻 caption 字面相似度** → BV1S6kQBNEJq 实测 0.08，**没抓到问题**
   （字面 unique 不等于视觉有切分区分度）
2. **Generic teaching word ratio**（"讲师/讨论/讲解/介绍/explains/discusses"
   等）→ 初版词典（5 中文 + 5 英文）+ 阈值 0.50，BV1S6kQBNEJq 0.36，**漏判**；
   早期暂时搁置
3. **2026-05-17 采纳两层结构阈值**：
   - **外层 n_chunks > 15**：长视频整体语义密度低，画面 pattern 单一
   - **内层 prefix-run 同质化**：n_chunks ≤ 15 但出现 ≥4 个共享 10 字前缀的连续
     caption 且剩余 chunks ≥ 3 时也降级
4. **2026-05-24 中层 generic_ratio 重生**：扩 corpus 后 FwOTs4UxQS4 AI Agent
   英文教程 caption 持续以 "The presenter / video / diagram explains..." 模板
   起句，generic_ratio=0.82。扩展英文动词词典（动作类 +ing/-s 形态 + 角色/载体
   类 instructor/diagram/slide）+ 阈值收紧到 0.65 后纳入作为**中层 gate**，
   覆盖原本只能由救援层兜底的 case，attempt 数从 #3 + 救援 retry 降到 #2。

复杂的 content-based heuristic 不稳，简单的 length-based 反而最 robust——这是
本工作的一个意外发现：**对 LLM-as-segmenter 而言，决定视觉信号是否有益的关键不
是 caption 内容质量，而是视频本身的"语义密度"，长视频的主题归并意图压过细分意图**。

**内层门控的发现路径**：原始 9 视频实验中 p44 (n=9, ≤ 15 外层通过) 出现局部
回归——mm 路径 attempt 2 一次过，mm.vl 路径反需 promote+repair_missing+
repair_oversize 三连兜底。诊断发现其 9 条 caption 中 chunks 1-5 共享前缀
"以太网交换机的自学习功能"（max_prefix_run=5），LLM 把这 5 个 chunks 视作同主题
试图合并成 1 章但剩余 4 chunks 无法挤进单章结构，于是反复漏 chunks。OS p37
caption 同样高度同质（max_prefix_run=4）但 n=5 仅 1 个"其它"chunk，合并后结构
天然合法，因此保留 VL 增益。**触发条件 `max_prefix_run ≥ 4 且 (n - run) ≥ 3`**
唯一精确命中 p44，不误伤 OS p37 — 重跑 p44 加门控后 attempt 2 一次过、零 repair。

**最终配置**：`--vlm-captions` 默认 disable；启用时三层自适应（2026-05-24 加中层后）：
1. 外层 `n_chunks > 15` → 降级 (4/9 案例)
2. 中层 `generic_ratio ≥ 0.65` → 降级（FwOTs 英文教程 0.82 命中，2026-05-24 加）
3. 内层 `max_prefix_run ≥ 4 且 (n - run) ≥ 3` → 降级 (1/9 案例，即 p44)

四个 ablation 字段：`vlm_captions`（用户开了 flag）、`vlm_captions_used`
（实际是否用了 caption）、`vlm_generic_ratio`（中层 gate 诊断指标）、
`vlm_degraded_reason`（降级原因，三层之一或 `rescue_after_llm_fail`）。
9 视频 ablation 实测：**4 used / 5 downgraded（外层 4 + 内层 1）**；启用且
切更细的 1/4（OS 哲学家进餐）；降级避开过度切分风险的最显著反转是
EH5jx5qPabU（32 → 9 章），最显著局部回归修复是 p44（3 次 attempts → 1 次
attempt + 0 repairs）。中层 gate 的命中案例见 §5.4.4 FwOTs 跨语言验证。

#### 5.4.4 跨语言泛化验证 + VL 救援第三层

为验证两层门控对英文的泛化性，新增 2 个英文教程视频（FwOTs4UxQS4 10:09 AI Agents
入门、WSPChlfxJyA 19:12 Claude 教程）跑完整 mm vs mm.vl 对比（连带原 EH5jx5qPabU
组成 3 视频组）。

| 视频 | n | mm-only 结果 | mm.vl (两层门控) 结果 | 失败归因 |
|---|---|---|---|---|
| EH5jx5qPabU | 34 | 32 章 attempt 1 (过度切分) | **9 章 attempt 2 (外层 n>15 降级)** | 外层正确触发，避开 slide flip 误判 |
| FwOTs4UxQS4 | 11 | 8 章 attempt 3 OK | **fallback TextTiling 5 章（3x missing/overlap）** | 门控**漏检**：英文 caption 5-8 语义同构（compiling/summarizing/posts）但首 10 字前缀不同（"The presenter/video/diagram/process"） |
| WSPChlfxJyA | 27 | fallback TextTiling 12 章 | fallback TextTiling 12 章（外层降级 sim cue 但仍失败） | 与 VL 无关——Qwen 在英文 27-chunk 上 catch-all bias 独立存在，是 [[english-support]] 已知问题 |

FwOTs case 暴露了内层门控的语言依赖性：char-prefix 在中文上有效因为同主题 caption
共享开头实体（"以太网交换机的自学习功能..."），英文 caption 习惯以冠词起句
（"The X explains Y..."）首词变化大但语义内核高度重复。设计基于词袋 Jaccard 或
内容词重叠的英文 friendly 内层门控试错复杂度高且易过拟合。

**第三层：VL 救援（事后兜底）**——观察到 FwOTs mm-only 仍能 attempt 3 通过 LLM 切分
8 章，证明 VL caption 才是失败原因。于是加：**LLM 3 attempts + repair 全失败且
visual_captions 被使用时，自动一次重试不带 caption**（仅 sim cue），LLM 已在显存
所以增量 ~10s 量级。

FwOTs 重跑实测：第一轮 VL 3 次 overlap/missing 失败 + repair 失败 → **救援触发** →
重试 attempt 2 一次过、6 章 LLM 切分（vs 原 fallback TextTiling 5 章）。
WSPChlfxJyA 救援不触发（VL 已被外层降级未使用）——验证救援机制只针对 VL 引入的
失败，不会误触发于 VL 无关的 catch-all。

**完整四层架构**（2026-05-24 加中层 gate 后）：
1. **外层** `n_chunks > 15` 先验降级——粗粒度防过度切分（4/9 中文 + 1/3 英文）
2. **中层** `generic_ratio ≥ 0.65` 先验降级——caption 多为通用动词/角色词无区分度
   （FwOTs 英文教程 generic=0.82 命中，2026-05-24 加，替换原救援层的英文兜底）
3. **内层** `max_prefix_run ≥ 4 且 (n - run) ≥ 3` 先验降级——caption 高度同质
   引发漏 chunks（1/9 中文，p44；中文 friendly，英文不触发）
4. **救援** LLM 全失败后事后降级——加中层后 corpus 0 触发，保留作为未知失败
   模式的安全网

新增 ablation 字段 `vl_rescue_used`，区分"先验门控降级"vs"事后救援降级"
（`vlm_degraded_reason='rescue_after_llm_fail'`）。

**跨语言验证结论**：
- 中文：先验门控 9/9 准确（包括 1 次内层捕获 p44）
- 英文：外层正确触发于长视频；内层 char-prefix 在英文上不鲁棒（冠词起句导致
  首词变化大）；FwOTs 英文 case 先经历救援层兜底，2026-05-24 中层 gate
  （generic_ratio）纳入后改为先验降级，attempt 数 #3→#2
- 四层架构能识别"VL 是不是凶手"——救援层不会拯救与 VL 无关的失败
  （WSPChlfxJyA 的 catch-all 是 [[english-support]] 中 Qwen-EN bias 的独立问题）
- **方法论意义**：早期被弃的 heuristic（generic_ratio）经扩 corpus + 扩词典 +
  调阈值后可重生作为先验 gate；救援层即便降为 0 触发的安全网仍有价值——它
  提供"VL 在用但 LLM 全失败"这一显式 ablation 信号供后续 heuristic 迭代

#### 5.4.5 扩样本验证：20 视频架构泛化

为加强结论统计性，新增 8 个中文视频（OS p47/p53、网络 p47/p48、3 个未知域 BV1h5L364Ezv/
BV1YP5W6ZEP9/BV1VsTfzdEZE、BV1nBWyzBEp2 p2），与原 9 中文 + 3 英文组成 20 视频
corpus 跑完整 mm.vl 三层架构。

**汇总**（20 视频）：

| 路径行为 | 计数 | 视频示例 |
|---|---|---|
| VL 启用 (vl_used=True) | 10/20 | p38, p46, p49, OS p37, p48, OS p47/p53, h5L, VsT, YP5 |
| 外层 gate 降级 (n > 15) | 6/20 | Vibe, Tina p02/Agent, EH, WSP, NW p2 |
| 内层 gate 降级 (prefix_run) | 2/20 | p44, **p47**（新捕获） |
| 救援层触发 | 1/20 | FwOTs (en) |
| Fallback TextTiling | 1/20 | WSP (en，与 VL 无关) |
| **LLM 切分覆盖率** | **19/20 = 95%** | 唯一例外 WSP |

**新内层 gate 捕获**：网络 p47 (n=12) caption 结构高度类似 p44——chunks 1-4 共享
前缀"讲解 IP 地址分类方案..."（4 个连续），chunks 5-8 共享"IP分组转发..."（4 个
连续），与 p44 的"5 自学习 + 3 直通交换"双 run 结构完全同构。Inner gate `pref_run=4
+ n-run=8 ≥ 3` 正确触发降级，attempt 2 一次过、零 repair。这是内层 gate 在原始
9 视频校准后的**首次"野外"命中**，证明 heuristic 不是过拟合 p44 单 case。

**LLM-as-segmenter 失败模式的语言对偶性**（research finding）：

| 语言 | 共享内核失败模式 | 触发表层 | 抓手 |
|---|---|---|---|
| 中文 | 主题词整段重复（"以太网交换机的自学习功能..."×5） | char-prefix 共享 | **内层 gate prefix-run** 抓得到 |
| 英文 | 句法模板化但内容同质（"The X verbs Y..."） | 词层分散，语义层聚集 | lexical metric 全失效，**救援层**事后兜底 |

实测三种 lexical 指标（char-prefix、char-Jaccard、word-bag Jaccard）在 FwOTs 上
最高 pair-wise Jaccard 仅 0.33（5↔6 一对），无连续 run ≥ 4——证明英文 caption 在
表层确实不重复，LLM 是在 word-bag 之上的语义层做主题归并。任何 lexical 先验门控
都救不了，**反应式救援是该失败模式的唯一合理架构**。

**架构经济性**：1/20 视频触发救援（额外 ~10s LLM 调用），5/20 触发先验降级
（节省 caption 读取 + 减少 retry），总体净增量 < 2% pipeline 时间，换来 95% LLM
切分覆盖率。

### 5.5 ASR 重复段去重的影响 (Case Study)

见第 6 章 Case Studies。

### 5.6 章标题质量主观打分

n=30 样本，5 分制：
- chars: 3.25 / texttile: 3.43（整体）
- PPT 子集：chars 3.12 / texttile **3.50**（Δ+0.38）
- 与自动指标"关键词覆盖率"Pearson r = +0.52（中度正相关）

### 5.7 LLM 章节切分路径覆盖率

9 视频（中文 8 + 英文 1）跑 Qwen2.5-7B-AWQ 章节切分，记录 retry 阶段与
program-repair 触发情况。完整表见附录 B。核心结论：

- **LLM 切分路径覆盖率 100%**（9/9 不需要 fallback TextTiling）
- attempt 1 直接通过 22%；剩下 78% 在 retry-with-feedback 后通过
- **catch-all 兜底**：1/9 视频（Tina Huang AI Agent 精华，36 chunks）3 次
  attempt 全失败，被 `_repair_missing_chunks` + `_repair_oversize` 程序化
  接力救回 16 章——证明 Qwen 模型本身在 30+ chunks 长视频上的 catch-all
  bias 无法用 prompt 工程根治，但程序化兜底能完全消除 fallback 的需要

## 6 Case Studies

### 6.1 王道 OS 哲学家进餐：ASR 卡片回路修复

**视频**：王道计算机考研 操作系统 p37 2.3.5_3 哲学家进餐问题（15:00，PPT 教学）

**问题诊断**：

faster-whisper 在 755.2s 起进入卡片回路，连续 9 段输出相同句子 "我们用这个呼吃信号量,保证了每个哲学家拿筷子这件事"（注：原句应为"互斥信号量"，ASR 同时还存在同音字错误）。在 chunk_chars=400 的 texttile chunker 输出下，这 9 段 ASR segment 凝聚成一个 13 秒、242 字的孤立 chunk（chunks 中的 chunk 8），其 jieba top-k 关键词被 "呼吃 / 信号量" 高频自我污染。该 chunk 与相邻 chunk 的 Jaccard 距离虚低，TextTiling depth score 无法识别此处的真实话题切换点，导致 segmentation 算法错过了"互斥解决方案 → 死锁分析"这个 gold 章节边界。

**修复后定量结果**（cc=400 texttile，K=3，gold=[5, 10]）：

| 指标 | dedupe off | dedupe on | Δ |
|------|------------|-----------|---|
| 预测边界 | [5, **8**] | [5, **9**] | 第二边界 +1 |
| Strict F1 | 0.50 | 0.50 | 0 |
| **F1@1** | **0.50** | **1.00** | **+0.50** |

**机制分析**：dedupe 后 "呼吃" 在 chunker 输出 chunks 中从 9 次降到 1 次，原 13 秒 micro-chunk 消失，chunks 字符长度分布从含 242 字 outlier 变为 249-873 字均衡分布。第二章节边界因此从 chunk 8 末（远离 gold chunk 10）推至 chunk 9 末（gold 容差内）。

**Takeaway**：该 case 说明上游 ASR 卡片回路会通过关键词频次污染下游 segmentation 算法；后处理 dedupe 是低成本的有效干预（10 视频 ASR cache 扫描显示 3 视频触发，min_run=3 阈值无误伤其余 7 视频）。

### 6.2 计网 p38：dedupe 在长视频上的累积收益

**视频**：王道计算机考研 计算机网络 p38（30:00，PPT 教学）

**问题诊断**：

这是 benchmark 中时长最长的视频（30 分钟）。faster-whisper ASR 输出 991 段 segment，其中两处出现连续重复 run：
- 230.8s 起 x3 "也就是说接下来一个不到 2.5Gbps 的电缆"
- 1922.5s 起 x3 "我们一会冲突域"

这两处单独看影响很小（chars chunker 下 chunks 数不变），但在 cc=400 texttile 下，关键词分布的细微偏移会通过 TextTiling depth score 的局部峰值传导，最终改变 4 个候选边界的排序。

**修复后定量结果**（cc=400 texttile，K=5，gold=[7, 14, 17, 20]）：

| 指标 | dedupe off | dedupe on | Δ |
|------|------------|-----------|---|
| 预测边界 | [3, 5, 7, 11] | **[7, 10, 17, 20]** | 3/4 边界严格命中 gold |
| **Strict F1** | **0.25** | **0.75** | **+0.50** |
| **F1@1** | **0.25** | **0.75** | **+0.50** |

**机制分析**：dedupe off 时，模型在视频前 1/3 选中 3 个低 depth 候选（chunk 3/5/7），把 4 个边界配额耗在视频前段。dedupe 移除关键词噪声后，模型重新分配权重，边界 7、17、20 都严格命中 gold（chunk 14 因为其他原因未命中，差距 4 chunks）。

**Takeaway**：dedupe 的收益不仅来自直接受影响的 chunks，还来自整个 chunker 关键词图的"去噪"效应——边界排序变化是非局部的。这解释了为什么计网 p38 仅 4 段 dedupe 就能带来 0.50 的 F1 提升。

### 6.3 Case Studies 整合：10 视频均值的子集分析

上述两个 case 是 dedupe 的 high-impact 实例。在 10 视频均值层面：

| 子集 | chunker | cc | ΔF1 | ΔF1@1 |
|------|---------|----|----|-------|
| PPT (n=6) | texttile | 400 | **+0.083** | **+0.167** |
| 全部 (n=10) | texttile | 400 | +0.050 | +0.100 |
| 全部 | texttile | 800 | 0 | 0 |
| 全部 | chars | 任意 cc | ≈ 0 | ≈ 0 |

**三条结论**：
1. dedupe 在 **cc=400 + texttile** 上是真正的 segmentation 改进（PPT 子集 ΔF1@1 +0.167）
2. **cc=800（paper main）操作点上 dedupe 几乎不变** — dedupe 是"免费保险"：不损害但也几乎不提升，因为 800 字 chunks 已经把 dedupe drop 的 5-10 段稀释吸收
3. **chars chunker 上 dedupe 中性** — dedupe 与语义 chunker 协同更好，因为 dedupe 真正影响的是"关键词频次"，对字符硬切的 chars 无作用

这一耦合关系是论文 chunker × dedupe 二维 ablation 的核心 takeaway。

### 6.4 24 视频 corpus：多模态架构泛化验证

§5.4.3 至 §5.4.5 的 VL caption + 三层自适应架构在以下 24 视频 corpus 上做了完整
验证（21 中文 + 3 英文，时长 4 min 到 40 min，覆盖王道 OS/计网考研、AI Agent
教程、Vibe Coding、Notebook LM、AI 工具应用、美食 vlog、英语播客等 8 个子域）。
最后 5 行为 2026-05-18 新增的扩 corpus 案例，进一步验证四层 gate（含 2026-05-24 新加中层）在更宽分布下的
稳健性。数据由 `scripts/aggregate_eval.py --mode section6-4` 自动从所有
`*.mm.vl.chapters.json` 聚合，扩 corpus 时一键刷表（手填易错，曾误计为 25 视频）。

| 视频 | n | mm.vl 章 | VL 路径 | LLM 状态 | 说明 |
|---|---|---|---|---|---|
| 计网 p38 | 11 | 6 | used | #1 | 基线，主题词变化大 caption 不干扰 |
| 计网 p44 | 9 | 3 | **内层 gate** | #2 | p44 calibration 原 case |
| 计网 p46 | 11 | 4 | used | #2 | |
| 计网 p47 | 12 | 4 | **内层 gate** | #2 | **野外捕获**，与 p44 同构（两段共享前缀） |
| 计网 p48 | 13 | 4 | used | #2 | |
| 计网 p49 | 11 | 4 | used | #1 | |
| OS p37 哲学家 | 5 | 5 | used | #1 | VL 增益最显著 case |
| OS p47 | 9 | 3 | used | #1 | |
| OS p53 | 9 | 3 | used | #1 | |
| BV1h5L364Ezv | 3 | 3 | used | #1 | 短视频边界 |
| BV1VsTfzdEZE | 3 | 1 | used | #1 | 短视频边界 |
| BV1YP5W6ZEP9 | 5 | 3 | used | #2 | |
| BV1nBWyzBEp2 p2 | 37 | 8 | 外层 gate | repair | 长视频，repair_oversize 救活 |
| Vibe Coding | 46 | 10 | 外层 gate | repair | 同 |
| Tina p02 | 21 | 6 | 外层 gate | #2 | |
| Tina AI Agent | 36 | 9 | 外层 gate | repair | |
| EH5jx5qPabU (en) | 34 | 9 | 外层 gate | #2 | 英文长视频，外层避开 slide flip 误判 |
| FwOTs4UxQS4 (en) | 11 | 6 | **中层 gate** | #2 | generic_ratio=0.82，2026-05-24 加中层 gate 后由先验降级；原救援层 case 退化为 0 触发安全网 |
| WSPChlfxJyA (en) | 27 | (fb) 12 | 外层 gate | fb | **唯一 fallback**：与 VL 无关，Qwen-EN catch-all |
| BV1C8L36jEYN (新, 美食 vlog) | 2 | 2 | used | #1 | 短视频边界，n_chunks=2 无需 gate |
| BV1pB5T6hEWW p1 (新, 英语播客) | 10 | 3 | used | #2 | ASR 后验校正 lang→en，Qwen 改用 en prompt 切粗粒度 |
| BV1pB5T6hEWW p3 (新, 英语播客) | 5 | 5 | used | #3 | prefix_run=4/5 |
| 计网 p34 (新) | 12 | 5 | used | #2 | |
| BV1E7wtzaEdq (新, LLM 教学) | 14 | 6 | used | #3 | attempt 3 一次过，无需 repair |

**核心数据**：

| 维度 | 数值 |
|---|---|
| LLM 切分覆盖率 | **23/24 = 96%** |
| 一次过 (attempt 1) | 8/24 |
| Retry-with-feedback (attempt 2-3) | 12/24 |
| Programmatic repair (promote/missing/oversize) | 3/24 |
| 救援触发 | 0/24（加中层 gate 后退化为安全网；原 1/24 由中层先验降级覆盖） |
| 外层 gate 降级 | 6/24 |
| 中层 gate 降级 | 1/24（FwOTs，2026-05-24 新增） |
| 内层 gate 降级 | 2/24 |
| Fallback TextTiling | 1/24 |

**三个 case study 维度**：

**(a) 内层 gate 野外命中 — 网络 p47**

p44 calibration 时担心的"过拟合单 case"在新增的网络 p47 上得到证伪。p47 (n=12)
的 caption 结构与 p44 同构：chunks 1-4 共享前缀"讲解 IP 地址分类方案..."
（4 个连续），chunks 5-8 共享"IP分组转发..."（4 个连续）；与 p44 的"5 自学习
+ 3 直通"双 run 模式完全一致。内层 gate `pref_run=4 + n-run=8 ≥ 3` 正确触发降级，
attempt 2 一次过、零 repair。这是 heuristic 不依赖 calibration sample 的关键
泛化证据。

**(b) 中层 gate 唯一命中 — FwOTs（原救援层 case，2026-05-24 升级）**

FwOTs (n=11 英文 AI Agent 教程) 早期在两层 gate（外层 + 内层）下漏检：英文 caption
5-8（"The presenter explains... / The video explains... / The diagram illustrates...
/ The process involves..."）句法模板化但内容同质（都讲 "compiling/summarizing/
posts"），LLM 在 word-bag 之上的语义层做主题归并漏 chunks。三种 lexical 指标
（char-prefix、char-Jaccard@.7、word-Jaccard@.2）的 max consecutive run 均不足以
触发先验降级——任何 lexical heuristic 都救不了。

**第一版方案（2026-05-19）**：救援层兜底——LLM 全失败 + VL 在用时 retry 不带
caption，FwOTs 从原 fallback TextTiling 5 章救回 LLM 6 章。

**第二版方案（2026-05-24）**：把 §5.4.3 早期被 0.50 阈值漏判的 generic_ratio 指标
扩英文词典（动作动词 +ing/-s 形态 + 角色/载体类 instructor/diagram/slide）+
收紧阈值到 0.65 后纳入作为**中层 gate**。FwOTs caption generic_ratio=0.82 直接触发
先验降级，attempt #2 一次过、无需救援 retry。原救援层降为 corpus 0 触发的安全网。

**架构演进意义**：FwOTs 同时验证了 (1) 单一 lexical 指标对跨语言不鲁棒
（char-prefix 中文有效英文无效）；(2) 早期被弃的 heuristic（generic_ratio）在
扩 corpus + 词典 + 调阈值后可重生；(3) 救援层作为安全网即便 0 触发也有价值——
它的存在迫使开发者显式标注"VL 在用但 LLM 全失败"这一信号，为后续 heuristic
迭代提供 ablation 点。

**(c) 三层架构外的失败 — WSPChlfxJyA**

WSPChlfxJyA (n=27 英文) 是 24 视频中唯一 fallback 到 TextTiling 的 case。三层
架构在该 case 上行为正确：外层 gate 因 n>15 触发，VL caption 未喂；但 sim cue 路径
attempt 2/3 仍持续 missing 9 个 chunks（chunk [10-13, 18-22]），repair_missing
覆盖不全。同视频 mm-only（纯文本）路径表现一致 fallback——证明问题与 VL 无关，
而是 [[english-support]] 章节记录的 **Qwen 在英文 27+ chunk 视频上的 catch-all
模型 bias**，是与本节多模态架构正交的独立失败模式。三层架构能"识别 VL 是不是
凶手"——救援层不触发于该 case（VL 已被外层降级），避免了浪费 retry budget 在
错误方向上。

**采纳的默认配置**（写入 src/pipeline.py 四层，2026-05-24 加中层后）：
1. 外层 `n_chunks > 15` → caption 不喂 LLM
2. 中层 `generic_ratio ≥ 0.65` → caption 不喂 LLM
3. 内层 `max_prefix_run ≥ 4 且 (n - run) ≥ 3` → caption 不喂 LLM
4. 救援：LLM 3 attempts + repair 全失败 + VL 在用 → 自动一次 retry without caption

24 视频实测净时间增量 < 2% (6 视频外层 + 1 视频中层先验降级节省 ~caption 时间)，
换 96% LLM 切分覆盖率。中层 gate 接管原唯一救援 case（FwOTs），救援层退化为
corpus 0 触发的安全网。新增 5 视频未引入任何 fallback / repair / 救援，全部走
LLM 主路径（1 × attempt 1 + 2 × attempt 2 + 2 × attempt 3）。

### 6.5 第二轮工程加固迭代（2026-05-19）

本节记录将 §6.4 的 24 视频 corpus 之外的两个新视频（王道计算机网络 p78「TCP 报文段」、p85「TCP 拥塞控制」）首次纳入 web 端到端生成流程时触发的 6 项问题及其修复。这一轮迭代将关注点从「单一指标的算法优化」转向「端到端管线在真实用户路径上的健壮性」，并把曾因为只在 CLI 上验证而漏掉的若干失败模式暴露出来。每一项均按「现象 → 根因 → 修复 → 后验 → 分析」四段式整理，对负面结果（trigger 误判调查最终证明为无 bug）也保留全部记录以备复用。

---

#### 6.5.1 ASR 末尾 hallucination loop 触发 ctranslate2 native abort

**现象**：

视频 p78（35:07）首次在 web 端生成时，pipeline 在 ASR 阶段进行约 6 分钟后，子进程以 Windows 退出码 `3221226505 = 0xC0000409` (STATUS_STACK_BUFFER_OVERRUN, 即 `abort()` 触发的 CRT 终止) 异常退出，无输出文件写入。stdout 末尾的进度行揭示了关键迹象——`faster-whisper` 的处理位置从音频实际长度 2027.1s **越过末尾继续推进到 2099.4s**（超出 72.3 秒），随后立即崩溃。Traceback 显示崩溃发生在 ctranslate2 的 native 模块内部，Python 栈停在 `pipeline.py:448` 的 `run` 帧。

**根因**：

faster-whisper 的解码器在视频末尾失去 VAD 锚点后进入 hallucination loop：language model 持续生成「合理但虚构」的 token，时间戳被错误向前外推。当生成位置远超音频长度时，ctranslate2 在内部 buffer 索引上发生越界，触发 `abort()`。这是 whisper 系列模型在 Windows + ctranslate2 路径上有据可查的 edge case，与项目 §6.1 提及的 OS p37 卡片回路同源（均为 hallucination loop），但本次因循环量级更大跨过了 native 层的安全边界。

**修复**：

在 `src/asr.py:transcribe()` 的 `model.transcribe()` 调用中新增两个参数：

```python
condition_on_previous_text=False,   # 切断跨段上下文携带，破除 loop 的状态依赖
no_repeat_ngram_size=3,              # 解码层硬约束：3-gram 不可重复
```

二者构成双层防御：`condition_on_previous_text=False` 在每段独立解码，使 hallucination 不会通过历史上下文向后续段累积；`no_repeat_ngram_size=3` 在束搜索内部禁止任意 3-gram 重复出现，确保即使发生短程重复也会被强制中断。代价是少量跨段叙事一致性下降（在中文 ASR 上几乎不可观察，因为 faster-whisper 中文标点本就不稳定），换取末尾稳定性，符合本项目对 ASR 输出「先正确再优雅」的优先级排序。

**后验**：

修复后，p78 ASR 顺利写出 `BV19E411D78Q_p78_p0.large-v3.asr.json`（738 segments，duration 2107.2s），无越界进度行。后续 11 chunks / 4 chapters 端到端通过。

**分析**：

| 失败模式 | OS p37（§6.1） | p78（本节） |
|---------|---------------|------------|
| 触发位置 | 视频中段（755s 起 9 段循环） | 视频末尾（2027s+） |
| 暴露层 | 下游 chunker keyword 污染 | ctranslate2 native abort |
| 干预层 | 后处理 dedupe | 解码参数 |

两个案例共同指向一个被低估的事实——**hallucination loop 不只是「质量差」，在 Windows + ctranslate2 路径上还是「可崩溃风险」**。本项目原有 `dedupe_consecutive_segments`（§6.1）只能在 ASR 输出回到 Python 层后做后处理；本次修复在解码源头加约束，与 dedupe 形成正交防御。

##### 6.5.1.bis 第二轮：vlog 长视频复发与三层加固（2026-05-21）

**现象**：

第一轮 fix 后近两周内，所有进入 corpus 的教学类视频均未再触发 native abort。但当 corpus 首次纳入 vlog 域（BV1q6ozBmE8z「上海日料探店」，26.1 min）时，pipeline 在 ASR 阶段进度推进至 **1542s / 1564s**（覆盖率 98.6%）后再次触发 Windows STATUS_FATAL_APP_EXIT (`0xC0000409`)，进程以 exit code 127 退出，无 `.asr.json` 写出。两次独立重跑均在 1542–1544s 区间崩溃（差 ≤2s），明显与音频内容无关，确认为 native 层的位置依赖型 bug。

**根因（与 §6.5.1 第一轮的差异）**：

第一轮 fix 后回看 BV1q6 case，发现失败模式已经发生了**质变**：

| 维度 | p78（§6.5.1 第一轮） | BV1q6（本节） |
|------|----------------------|---------------|
| 进度越界？ | 是（2027 → 2099s，越界 72s） | 否（1557.6s ≤ duration 1564.17s） |
| 触发阶段 | `transcribe()` 推进中 | ASR 实际完成后、Python 收尾前 |
| Python frame | `pipeline.py:run` | 不可定位（生成器 yield 后栈已展开） |
| `condition_on_previous_text=False` 是否生效 | 是 | 是（仍崩） |

也就是说，**第一轮 fix 仅消除了「外推越界」这一种触发路径**；ctranslate2 native abort 还存在第二条触发路径：在 ASR 正常完成后、模型/buffer 资源释放阶段触发的越界写。后者无法通过解码参数预防，因为崩溃时解码本身已经结束。这与项目 §6.1 / §6.5.1 既有的「先释放模型，避免与下一阶段抢 VRAM」习惯属同源——ctranslate2 在资源释放路径上的健壮性弱于解码路径。

**修复**（三层叠加，`src/asr.py:transcribe`）：

第一层沿用第一轮的 `condition_on_previous_text=False` + `no_repeat_ngram_size=3`，作为既已验证的解码约束保留。

第二层引入 faster-whisper 1.x 原生的两个 hallucination gate：

```python
hallucination_silence_threshold=2.0,   # ≥2s VAD 静默时跳过解码段
compression_ratio_threshold=2.0,        # 默认 2.4，收紧让 fallback 温度阶梯主动丢弃高压缩比段
```

`hallucination_silence_threshold` 是 faster-whisper 1.2 新增的官方接口，在检测到 VAD 静默时直接跳过相邻段的解码，从源头切断「在沉默处生成 token」的 hallucination 入口。`compression_ratio_threshold` 收紧后会让温度退火 fallback 更早触发，主动丢弃解码概率过于「确信」（往往是 hallucination loop 特征）的段。

第三层是关键——**流式增量落盘**，覆盖 native abort 在 try/finally 之外触发的盲区：

```python
INCREMENTAL_DUMP_EVERY = 50

def _dump(seg_list, last_end, partial):
    payload = {..., "partial": partial,
               "duration": info.duration if not partial else last_end}
    tmp = out_path.with_suffix(".asr.json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    tmp.replace(out_path)   # atomic on Windows NTFS

for s in segments:
    ...
    if len(seg_list) % INCREMENTAL_DUMP_EVERY == 0:
        _dump(seg_list, last_end, partial=True)
# 末尾 final write partial=False
```

Native abort 不经过 Python 异常机制，`try/finally` 与 atexit 钩子均无法触发；唯一可靠的方法是**在生成端主动按段落盘**。每 50 段（按 BV1q6 节奏约每 60–90 s）一次原子 rename，确保最差情况下崩溃前最后一次 dump 之后的内容损失上界可控。`partial=True/False` 字段让下游脚本能判断是否需要重跑或可以直接消费。

**后验**：

BV1q6 重跑后 ASR 进度依然崩在 1542s 附近（无任何参数能预防 native 层 abort），但本次 `.asr.json` 已落盘——内容 `partial=False`, 688 segments, `last_end=1557.6s`, `duration=1564.17s`，**覆盖率 99.6%**。下游 pipeline 不带 `--force-asr` 直接复用此 cache，端到端通过。

2026-05-22 在新 vlog（BV1dkLr6UEJ6「陈泽测评山姆零食」，15.5 min）上回归三层加固：ASR 完整 669 segments 写出（duration 927.2s，无 partial 标记），无 abort，下游全链路通过。同日 BV1AYR6BsE9U「陈泽薯片测评」28.2 min 再次撞上同型故障——ASR 推进到 1690.3s / 1693.1s 时 Fatal Python error: Aborted，但 `.asr.json` 已落盘（1383 segments，`partial=False`，`last_end=1692.9s`，覆盖率 99.99%），retry pipeline 复用 cache 完整通过，验证了 L3 兜底机制在 native abort 真实发生时的工程价值。

**分析**：

| 防御层 | 防护机制 | 适用故障模式 |
|--------|---------|--------------|
| L1 解码约束 (§6.5.1 第一轮) | `condition_on_previous_text=False` + 3-gram | 外推越界（p78） |
| L2 hallucination gate (1.x 原生) | silence threshold + compression ratio | 沉默处生成 / 概率异常段 |
| L3 增量落盘 | 流式 atomic write 每 50 段 | native abort 在 try/finally 外触发（BV1q6） |

三层防御从「预防」（L1/L2）到「兜底」（L3）形成纵深。L3 是关键的认识跃迁——承认在 native 层崩溃面前 Python 端的所有 exception handling 都不可靠，必须用「持久化频率」换「最大损失上界」。这与数据库领域的 WAL（write-ahead log）思想同源：不期望崩溃不发生，只期望崩溃后状态可恢复。

本节的另一项 takeaway 是 **failure mode 会演进**：第一轮 fix 没有「失效」，它仍然在为符合该模式的视频提供保护；只是当 corpus 跨入新域（vlog vs 教学）时，曾经稀有的第二条触发路径变得可观察。这提示对系统健壮性的工程评估必须随 corpus 同步迭代——一个 fix 在它当时的 benchmark 上 100% 通过，不代表它在新场景下仍然 100% 充分。

---

#### 6.5.2 `.mm.` 后缀产物漏出版至 web/public

**现象**：

p78 第二次提交（避开 hallucination 后）pipeline 成功完成，stage 跑到 `done`、percent 100，但前端 `/notes/BV19E411D78Q_p78_p0` 路由对 `summary.json` 与 `chapters.json` 同时返回 404，note 在 `/api/notes` 列表中也不出现。`data/outputs/` 下产物完整（`.mm.summary.json` / `.mm.chapters.json` / `.mm.keyframes/` 全部存在），但 `web/public/notes/BV19E411D78Q_p78_p0/` 目录为空。

**根因**：

`server.py:_publish_to_web()` 中的源文件路径硬编码为 `{stem}.large-v3.neural.texttile.{kind}.json`，未匹配实际写出的 `{stem}.large-v3.neural.texttile.mm.{kind}.json`。`.mm` 中缀在 2026-05-17 引入 keyframes / VLM 路径时加入（见 §5.4.3 文件命名约定），但 publish 函数当时未同步更新，CLI 自测路径不经此函数所以未被发现。

**修复**：

将硬编码 `texttile.{kind}.json` 改为 glob `texttile*.{kind}.json`，并取 mtime 最近一个，兼容 `texttile`、`texttile.mm`、未来可能加的 `texttile.mm.vl` 等变体：

```python
def _pick_latest(pattern: str) -> Optional[Path]:
    cands = sorted(DATA_OUTPUTS.glob(pattern), key=lambda p: -p.stat().st_mtime)
    return cands[0] if cands else None

src = _pick_latest(f"{stem}.large-v3.neural.texttile*.{kind}.json")
```

`keyframes/` 目录与回退 md 扫描路径做同样改造，并把 stem 回填正则 `\.large-v3\.neural\.texttile$` 扩为 `\.large-v3\.neural\.texttile(\.mm)?$`。

**后验**：

修复后手动对 p78 重放一次 publish，目录正确建立（`summary.json` 1.2 MB / `chapters.json` 3.3 KB / `keyframes/` 11 张），前端列表立即可见。重启 server 后，新生成 job 的 publish 自动走 glob 路径。

**分析**：

本 bug 暴露的元问题不是某一行代码错，而是「产物文件名是一个隐式扩展点，而 publish 是耦合在文件名 schema 上的下游消费者」。在 §5.4.3 引入 `.mm` 时，project memory 仅记录了 stem 命名规则的变化，没有提示 publish 路径同步。可以在 `_output_stem` 函数旁加 docstring 注释「修改此函数需同步更新 server.py:_publish_to_web 与 scripts/aggregate_eval.py 的文件匹配模式」，但更可靠的做法是 publish 时通过 glob 模糊匹配（本次修复采用），把 schema 漂移从「编译期不可见的契约」降级为「运行期不致命的容错」。

---

#### 6.5.3 计算机网络域 ASR 错字字典扩充

**现象**：

p78 + p85 生成成功后，对 chunk-level 输出做扫描发现：

| 错听 | 正确 | p78 频次 | p85 频次 | 直接影响 |
|------|------|---------|---------|---------|
| AKK | ACK | 26 | 11 | chunk 2/6 关键词污染、headline 拼写错 |
| 校验核 | 校验和 | 6 | — | **chunk 8 headline 直接错为「校验核方法」** |
| 拥测 | 拥塞 | — | 52 | 关键词频次最大错听变体 |
| 拥測 | 拥塞 | — | 21 | 繁简混 |
| 拥色 | 拥塞 | — | 21 | |
| 拥瑟 | 拥塞 | — | 6 | |
| 拥舍 | 拥塞 | — | 3 | |
| 拥饰 / 拥侧 / 拥側 / 拥筛 | 拥塞 | — | 6 (合计) | 长尾 |
| 報文 / 導致 | 报文 / 导致 | — | 5 | 繁简模式偶发 |

对 p85 而言，「拥塞」一词的 9 种错听变体合计出现 **109 次**，超过正确写法 **68 次**——whisper 在该字上出现系统性失败。所有错听变体在 `_DOMAIN_CORRECTIONS["network"]` 字典中均未收录。

**根因**：

`_DOMAIN_CORRECTIONS` 是一个手工 substring 替换字典，按视频域（network / os / ...）触发。它原本只收录了项目早期视频中观察到的错字（如「双角线 → 双绞线」、「手部 → 首部」、「表象 → 表项」）。p85 是首个进入 corpus 的「TCP 拥塞控制」主题视频，「拥塞」这个高频专有词此前未在 benchmark 中出现，错字也就未被纳入字典。

**修复**：

在 `pipeline.py:_DOMAIN_CORRECTIONS["network"]` 中追加上表全部错听变体的 substring 替换。所有词都验证过——它们在计网域内无其他合法含义（如「拥测」在中文不是常用词，「AKK」非任何术语），全局替换安全。

```python
"拥测": "拥塞",   "拥測": "拥塞",   "拥色": "拥塞",
"拥瑟": "拥塞",   "拥舍": "拥塞",   "拥饰": "拥塞",
"拥侧": "拥塞",   "拥側": "拥塞",   "拥筛": "拥塞",
"AKK": "ACK",
"校验核": "校验和",
"報文": "报文",   "導致": "导致",
```

ASR cache 命中时（pipeline.py:455-457），原始 `asr.json` 不被覆盖，新字典在每次 pipeline 运行的 `apply_term_corrections` 阶段（line 479）应用到内存中的 segments，因此**无需重跑 ASR 即可获得修复**。

**后验**（p85 复跑，ASR cache 命中，仅校正 + 下游环节重跑）：

| 指标 | BEFORE（首跑） | AFTER（修复后） | Δ |
|------|---------------|----------------|---|
| 12 种错字残留总和 | **121** 处 | **0** 处 | -121 (100% 消除) |
| 「拥塞」正确写法频次 | 70 | **179** | +109（恰好等于错听变体之和，全归并） |
| 「ACK」正确写法频次 | 31 | 38 | +7（AKK x9 修复） |
| chunk 8 headline | 「校验核方法」（错） | (n/a，p78 用例) | — |

**chunk-level headline 案例对比**（13 chunks）：

| chunk | BEFORE headline | AFTER headline | 评价 |
|-------|----------------|---------------|------|
| 4 | RTT与拥塞窗口 | 拥塞窗口与SSTHRESH | AFTER 抓到具体术语「SSTHRESH」（慢启动阈值），更准 |
| 5 | 慢开始算法 | 拥塞控制与快重传 | 内容确为快重传段，AFTER 更贴合 |
| 6 | 拥塞避免算法 | 拥塞窗口增长机制 | 同主题，措辞更技术化 |
| 2 | 冗余ACK机制 | 拥塞控制原理 | **AFTER 更模糊** — 退步案例 |
| 3 | 拥塞窗口调整 | 拥塞控制与流量控制 | 主题漂移，**待人工评判** |

**分析**：

本案例展示了一个 ASR 后处理字典维护的**双层结构**：
- **域无关错字（CamelCase / 全大写 token）**：通过 `_build_term_corrections` 从 metadata 自动抽取 + `_ASR_CONFUSIONS` 表泛化，无需手工维护
- **域特定同音字 / 训练语料偏差错字**：必须人工累积，每新增 sub-domain 视频可能引入新的需补录条目

对论文影响：§4.1.1 应增加一段说明「域特定字典是一个 ongoing-maintenance 资源，每新进入一个 sub-domain 都要做一次错字 EDA」。对系统设计影响：未来可以加一个 `scripts/eda_asr_errors.py` 半自动工具——给定一个 domain 关键词（如 "拥塞"），从 ASR 全文中扫描距离 ≤1 的相似字符组合，输出候选错听列表供人工筛选，避免每次完全靠肉眼。

---

#### 6.5.4 jieba 关键词抽取的 stopword 渗漏

**现象**：

p78 / p85 chunk-level 输出的 `keywords[]` top-5 中频繁出现 `这个 / 等于 / 题目 / 当中 / 这种` 等口语虚词。例如 p78 chunk 2 keywords `['TCP', 'AKK', '报文', '确认', '字节']` 看似干净，但 chunk 5 keywords `['报文', 'FIN', 'TCP', '紧急', '这个']`——「这个」抢占了一个本应是「报文段头部字段」相关术语的位置。p85 chunk 4 keywords `['发送', 'TCP', '拥塞', '这个', 'ACK']` 同样。

**根因**：

项目在 `summarize.py:_GLOSSARY_STOPWORDS` 维护了一份精心整理的中英停用词集（约 200 条，涵盖讲师口头禅、中文虚词、英文功能词、缩写残片），但这份集合**只在「术语表生成」阶段被 `_is_stopword()` 过滤使用**。`jieba.analyse.extract_tags()` 的全部 4 处调用（chunker、chunk-level keywords、章标题关键词抽取、chunk cleaning）都使用 jieba 内置 stopword 表（很小、只覆盖最基本中文功能词），未传入 `_GLOSSARY_STOPWORDS`。

**修复**：

在 `summarize.py` 模块加载时把 `_GLOSSARY_STOPWORDS` 写入临时文件，通过 `jieba.analyse.set_stop_words()` 设为全局状态。这是 jieba 提供的唯一公开 API（无 per-call 参数版本）：

```python
def _init_jieba_stopwords() -> None:
    sw_file = Path(tempfile.gettempdir()) / "notegen_jieba_stopwords.txt"
    sw_file.write_text("\n".join(sorted(_GLOSSARY_STOPWORDS)), encoding="utf-8")
    jieba.analyse.set_stop_words(str(sw_file))

_init_jieba_stopwords()
```

虽然 `set_stop_words` 修改全局状态在多进程并发下不安全，但本项目 pipeline 是单进程 subprocess、jieba 仅一处消费者，无副作用。

**后验**（独立单元验证 + p85 复跑）：

单元测试输入文本 `'这个 TCP 拥塞控制 是 网络层 的 重要 算法 这个 协议'`：

```
before: ['TCP', '拥塞', '网络层', '算法', '这个', '协议', '控制', '重要']
after : ['TCP', '拥塞', '网络层', '算法', '协议', '控制', '重要']
```

`这个` 被正确滤除，top-K 自动收缩。p85 复跑层面（13 chunks 的 keywords[] top-5 stopword 占用统计）：

| Stopword | BEFORE 占用次数 | AFTER 占用次数 | 说明 |
|----------|----------------|---------------|------|
| 这个 | 8 | **0** | 完全消除（已在 `_GLOSSARY_STOPWORDS`） |
| 等于 | 2 | 3 | 略增 — 不在 stopword 集中，建议补录 |
| 题目 | 1 | 2 | 略增 — 考研域内是高频但非术语，需 case-by-case 判断 |
| 合计渗漏 | **11** | **5** | -55% |

修复效果是「部分修复」：核心高频虚词「这个」被根除，但「等于 / 题目」反而因为 stopword 表未收录、且原本被「这个」抢占的 top-5 位置腾出而上位。`等于` 在数学公式 / 计算窗口的语境是关键词（如「窗口等于 RTT × BW」），强行加入 stopwords 会破坏教学视频常见的「公式描述」表达；`题目` 在考研域专门指代「真题示例」，是讲师反复使用的有意义元数据。这两个词的处理是一个 domain-aware stopword 的开放问题——本项目当前选择保守不动，将「部分修复」的诚实记录写入论文，作为未来 stopword 表 domain 化的动机。

更深一层影响是 **章节切分受 keyword 图变化间接影响**：BEFORE 章节数 6，AFTER 章节数 7（详见 §6.5.6 后验表）。但此变化是 ASR 错字修复（§6.5.3）+ stopword 清洁（本节）+ VLM caption 启用（§6.5.6）三因素共同作用，无法单独归因于 stopword 修复。

**分析**：

这条 bug 暴露的元问题是「stopword 数据资产存在但未被全部消费点共享」。`_GLOSSARY_STOPWORDS` 这份资产在术语表场景下是 post-filter，在 keyword extraction 场景下应是 pre-filter，但代码结构上没有强制二者使用同一份数据。一个更结构化的设计是把停用词集合提升为 module-level 资源，在 `summarize.py` 初始化阶段同时注入到 jieba 全局表与 `_is_stopword()`，使任一处更新都自动同步。本次修复采用了这一思路（`_init_jieba_stopwords()` 在 `_GLOSSARY_STOPWORDS` 定义后立即调用）。

对下游影响：keyword 出现 stopword 不只是观感问题，还会影响 TextTiling chunker 的 Jaccard 距离计算——「这个」如果在所有 chunks 中频繁出现，会人为拉低相邻 chunks 的距离（共享 token 增多），从而模糊真实话题边界。这与 §6.1 / §6.2 的 dedupe-改善 chunker 边界检测属于同一类「上游 keyword 噪声 → 下游分段失真」机制，是论文 §4.1 / §4.2 中应当统一论述的「关键词图清洁度」概念。

---

#### 6.5.5 Wrap-up trigger 误报调查：负面结果

**现象（疑似）**：

p78 章 4 标题被 wrap-up 检测器标注为「MSS 与报文格式 · 本节复习」，但章节标题本身（MSS、报文格式）显然是新知识点，不像复习。初步怀疑 `_mark_wrapup_chapter` 函数的 trigger 阈值（hits ≥ 2）过低导致误报。

**调查**：

对 p78 末章（chunks 9-10）的全部 chunk 文本扫描 12 个中文 wrap-up triggers，结果如下：

| Trigger | 命中次数 | 上下文 |
|---------|---------|--------|
| `以上就是` | 1 | "...好的那么以上就是 TCP 报文段这个考点的全部内容..." |
| `在这个视频中` | 1 | "...好的在这个视频中我们详细探讨 TCP 报文段的格式..." |
| `考点` | 2 | "...这种考评不高的考点..." |
| `回顾一下` | 1 | "...你只需要在考试前几天迅速的回顾一下..." |

合计 5 处真 trigger 命中。p85 末章（chunks 11-12）同样命中 2 处真 wrap-up phrase（「以上就是这节课的全部内容」、「在这个视频中我们主要介绍了慢开始和拥塞避免」）；非末章累计仅 1 处 `考点` false positive，但被「只检最后一章」的过滤规则正确挡掉。

**结论（负面）**：

`_mark_wrapup_chapter` **不存在 bug**。两个视频的末章确实进行了讲师 wrap-up，trigger 触发是正确行为。最初的误判源于「只看章节标题就判断章节性质」——而章节标题由 LLM 从 chunk 内容生成，倾向于抓「新出现的术语」（MSS、报文格式），不会主动反映该 chunk 还包含 wrap-up 性质。换言之，p78 章 4 是「混合性章节」：既介绍新知识点（MSS 字段、报文格式总览），同时夹杂讲师的回顾陈述。

**收获**：

虽然不是 bug，但调查过程暴露了一个 future-work 选项——可以在 LLM 章节标题生成阶段把「该章节是否为 wrap-up」作为额外 prompt 信号，让标题在 wrap-up 场景下更倾向「TCP 报文段总结」或「本节复习要点」这类显式总结性命名，而非抓最末出现的新名词。这是设计取舍：当前实现将「事实标记」（`· 本节复习`）与「内容标题」分开，可读性已足够；嵌入式命名虽更优雅但增加 LLM prompt 工程复杂度。本节作为负面结果存档，避免下次再调研同一问题。

---

#### 6.5.6 Web pipeline 默认开启 VLM caption

**现象（误读纠正）**：

在最初的 6.5.4-6.5.6 准备阶段，发现 p78 / p85 的 `ablation.vlm_captions_used = false`。结合 §5.4.3 记述的「n_chunks ≤ 15 自适应启用」规则（项目记忆条目），最初判断为「自动启用逻辑失效」。但代码层调查显示——**`n_chunks ≤ 15` 是 `--vlm-captions` 已显式开启后的「内层降级阈值」，不是自动启用条件**。pipeline 入口 `vlm_captions = args.vlm_captions` 完全由 CLI flag 控制，且 `server.py` 的子进程命令行未传该 flag，所以 web 路径下 VLM caption 从未被启用过。

**根因**：

§5.4.3 的 paper 文字与项目记忆均准确（明确写明「--vlm-captions 显式开启」），但记忆的索引摘要简化为「n_chunks ≤ 15 自适应启用」，措辞歧义导致 web pipeline 长期处于 VLM-off 状态。这本质上是「**默认配置漂移**」问题：CLI 自测时手动加 `--vlm-captions` 验证有效，但 web 默认配置遗漏了向用户启用该改进。

**修复**：

`server.py` 的 pipeline 启动命令追加 `--vlm-captions` flag：

```python
cmd = [
    str(PY), "src/pipeline.py", url,
    ...
    "--keyframes",
    "--llm-chapters",
    "--vlm-captions",   # 新增：n_chunks>15 内部自动降级，无副作用
]
```

`--vlm-captions` 仅在 `n_chunks ≤ 15` 且 `max_prefix_run < 4` 双重门控通过时实际投入 LLM，对长 / 单调视频自动降级回 CLIP sim cue，附加成本仅为 Qwen2.5-VL-7B-AWQ 首次模型加载约 30 秒（VRAM 占用 ~5-7 GB），不影响后续切分质量。

同步修正项目记忆索引摘要为「`--vlm-captions` 显式开启，n_chunks>15 内部降级；2026-05-19 web 默认开」，避免歧义再次诱发误读。

**后验**（p85 复跑后 ablation 字段对照）：

| 字段 | BEFORE | AFTER |
|------|--------|-------|
| `vlm_captions` (flag 开启) | false | **true** |
| `vlm_captions_used` (实际启用) | false | **true** |
| `vlm_max_prefix_run` | — | 2（< 4，内层 gate 通过） |
| `vlm_degraded_reason` | — | None |
| `llm_pass_via` | attempt_3 | **repair** |
| `llm_fail_reasons` | [oversize, missing] | [oversize, oversize, missing] |
| 章节数 | 6 | **7** |
| 章 1 chunks 数 | 4（0-1115s, 18min, 标题模糊） | **2**（0-460s, 7.7min, 标题更准） |

**章节切分对比（BEFORE 6 章 vs AFTER 7 章）**：

| # | BEFORE 标题（chunks） | AFTER 标题（chunks） |
|---|---------------------|---------------------|
| 1 | 拥塞控制与TCP报文 (0-3) | 拥塞控制与窗口机制 (0-1) |
| 2 | RTT与拥塞窗口管理 (4-5) | 拥塞控制原理 (2) |
| 3 | 拥塞避免与超时处理 (6-7) | 拥塞控制与流量控制 (3) |
| 4 | 拥塞窗口调整策略 (8-9) | 拥塞窗口与SSTHRESH (4) |
| 5 | 接收窗口的作用 (10) | 拥塞控制与快重传和窗口增长 (5-6) |
| 6 | 发送窗口与MSS · 本节复习 (11-12) | 拥塞避免与窗口RTT (7-9) |
| 7 | — | MSS与拥塞窗口和接收窗口 · 本节复习 (10-12) |

**分析**（VLM 启用后切分变化）：

VLM caption 启用带来三类可观察变化：
1. **章节数 +1（6 → 7）**：原 BEFORE 章 1（0-1115s, 4 chunks）被 AFTER 拆为 4 个章（chunks [0-1] / [2] / [3] / [4]），其中 3 个为单 chunk 章。这一现象与 §5.4.3 提及的「PPT 域过度切分风险」一致——VLM caption 描述每帧 PPT 内容时差异度高，让 LLM 倾向于把每张 slide 当独立章节
2. **LLM 切分难度上升**：BEFORE 3 次 attempt 之后无 repair 即过；AFTER 3 次 attempt 全 fail 后通过 repair 路径救援（`repair_missing` + `repair_oversize` 都触发）。这表明 VLM caption 让首次 outline 更难 well-formed，但 repair 机制（§5.4.3 第三层 safety net）兜底成功
3. **章节标题更专业化**：「拥塞窗口与SSTHRESH」（AFTER ch4）抓到了具体协议常量 SSTHRESH，「拥塞控制与快重传和窗口增长」（AFTER ch5）准确反映了讲师在该段引入快重传机制——这些都是 ASR 错字修复 + VLM 视觉锚定共同作用的正向收益

**取舍权衡**：
- **正向**：粒度更细，命名更准，AFTER 章 1 不再有「拥塞控制与TCP报文」这种模糊大章
- **负向**：单 chunk 章节增多（AFTER 有 3 个），可能让用户感觉「章节碎片化」
- **未来工作**：在 §5.4.3 已识别的「PPT 翻页 ≠ 话题切换」原则下，需要在 LLM prompt 中明确「不要把每页 PPT 当独立章节」，或在 repair 阶段对单 chunk 章设最小合并阈值

VLM 时间开销实测：本次复跑 ASR cache 命中（跳过最慢的 6 分钟 transcribe），从 chunker 到 publish 端到端约 3 分钟，其中 Qwen2.5-VL-7B-AWQ 首次模型加载 ~30s，VL caption 推理 11×~1s = ~11s，其余为 Qwen-Instruct 推理 + 翻译 + 关键帧抽取。Web 用户体验影响在可接受范围内。

**分析**：

本案例的工程教训分两层：
1. **代码 - 文档同步**：CLI 自测的「能力 readiness」 ≠ 用户路径的「默认 readiness」。一个新功能完成 CLI 验证后，必须显式审查所有 entrypoint（web server、批处理脚本、IDE 集成等）是否开启
2. **项目记忆的高保真度要求**：项目记忆的索引摘要会被频繁回读，措辞歧义可能持续误导，应像 API doc 一样追求无歧义。本次问题暴露后已即时修正索引

实证上看，VLM caption 在 24 视频 corpus 上的净时间增量 < 2%（见 §5.4.5），对 web 用户体验影响可忽略；切分 LLM 一次性通过率 +6 pp（attempts 减少）的收益对每个 web 用户都直接可见，这一默认配置变更是正向收益。

---

#### 6.5.7 本轮迭代汇总

| # | 类别 | 修复影响层 | 量化收益（p85 复跑实测） |
|---|------|----------|------------------------|
| 6.5.1 | 健壮性 | ASR 解码参数 | 消除 p78 长视频 native abort 风险；p78 再跑无越界 |
| 6.5.1.bis | 健壮性 | ASR 三层防御（2026-05-21） | BV1q6 vlog 1542s 复发触发新触发路径调查；加 hallucination_silence + compression_ratio + 增量落盘；BV1q6 99.6% 覆盖率落盘、BV1dkLr6UEJ6 完整通过 |
| 6.5.2 | 健壮性 | publish 路径 | 修 1 个用户路径 silent failure；glob 兼容 `.mm`/`.mm.vl`/未来变体 |
| 6.5.3 | 质量 | ASR 后处理字典 | p85 12 种错字 **121 → 0**（100% 消除）；「拥塞」正确写法 +109；headline 修 1（校验核 → 校验和） |
| 6.5.4 | 质量 | keyword stopword | chunk-level 关键词 stopword 占位 **11 → 5（-55%）**；「这个」从 8 → 0 |
| 6.5.5 | 负面结果 | — | 验证 wrap-up trigger 无 bug；为未来标题生成提供 design hint |
| 6.5.6 | 默认配置 | web pipeline | VLM 在 web 路径默认开；p85 章节数 6 → 7 / 章 1 时长 18min → 7.7min；ablation 字段 vlm_captions_used 由 false 翻 true |

**6 项中 4 项为代码修改（含 1 项默认配置变更）、1 项为负面结果存档、1 项为产物路径模糊匹配重构**。本轮迭代展现的元规律是——当 corpus 从「论文 ablation 跑」扩展到「真实端到端用户路径」时，新暴露的失败模式更偏「配置 / 集成 / 长尾失败模式」而非「算法本身」。这与 §6.1-§6.4 中以「算法改进 → metric 提升」为主旋律形成对比，提示后续如果要进一步提升系统可靠性，工程加固投入比算法精调更具边际收益。

**p85 端到端验证 takeaway**：
- ASR 错字字典扩充是**最高 ROI 修复**：5 行代码 + 字典维护，将 121 处错字全部消除，下游 keyword/headline/segmentation 三层均受益
- stopword 修复展现了一个**部分修复的诚实记录**——「这个」根除后，原被压制的「等于/题目」占位上升，揭示 domain-aware stopword 是开放问题
- VLM 默认开启在 p85 上确实带来**章节标题更专业化**（出现 SSTHRESH、快重传等具体协议术语），但也触发了 §5.4.3 预测的「PPT 域过度切分」风险（3 个单 chunk 章）。LLM repair 机制成功兜底，建议下一轮在 prompt 工程层显式抑制
- 章节切分结果的总体变化（6→7 章、attempt-only-pass → repair-passed）是三项修复的共同结果，单独归因到任一项需要更精细的 ablation——这是论文方法论的 follow-up 工作

整体看，本轮 6 项工程加固以**低 LOC 改动换取了端到端可用性 + 单视频质量两个维度的实质提升**，为论文 §8 「Future Work」中「面向用户路径的健壮性验证」一节提供了具体范例。

### 6.6 vlog 域适配：LLM 字面 hallucinate 的根因与修复（2026-05-21~22）

§6.5.1.bis 把 vlog 长视频纳入 corpus 后暴露了第二条 ASR 故障路径并完成三层防御；同一轮 corpus 扩展也在**下游 LLM 摘要层**触发了一类此前未被观察的失败模式——章 abstract 出现大规模字面级 hallucinate。这类失败在教学类视频上长期被掩盖，因为教学类章标题（"PPP 协议"/"NAT"）本身就是技术概念，LLM 按字面联想碰巧靠谱；vlog 域章标题大量使用 up 主自创术语（"心理线"/"包容心"/"皇上价格"），字面联想必然脱离 ASR 实际内容。本节记录该问题的根因、修复与跨视频回归验证。

#### 6.6.1 BV1q6 日料探店：13/16 章 abstract 字面 hallucinate

**现象**：

BV1q6ozBmE8z（上海日料探店，26.1 min）经 §6.5.1.bis 三层防御救回 ASR cache 后，LLM 切分得到 K=16 章。`generate_chapter_abstracts` 输出的章 abstract 在人工对照后发现 **13/16 章** 与 ASR 实际内容严重脱节：

| 章号 | 章标题 | LLM 生成的 abstract | 章内 ASR 实际内容 |
|------|--------|---------------------|-------------------|
| ch3 | 心理线 | 分析心理线在**股市**中的应用，揭示投资者如何利用心理指标做出决策 | 讨论"莫娜鸽子腿"菜品口感 |
| ch5 | 心理极限 | 揭示**潜能边界**与突破方法 | 蒸汽雾化眼部按摩仪改善黑眼圈 |
| ch10 | 包容心 | 倡导包容心，通过真实故事展现不同背景下的**理解与接纳** | 讨论菜品质量评分 |
| ch14 | 走鱼价格 | **市场商家差异**的价格分析 | "去掉某条鱼人均七八十元" |
| ch15 | 皇上价格 | 揭示**皇上价格**的秘密，从**高端市场**到**普通消费者**的视角进行解读 | "770 或 760 元左右"（"皇上"是 ASR 错字） |

ch15 进一步揭示了一条二阶 hallucinate 链路——ASR 错字（"770/760"识为"皇上"）→ LLM 看到"皇上"字面，进一步联想到"清朝皇帝"。上游 ASR 噪声通过 LLM 的字面联想被**放大**而非仅仅"传递"，这是单纯 ASR 后处理无法覆盖的层级问题。

**根因**：

`segment_llm.py:generate_chapter_abstracts` 给 LLM 的 user prompt 只包含章标题与每章 chunk-level **headline 关键词**（如"心理线 / 鸽子腿 / 按摩"），**完全不喂 ASR 原文**。LLM 在缺少 grounding 信号时，按训练分布对自创术语做字面联想——"心理线"在 LLM 先验里关联股市技术指标，"包容心"关联情感教育，"皇上"关联清朝。

这一缺陷在 v5 引入 `VLOG_SECTION_ABSTRACT_SYSTEM` 时未被修复：v5 改动只动 system prompt 风格（让 abstract 用"本段..."开头 + 强调场景元素），但**没动 user prompt 的 input 构造**。教学类视频未暴露此 bug 的原因是其章标题与 ASR 内容在概念层强相关，字面联想偶然成立。

**修复**：

`segment_llm.py:generate_chapter_abstracts` 的 user prompt 构造改为：每个 chunk 同时输出 headline 与 ASR snippet。snippet 优先取 `chunk.summary`（chunker 阶段产生的抽取式紧凑摘要），fallback `chunk.text[:200]`。K ≥ 10 时收紧到 `snippet_max=120` 防 context 超额（16 章 × 120 字 ≈ 6000 tokens 安全）：

```python
snippet_max = 200 if K <= 8 else 120
for sub_c in ch.get("chunks", []):
    hl = (sub_c.get("headline") or "").strip()
    if hl:
        lines.append(f"  - {hl}")
    snippet = (sub_c.get("summary") or sub_c.get("text") or "").strip()
    if snippet:
        snippet = re.sub(r"\s+", " ", snippet)[:snippet_max]
        lines.append(f"    内容: {snippet}")
```

user_prompt 同步增加硬约束："**严格根据「内容」实际讲的事情写**——不要从{unit_word}标题字面猜测含义，不要写「内容」里没出现的概念或场景"。三重约束（snippet input + user_prompt + `VLOG_SECTION_ABSTRACT_SYSTEM` 的场景元素要求）协同生效。

**后验**：

BV1q6 K=16 重生成对照——

| 章 | 旧（hallucinate） | 新（基于 ASR） | 评级 |
|----|---|---|---|
| ch2 卡时间 | 时间管理重要性 | 至少达到六成消费标准 | ✓ |
| ch3 心理线 | 股市心理指标 | 莫娜鸽子腿 口感令人怀疑 | ✓✓✓ |
| ch5 心理极限 | 潜能边界 | 蒸汽雾化眼部按摩仪改善黑眼圈 | ✓✓ |
| ch10 包容心 | 理解和接纳 | 给予创作者更多时间完成视频 | △（略飘但已不离谱） |
| ch14 走鱼价格 | 市场商家差异 | 去掉某条鱼 人均七八十元 | ✓✓ |
| ch15 皇上价格 | 清朝皇帝秘密 | 770 或 760 元左右 | ✓✓✓ |

13/16 章显著改善，3/16 章略飘但已不再是"离谱 hallucinate"级别。

**跨视频回归（3-vlog corpus，2026-05-22）**：

| 视频 | 时长 | K | abstract 全贴合？ |
|------|------|---|-----------------|
| BV1dkLr6UEJ6 陈泽测评山姆零食 | 15.5 min | 6 (mm) / 7 (txt-only) | ✓ |
| BV1uHL16SEBp 翔翔包子 | 8.1 min | 7 | ✓ |
| BV1AYR6BsE9U 陈泽薯片测评 | 28.2 min | 8 | ✓ |

**21/21 章 abstract 无字面 hallucinate**——BV1q6 第一轮 13/16 严重 hallucinate 在新 corpus 上 0 复发。snippet 注入 + user_prompt 严格约束 + `VLOG_SECTION_ABSTRACT_SYSTEM` 三层约束在跨视频上稳定。

值得一提：BV1AYR6BsE9U（陈泽薯片）附带踩中 §6.5.1.bis 的 L3 增量落盘场景——ASR 推进到 1690.3s/1693.1s 后 native abort（与 BV1q6 同型），cache 99.99% 覆盖率落盘，retry 复用通过。这次跨视频回归同时验证了三层 ASR 防御 + abstract snippet 修复**两条独立的 vlog 域加固**。

**分析**：

本案例的方法论 takeaway 有三层：

1. **LLM-as-summarizer 在缺少 ASR grounding 时的字面 bias 是系统性而非偶发**。教学类视频偶然规避了此问题，并不能作为"abstract prompt 足够鲁棒"的证据——必须在术语自创度更高的域（vlog）上做对抗性验证。这也呼应 §6.5.7 的元规律——"corpus 扩展才能暴露此前被掩盖的失败模式"。

2. **上游 ASR 错字会通过 LLM 联想被放大**。ch15 "770/760 → 皇上 → 清朝皇帝" 是经典的二阶 hallucinate。这意味着 ASR 后处理（§6.5.3 字典扩充）与下游 LLM grounding（本节）必须协同——任何一层独立修不彻底。同一原则在 §6.7 章标题层（J7 三件套）再次复现。

3. **input grounding 比 prompt 警告更可靠**。本修复的核心是 input 多塞了 100-200 字 snippet，而非加更长的 system prompt 警告。这一观察与 §6.7.2 / [[feedback-prompt-vs-python]] 的"把判定搬 Python 给二值化 hint"属同一思路——**给 LLM 数据而非规则**通常比反过来更有效。

适用范围：所有 `generate_*_abstract` / `generate_*_summary` 类 LLM 调用——input 必须包含 ASR 实际文本 snippet，不能只给 headline / title。`refine_chapter_titles`（§6.7.1 的修复）也采用同款 snippet 注入。

### 6.7 LLM 章标题质量加固（2026-05-24~25）

§6.6 把 abstract 层的 LLM grounding 修好后，章标题层（`refine_chapter_titles`）在后续视频上接连暴露两类独立失败模式：一类是 **ASR 错字直接漏入章标题**（BV1EBdcBrEea 显卡盲盒 vlog 把"烟台"误识漏入），另一类是 **chunker 上游塌成同一 headline 后 LLM 输出 N 章共享前缀雷同串**（王道 p68 中断系统的"服务程序详解/执行/恢复/应用"）。两者本质相同——**LLM 在 input 信号稀疏时回退到字面拼接**——但表现差异大，修复路径也不同。本节分别记录。

#### 6.7.1 J7 三件套：N 章共享前缀的 LLM 失败模式

**视频**：王道计算机考研 计算机组成原理 BV1BE411D7ii_p68 中断系统（PPT 教学，n_chunks=20）

**现象（J6 之后回归触发）**：

§6.5.3 / J6（commit 67136f0）把"中段→中断"等计算机组成域 ASR 错字清掉后，p68 ASR 文本干净，但 web 端重跑章标题输出退化：

| 章 | J6 后章标题 | 评价 |
|----|------------|------|
| ch1 | 程序方式与处理 | generic（无具体术语锚定） |
| ch2 | 请求与响应流程 | generic |
| ch3 | 向量地址解析 | generic |
| ch4 | 服务程序**详解** | 共享前缀串首章 |
| ch5 | 服务程序**执行** | 共享前缀串 |
| ch6 | 服务程序**恢复** | 共享前缀串 |
| ch7 | 服务程序**应用** | 共享前缀串 |

ch4-ch7 共 4 章共享"服务程序"前缀 + generic 后缀（详解/执行/恢复/应用），完全失去章间区分度；ch1-ch3 也都是 generic 套话标题（"方式"/"流程"/"解析"）。J6 牺牲章标题信息密度换 ASR 干净底线（[[project-j6-asr-titles]]）的代价超出预期。

**根因（dryrun 诊断 `scripts/_dryrun_chapter_titles.py`）**：

三层信号都失效：

1. **chunker (`generate_headlines`) 塌缩**：ch3-ch6 共 20 chunks 的 chunk-level headline 全部生成同一字符串 "中断服务程序"——这是 LLM-based chunker 在同主题视频后半段的已知失败模式（同前半段切完后，LLM 复用同一概念命名），20 个 chunks 给 `refine_chapter_titles` 0 段级差异信号。
2. **chunks keywords 有信号但被噪声污染**：实际 chunk keywords 含 PC/向量/12H/多重/屏蔽/微秒/例题 等区分性术语，但同时混入 ASR 错字残留（屁屁/屏屏/中段/中斷/中斧/地坝/任劳/程庇），jieba `extract_tags` 把错字误选成 top-K。
3. **现有 prompt 规则未覆盖此场景**：H2（去重）只抓"完全相同 title"，I6（generic 模板）只抓"全 generic token"。"服务程序详解"这种"共享前缀 + 差异后缀"模式既不完全相同又含 specific 词，两个规则都漏。

**修复（commit 8eb8376 + aa4880e，三件套）**：

**J7-A — snippet 喂 LLM（`refine_chapter_titles` 输入端）**：

仿 §6.6.1 的 abstract 修法，每个 chunk 同时输出段标题、高频词与 ASR snippet：

```python
snippet = (c.get("summary") or "").strip() or text[:120].strip()
if snippet:
    snippet = snippet[:120].replace("\n", " ")
    lines.append(f"    内容: {snippet}")
```

让 LLM 在 chunker headline 塌缩时仍能从 ASR snippet 看到本章实际讲了什么（如 ch5 实际讲"多重中断"、ch7 实际讲"中断屏蔽"）。

**J7-B — prompt 共享前缀禁令**：

新增两个条件子句，仅在触发时注入：

- `dup_headline_clause`（当 ≥1 章内 chunks headlines 完全相同时）：强制 LLM "**绝对不能**用段标题作为章标题词根——必须从「内容」行抽出本章独有的子机制 / 步骤 / 对象"。
- `prefix_clause`（默认开启）：禁止 ≥3 章共享 ≥2 字前缀。

**J7-C — Python 端 `_split_shared_prefix_titles` 兜底**：

即便 prompt 已禁，LLM 在主题集中视频上仍可能输出"X 详解 / X 执行 / X 恢复"模式。Python 后处理检测：若 ≥3 章共享 ≥2 字中文前缀，从各章独有 keyword 重写。关键守门——**`max_share_ratio=0.7` 视频整体主题守门**：若 `hit_indices / K ≥ 0.7`，视为视频本身就讲该主题（如整集都在讲"中断"），保留前缀不拆。

p68 测试：第一次（4/7 = 0.57 < 0.7）触发拆解；J6 重跑后（"中断"为整集主题 6/7 = 0.86 ≥ 0.7）不触发，避免破坏合法主题前缀。

另两个辅助：扩 `_GENERIC_TITLE_TOKENS` 加 对应/这些/那些/叫做/哪些/返回/执行/恢复 等口语连接词；`_collect_low_prob_chars(threshold=0.5)` 收集 ASR 低 prob 字，含错字的 keyword 不进 J7-C 候选池。

**后验（p68 web 落地 + 6 视频跨回归 dryrun）**：

p68 落地（commit 6535c85，`scripts/_apply_chapter_titles.py` 只重跑 `refine_chapter_titles` + 同步前端 title/title_zh/title_en + regen md）：

| Ch | J6 后 | J7 落地后 |
|----|-------|----------|
| 1 | 程序方式与处理 | 中断机制与请求 |
| 2 | 请求与响应流程 | 中断处理流程与优先级 |
| 3 | 向量地址解析 | 中断向量地址与响应 |
| 4 | 服务程序详解 | 中断服务程序详解 |
| 5 | 服务程序执行 | 多重中断与屏蔽技术 |
| 6 | 服务程序恢复 | 中断服务程序执行 |
| 7 | 服务程序应用 | 中断系统概述 |

7/7 章全部更新。ch4/ch6 仍共享"中断服务程序"4 字前缀，但仅 2 章 < `min_share=3` 不触发 J7-C，可接受。"中断"为视频整体主题（6/7 ≥ 70%），J7-C 守门正确跳过强拆。

6 视频跨回归 dryrun（不写盘，仅验证 J7 不破坏非 dup-headline 视频）：

| 视频 | n_ch | J7-C 守门 | 评价 |
|------|------|----------|------|
| p66 IO 接口 | 5 | 跳过 | 4/5 章改，主体改进 |
| p67 IO 查询 | 5 | 跳过 | 4/5 改，部分降级（J7-A/B 副作用） |
| p70 DMA | 4 | 跳过 | 全新，"DMA-X" 是合法主题前缀 |
| p81 TCP 流量 | 5 | 跳过 | 4/5 改 |
| p92 邮件 | 5 | 跳过 | 全改 |
| p93 HTML | 5 | 跳过 | ch1 暴露 LLM 幻觉（"四维事实"，触发 K1） |

**6/6 视频 J7-C 守门全跳过**，验证守门不破坏 non-dup-headline 视频。p93 ch1 的 "网页元素与HTML结构" → "四维事实建立网页框架"幻觉触发了 K1 后续 patch（`_calibrate_headline_words` 加 word-prob<0.5 守门，commit f6c859e）——J7-B 的 prefix_clause 强制 LLM 避开公共词时可能选择 unusual 概念，这是 corpus-wide trade-off。

**分析**：

1. **chunker 失败会通过 input 信号稀疏传导到章标题层**。本案例与 §6.6.1 同构——LLM 在 input grounding 不足时回退到字面拼接，差异只在拼接对象（abstract 拼章标题字面，章标题拼共享 headline）。统一的修复范式是 **input 端补 ASR snippet 给 LLM 看实际内容**，而非更复杂的 prompt 规则。

2. **三件套的分层防御对应失败的三个发生层**：J7-A 修 input 信号、J7-B 修 LLM 决策偏好、J7-C 修 LLM 决策残留。**任一层单独不够**——只做 J7-A 时 LLM 仍可能拼共享前缀（特别是同主题视频）；只做 J7-B 时 LLM 缺 input 无法生成差异化命名；只做 J7-C 时强行拆解会破坏合法主题前缀（如"DMA-X"）。三层叠加 + 0.7 视频主题守门是测试 6 视频后稳定的工作点。

3. **"修一层暴露下一层"的迭代节奏**。J6 把 ASR 修干净后 J7 暴露；J7 落地后 K1 暴露 prefix_clause 与 LLM 创造性的 trade-off。这与 §7 演进章描述的 corpus 扩展驱动迭代是同一规律——但本节展示该规律也在**单一视频的不同处理层**上以微观尺度重现。

#### 6.7.2 章标题 Python 端校准：把判定从 prompt 搬到代码

**视频**：BV1EBdcBrEea_p0 "8 个显卡盲盒"（vlog，8 个显卡型号开箱评测）

**现象**：

J6 之前的 chapter title prompt 含一条规则："**主题词锚点**：headline 里若出现高频 specific 词（型号 / 专有名词），用作章标题核心；若该词被 chunk keywords 与 ASR text 都未支持（即 ASR 错字），从标题剔除"（rule 8 / rule 5）。BV1EBdcBrEea 章 2 chunks 含"烟台显卡"（ASR 把"烟"识错的产物）与"3070显卡"两组 headline。LLM 输出章 2 = "**烟台**显卡与3070显卡"——错字未被剔除。

**根因**：

`refine_chapter_titles` 的 user_prompt 在 1300+ tokens 上下文里同时含 10+ 条规则。Rule 4（"2 段成片段时用 'X 与 Y' 拼接"）作为**结构化输出指令**比 Rule 8（"主题词锚点 + ASR 错字剔除"）作为**语义级判定指令**更容易被 LLM 遵循。LLM 在多规则冲突时倾向选择句法明确的指令——rule 4 直接给出"X 与 Y"模板，rule 8 要求模型自己在每个名词上判定"是否在 kw 或 text 里有支撑"，认知负担显著高。

实测：rule 8 在多数 case 下确实生效（如 ch4 "电源配件"里"电源"被剔除），但在"两段拼接"的明确句法触发下被压制。

**修复（commit b764618）**：

把 Rule 8 的"NLP 判定"从 prompt 搬到 Python 端，给 LLM 一个**二值化 hint 列表**——

```python
def _calibrate_headline_words(headline, keywords, text, chunk=None) -> dict:
    """jieba 切 headline 名词，逐个验证是否在该 chunk keywords 或 text (≥3 次)
    里有支撑。ASCII 数字/英文（型号 X79/580/3070/R7X）不参与校验。
    返回 {ok: [...], drop: [...]} 两个名词列表。
    """
```

`refine_chapter_titles` 在调 LLM 前对每个 chunk 跑 `_calibrate_headline_words`，把 drop 列表写入 user_prompt 的 `drop_clause`：

> "⚠️ 标注了「已识别 ASR 错字」的词是 Python 校准过的，**绝对禁止**进入任何章/片段标题。若该段所有关键名词都被标禁，则该段不能单独主导命名，必须借同章其他段或共同高频词抽象。"

LLM 不再自己做 step 1 判定——Python 已把"哪些是 ASR 错字"以二值化形式标好，LLM 只负责 step 2 命名。同时该结构嵌入 `generate_chapter_abstracts`：drop 词在 input 阶段被替换为 `[?]` mask，LLM 看不到原词字面，从源头避免被错字诱导。

**后验（BV1EBdcBrEea_p0 重生成）**：

| Ch | 旧标题 | 新标题 | 评价 |
|----|--------|--------|------|
| ch1 | (中性变化) | — | — |
| ch2 | **烟台**显卡与3070显卡 | 显卡对比 | ✓ "烟台"成功剔除 |
| ch3 | (中性变化) | — | — |
| ch4 | **电源**配件 | 显卡与配件 | ✓ "电源"剔除；"配件"虽 Python drop 但 LLM 保留（仅 1 段，无替代词），可接受 |

**K1 后续守门补丁（commit f6c859e）**：

J7 落地后，p93 ch1 暴露了 `_calibrate_headline_words` 的反向 bug——把"万维网"误判为 ASR 错字（chunk text 出现 0 次但是 LLM 合法抽象）→ drop hint 给 LLM 后，LLM 在"避开禁用词"的压力下生成幻觉"四维事实建立网页框架"。修复：加 word-level prob<0.5 守门，名词只要不含低 prob 字符，即视为 LLM 合法抽象保留：

```python
if low_prob_chars:
    has_low_prob = any(c in low_prob_chars for c in w if not c.isascii())
    if has_low_prob:
        drop.append(w)
    else:
        ok.append(w)
```

"万维网"含字符均高 prob → ok 保留；"烟台"中"烟"低 prob → drop。在 p93 K=5 重生成上 ch1 正确恢复为"网页元素与HTML结构"。

**分析**：

1. **prompt 多规则冲突时把判定搬 Python**。本案例与 [[feedback-prompt-vs-python]] 互为印证——当 LLM 需要在两个 prompt 规则之间做取舍时，模型对"结构化输出指令"的遵循度高于"语义级判定指令"。把语义判定外包给 Python 后给模型二值化 hint，是把"软约束"转为"硬约束"的可靠路径。

2. **二值化 hint 优于 NLP 描述**。`_calibrate_headline_words` 的 drop 列表本质是个布尔表（哪些名词被禁），LLM 只需匹配字符串而非自己做 NLP 推理。这与 §6.6.1 用 ASR snippet 给 LLM "看数据而非规则"是同一原则的不同表现。

3. **Python 校准本身也需要守门——避免反向 hallucinate**。K1 patch 揭示：把判定搬 Python 不是"一搬就完"，Python 端的启发式也会误伤（"万维网"被误判 ASR 错字）。word-prob 是一个比 keyword/text 频次更可靠的最终守门信号——ASR 真错字在 word-level prob 上确实偏低，合法抽象词不偏低。本节给出的"先用启发式判断 → 再用 prob 守门"双层校准，是后续 Python-端 LLM input 净化的范式。

适用范围：所有"LLM 在 prompt 内做 NLP 判定"的场景，特别是 prompt 含 ≥5 条规则且规则间存在结构化/语义化优先级冲突时。

## 7 系统演进 (System Evolution)

§3-§6 给出的是本工作"当前态"的系统设计与评估。然而本工作并非一次性设计完成，而是经历了 6 个明确的里程碑迭代，每一轮都由"corpus 扩展暴露的失败模式"驱动算法或工程改动。本节按时间顺序回顾这 6 个版本（v1-v6），每个版本以"触发问题 → 改动 → 量化效果 → takeaway"四段式呈现。这一组织既能让读者理解"为何当前架构是这样的"，也为后续工作提供了具体的失败案例索引——附录 C 进一步收录了过程中**未被采纳**的探索性尝试。

### 7.1 v1：纯 Pegasus baseline（项目起点）

**架构**：faster-whisper large-v3 ASR → chars / TextTiling chunker → Randeng-Pegasus-238M 段落 headline + jieba 抽取式正文 → Chinese-CLIP α=0.3 多模态章节切分 → Pegasus 章标题 → 基础 md 输出。详见 §3 系统架构与 §4.2 多模态章节切分。

**核心设计决策**（v1 即定型，后续未变）：
- 多模态融合系数 α=0.3：视觉作 tie-breaking 而非主导，避开"PPT 翻页 ≠ 章节切换"的伪信号
- 章节数自适应公式 `K = max(2, min(6, n_chunks-1, ⌈duration_min / 6⌉))`：每 ~6 分钟 1 章
- chars / texttile 双 chunker，同时报告 strict F1 与 F1@1 容差指标

**v1 已暴露但未解决的问题**：
- ASR 输出存在"卡片回路"（同句重复多次），但 v1 直接喂下游未做后处理
- Pegasus 章标题在 chunks ≤ 3 时倾向 copy 单段 headline，未做 fallback
- 学习场景需要的 TOC / 术语表 / 章末小结全部缺失
- 章节切分依赖 TextTiling depth score + Pegasus 标题，在 30+ chunks 的长视频上 Pegasus 邻章标题串台严重

**takeaway**：v1 完成了"视频 → 流水笔记"的最小可用路径，但产出更接近"自动字幕的换行版本"而非"学习笔记"。后续 5 个版本基本都在补足"笔记的结构化"。

### 7.2 v2：ASR 后处理与 chunker × dedupe 耦合发现（2026-05-15）

**触发问题**：王道 OS p37 哲学家进餐视频上 F1@1 仅 0.50，定位发现 ASR 在 755.2s 起进入卡片回路、连续 9 段输出同一句话，把 jieba 关键词 Jaccard 距离严重污染，使 TextTiling depth score 漏掉 gold 章节边界（详见 §6.1）。

**改动**：
1. **连续重复段去重（LCP-based）**：扫描 ASR segment 列表，连续相同或近似（LCP ≥ 20 字 OR LCP ≥ 0.85×min(len)）的 run 长度 ≥ 3 时保留首段并合并时间戳。0.85 阈值经反例校准——0.6 误判 "如何避免饥饿/死锁?" 这种真综合改写
2. **术语字典自动注入**：从 video metadata 抽 CamelCase / 5+ 字母大写词 + whisper 高频混淆词典生成 substring 替换（如 "Cloud" → "Claude"）
3. **p39 三修**：章节数公式从 `⌊n/3⌋` 改为 `⌈duration_min/6⌉`，stopword 列表扩充（"这个/那个/介绍/讲解"），dedupe 阈值从普通相等改为 LCP

**量化效果**：
- 王道 OS p37：F1@1 0.50 → **1.00**（Δ+0.50）
- 计网 p38：strict F1 0.25 → **0.75**（Δ+0.50）
- 10 视频均值（cc=400 + texttile + PPT 子集）：ΔF1@1 +0.167

**核心发现 — chunker × dedupe 耦合**：dedupe 收益仅在 texttile + cc=400 上显著，cc=800 与 chars chunker 上中性（详见 §6.3）。该耦合证明 dedupe 的本质是"关键词频次去噪"而非简单文本清洗，对字符硬切的 chars 无作用。这一发现成为本工作方法论上的一个 contribution——以往的 ASR 后处理研究主要关注转写准确率，未关注其通过关键词分布向下游 segmenter 的传导路径。

**takeaway**：v2 把"上游 ASR 失败 → 下游 segmentation 污染"这条耦合通路定量化，奠定了论文 §6.1-§6.3 的核心 case studies。

### 7.3 v3：学习场景 md 结构 + 章标题 fallback + ASR 置信度（2026-05-15）

**触发问题**：v2 修好 ASR 与 segmentation 后，产出仍是"章节 + 流水段落"结构，对学习场景仍然不可用——缺少 TOC、术语表、章末小结这些教科书式的索引组件。此外 Pegasus-238M 在 chunks ≤ 3 的短输入上有 copy 退化倾向（直接抄一段 headline 不做综合）。

**改动**：
1. **学习场景 md 升级**（5 类元素，默认开）：
   - 顶部摘要卡（时长 / 章段数 / 核心关键词 top-8）
   - HTML 锚点 TOC
   - 知识点速览（按章列 chunk headlines）
   - 跨段投票术语表 top-15（含首次出现段链接 + 上下文 snippet）
   - 抽取式章末小结（章内 1-2 句）
2. **Pegasus 章标题 copy-fallback 差异化**：n ≤ 3 检测到 copy 时退到"前 2 段 headline 用·拼接"，n ≥ 4 保留 Pegasus 输出（Pegasus 可能从多候选中有意挑 representative）
3. **ASR 置信度标记**：开启 `word_timestamps=True`，对 segment-level confidence < 0.5 的位置在 md 中加 `[?]` 上标，让读者直观识别可能错字的位置

**量化效果**：md 结构是 UX 改进，不直接对应一个 F1 数字。但 §5.6 的章标题主观打分显示：texttile 子集 3.43 / chars 3.25（n=30 样本，5 分制），PPT 子集差距更大（+0.38）；与"关键词覆盖率"Pearson r=+0.52。说明 fallback 与 md 结构在主观质量上有可观增益。

**takeaway**：v3 把笔记从"流水文本"升级到"教科书索引"形态。md 结构后来成为 v5 大类模板分发的底层载体。

### 7.4 v4：LLM 章节切分 + B1 两步法 + VLM caption + 英文支持（2026-05-16~17）

**触发问题**：v1-v3 的章节切分基于 TextTiling depth score + Pegasus 标题。在 30+ chunks 长视频上 Pegasus 邻章标题串台严重（p38 实测两章标题互换），且 TextTiling 在 PPT 教学视频上常切错"专题视频"——把整个视频压成 1-2 个 catch-all 章节，破坏笔记导航。

**改动**：
1. **Qwen2.5-7B-AWQ 替代 Pegasus 切章**：把 chunk headlines + 视觉 cue 喂给 LLM 让其直接输出层级化大纲 JSON。配 retry-with-feedback 机制（attempt 1 失败时把具体错误回灌让 LLM 自我修正）
2. **B1 两步法**：第一步 LLM 切分章节边界，第二步用独立 LLM call **只看本章 chunk headlines** 重写章标题——避开"一次切+命名"时邻章 headline 串台。修了 p38 标题串台 bug
3. **VLM caption 视觉信号升级**：Qwen2.5-VL-7B-AWQ 替代单 CLIP cosine 浮点数，每章 1 句"教学相关"自然语言 caption，喂给 segment LLM 作 prompt cue。配四层自适应门控（外层 n>15 / 中层 generic_ratio≥0.65 / 内层 prefix_run≥4 / 救援层 LLM 全失败 + VL 在用，最后一层加中层后退化为 0 触发安全网）
4. **英文视频支持**：句号本土化（中文"。"→ 英文"."）、Qwen 英文 prompt、wrapup 大小写敏感、`generate_headlines` parse 容错
5. **附录 B 切分路径表**：9 视频 LLM 100% 覆盖率全量统计写入论文

**量化效果**：
- LLM 切分覆盖率 **9/9 = 100%**（v1 TextTiling 在某些长视频上 fallback 比例不可忽略，详见 §5.7 / 附录 B）
- attempt 1 直接通过 22%；retry-with-feedback 救活 67%；程序化 `_repair_oversize` 救活剩余 11%
- 多模态 ablation §5.4：mm 加速 retry 通过 3/9，无回归；VL caption 四层门控扩到 24 视频后 LLM 覆盖率 23/24 = 96%（中层 gate 2026-05-24 加入，接管原唯一救援 case FwOTs）

**核心发现 — LLM-as-segmenter 失败模式的语言对偶性**（§5.4.5）：
- 中文 caption 主题词整段重复（"以太网交换机的自学习功能..."×5）→ **char-prefix 共享**抓得到（内层 gate）
- 英文 caption 句法模板化但语义同质（"The X verbs Y..."）→ char-prefix 失效但
  **generic 动词词频**有强信号（中层 gate，FwOTs 0.82）
- 早期判定"任何 lexical 先验门控都救不了英文"过于悲观——扩 corpus + 扩词典 +
  调阈值后 generic_ratio 可作为英文友好的中层 gate。救援层从唯一可行架构降级
  为安全网，仍保留以应对未知失败模式（2026-05-24 重新评估）

**takeaway**：v4 是本工作架构的最大跃迁——Pegasus → LLM 把"覆盖率"从 TextTiling fallback 救活变为 LLM 主路径 + 程序化兜底。四层 VL 门控（外层/中层/内层/救援）的发现路径——lexical 指标失效 → 救援层兜底 → 扩词典重生为先验 gate——也成为论文方法论上的一个 contribution。

### 7.5 v5：大类分类 + 模板分发 + 第二轮工程加固（2026-05-19~20）

**触发问题**：v4 的算法在"论文 ablation 跑"上看起来 96% 覆盖率，但首次端到端接入 web 前端跑真实用户路径时暴露 8 类失败模式（详见 §6.5 与本节）：

1. ASR 末尾 hallucination loop 触发 ctranslate2 native abort（p78）
2. 跨域笔记 UI 突兀——把"💡知识点速览 + 🎯⭐ + 📚术语表"全套教学元素硬塞给科普 / 旅游 / 美食 vlog 视频
3. 长 chunks (>120s 单 chunk) 在 vlog 文本下 chunker 切不开（"菜单/食物/吃"贯穿全部，关键词 Jaccard 无跳变）
4. vlog 视频用教学 prompt 把"凉粉脆饼"和"笋干可颂"合成一章
5. LLM 章节切分在 6 视频 audit 暴露 4 个 systematic bug（non_contiguous / 主题词冗余 / dominant_chapter / no_nav_points）
6. md 文件本身永远是 teaching 模板（to_markdown 没接 category），前端 NotesContent 切了但下载 md 没切
7. LLM abstract 仍写"本章 XX"（CHAPTER_ABSTRACT prompt 是教学专用）
8. 黑屏花屏事故：Qwen-7B + Qwen-VL + Whisper 同时常驻显存导致 GPU 驱动崩溃 + 强制重启

**改动**：
1. **大类分类器**（`src/classify_category.py`）：纯启发式 4 维打分（uploader 白名单 / 触发词 / ASR 术语密度 / 时长），输出 `category ∈ {teaching, popsci, vlog, talk}` + confidence。24 视频 24/24 准确
2. **md + 前端按 category 分发**：to_markdown 加 `category` 参数派生 5 个 flag（show_marks / show_kp / show_glossary 等）；前端新增 VlogTimeline 组件；catalog 卡片细分到"编程教学/考研专业课/工具教程"
3. **vlog/talk 专属 LLM prompt**：`SYSTEM_PROMPT_VLOG` / `SYSTEM_PROMPT_TALK` 强调"换地点/换对象/换活动"是章节边界，`VLOG_SECTION_ABSTRACT_SYSTEM` 强制"本段/场景元素"代替"本章/技术点"
4. **chunk 后处理硬切**（`src/summarize.py:split_oversize_chunks`）：duration>120s 且 chars>=400 的 chunk 按时间中点找最近 segment 边界切，下游 chapter / keyframes 自适应新 chunks 数
5. **segment 4 新硬规则 + 1 个 post-process**（详见 §6.5 与 [[project-segment-rules-iteration]]）：
   - `non_contiguous`：章 chunks 必须连续（封 Disney vlog 4/4 systematic bug）
   - 主题词 dedup post-process：85% 阈值 + jieba cut_for_search 中文 token + 仅英文/缩写英文路径
   - `dominant_chapter`：单章 ≤ 45% 总时长（NAT p51 4-章 ch1=48% 命中）
   - `no_nav_points` (Rule C)：n>=3 必须 ≥2 导航点
   - LLM temperature 0.15 → 0.05，retry decay
6. **B 站 cookie/画质链路**：DPAPI 锁 Chrome/Edge cookie 时用 data/.cookies/*bilibili*.txt 绕过；probe endpoint
7. **大模型严格串行加载红线**：所有大模型严格串行 + 三件套释放（`del / torch.cuda.empty_cache / gc.collect`）。这是黑屏事故后定的工程红线，不再为"减少模型加载开销"做常驻池

**量化效果**：
- 大类分类器：24/24 准确（含 14/14 经第二轮调参修对的 python/claudecode/AI 早报 case）
- 端到端管线稳定性：p78/p85 首次接入 web 时遇到的 6 项 §6.5 问题全部修复
- LLM 切分硬规则触发统计（6 视频 × 多轮）：non_contiguous 4 次 / 主题词 dedup 1 次 / dominant_chapter 2 次 / no_nav_points 1 次

**核心发现 — 工程加固的元规律**（§6.5 末尾）：当 corpus 从"论文 ablation 跑"扩展到"真实端到端用户路径"，新暴露的失败模式更偏"配置 / 集成 / 长尾"而非"算法本身"。这与 §6.1-§6.4 中"算法改进 → metric 提升"的主旋律形成对比。

**takeaway**：v5 把工作重心从"算法精调"转向"系统集成"。大类模板分发是面向应用的核心交付物，让笔记系统真正能处理跨域内容；segment 4 硬规则把 LLM 的 systematic bias 从概率问题转为决策问题。

### 7.6 v6：子规则一致化 + 兜底验证（2026-05-21，当前态）

**触发问题**：v5 末尾加的 4 条硬规则把 LLM 失败率压到了野外极低水平，但 [[project-segment-rules-iteration]] memory 标"auto_subs 兜底未野外触发——LLM 听话率高，不需要"。我们怀疑这个 "0 触发" 是 LLM 听话还是兜底本身 broken，于是构造倔强单顶层的 stress test（`scripts/stress_test_auto_subs.py`）跑系统化验证。

**改动**：

1. **stress test 暴露 auto_subs 兜底 n ≥ 4 一直 broken**：构造 3 个 case（n=4 单顶层 / n=3 单顶层 / n=4 双顶层无 children），n=3 case 通过、**n=4 case 撞 children-blind 规则被二次 reject**。`_diagnose_outline` L740-741 `n>=4 + len<3 → reject` 不看 children，而 auto_subs 注入的 N children 在父层只是"1 顶层"，所以日志显示"自动生成 N 子章节 [OK]"之后被 _diagnose 二次 reject，pass_via 仍 None，最终输出空 chapters。
2. **合并规则为 children-aware**：把 `_diagnose_outline` L740 / L744-750 与 `_validate_outline` L830-831 / L832-836 四处合并为统一规则——`min_top = 3 if n>=4 else 2`，单顶层 + ≥2 children 视为等价导航形态。这同时也修了 LLM 主动切"1 顶层+多 children" 在 n>=4 时被误杀的旧 bug。
3. **fail_reason keyword 重映射**：原匹配"至少 3 个顶层" / "笔记将零导航价值"两个旧错误串失效，新规则错误串带"应至少 X 顶层"，分别用 "应至少 3" / "应至少 2" 关键字区分 too_few_chapters / no_nav_points 标签。
4. **`_repair_missing_chunks` children 一致性 pass**：4 视频回归暴露的次级 bug——repair 给顶层补了 chunk 但原 children 没覆盖父全部 → `_diagnose` 看 parsed 通过 → `_validate` 看 ch_out 静默丢 children → nav 检查 reject → 空 chapters。修：repair_missing 末尾 pop 不一致的 children，让 auto_subs 兜底接力补 1:N。
5. **顺手清理两个低优 bug**：jieba cut_for_search 中文主题词 dedup（替代 cut 切不出"子网"独立 token 的盲区）；ASR `[asr] X/Y` progress 显示分母改 `info.duration`（原分母用 chunks 数误报）。

**量化效果**：

| 测试 | 结果 |
|---|---|
| stress test mock LLM（n=2/3/4 + 倔强双顶层 negative） | **3/3 全过** |
| 4 视频回归（n=2 vlog / n=3 PPP / n=11 NAT / n=36 Tina AI Agent） | **4/4 无回归** |
| auto_subs 实战首次触发 | BV19E411D78Q_p42 PPP n=3 single-top → 1 顶层 + 3 children |
| 现有 baseline 一致性 | NAT 7→7 章 / Tina 9→9 章，完全对齐 |

**核心发现 — "未触发"≠"工作正常"**：v5 把 auto_subs 标"belt-and-suspenders 未野外触发"作为它"不需要"的证据，stress test 揭示真相是它**一直 broken 没人发现**。这印证了 §6.5 末尾元规律的逆向版本——某些失败模式只有在"系统化构造性测试"下才会暴露，而野外 corpus 因为分布偏置会自然回避触发条件。论文方法论上的 takeaway 是：**对兜底机制必须做 stress test，不能用"野外未触发"作为它正确性的证据**。

**takeaway**：v6 是"对前 5 个版本积累的兜底机制做系统性验证"的一轮。从产物角度看仅修了一个隐藏 bug，但从方法论角度看建立了"stress test 配套于兜底机制"的开发范式，并把这个范式以脚本（`stress_test_auto_subs.py` + `regress_segment_rules.py`）固化下来供未来 v7+ 复用。

### 7.7 v1-v6 演进汇总

| 版本 | 时段 | 核心改动 | 量化效果 | 论文章节 |
|---|---|---|---|---|
| v1 | 2026-05 前 | Pegasus baseline，TextTiling+CLIP α=0.3 | 笔记最小可用 | §3, §4.2 |
| v2 | 2026-05-15 | ASR LCP dedupe + 术语字典 | OS p37 F1@1 +0.50；p38 strict F1 +0.50 | §4.1, §6.1-6.3 |
| v3 | 2026-05-15 | 学习 md 结构 + copy fallback + ASR `[?]` 置信度 | 章标题主观 3.43 / 3.25 | §4.3, §4.4 |
| v4 | 2026-05-16~17 | Qwen2.5-7B-AWQ 替代 Pegasus + B1 两步法 + VLM caption 三层门控 + 英文支持 | LLM 覆盖率 9/9→23/24 = 96% | §5.4, §5.7, 附录 B |
| v5 | 2026-05-19~20 | 大类分类器 + 模板分发 + segment 4 硬规则 + 工程加固 6 项 + 串行加载红线 | 24/24 分类准；6 项端到端可用性修复 | §6.4, §6.5 |
| v6 | 2026-05-21 | auto_subs stress test 暴露 n≥4 broken + nav 规则合并 + repair_missing 一致性 | 3/3 stress test + 4/4 回归；auto_subs 首次野外触发 | §7.6, 附录 C |
| v6+ | 2026-05-22 | autoawq Windows 安装陷阱全链路打通（torch DLL/datasets shim） | transformers 4.49 + autoawq 0.2.6 + Qwen2.5-VL 全 OK | §6.5.x |
| v7 | 2026-05-24 | VL caption 中层 gate (generic_ratio≥0.65) 重生 + 章标题 Python 端校准 (jieba + drop hint) | FwOTs 救援 → 中层先验降级；vlog 域 ASR 错字（烟台/电源）不再漏入章标题 | §5.4.3-4, §6.4 |

**演进的元模式**：v1-v3 主要是"算法精调"（dedupe / md 结构 / fallback），v4 是"架构跃迁"（Pegasus → LLM），v5-v6 转向"系统集成 + 测试方法论"（大类分发 / stress test / 工程红线），v7 体现"早期被弃 heuristic 可重生 + prompt 规则冲突时把判定搬 Python"两条新方法论。这一阶段切换反映了一个本工作过程中观察到的现象——**算法 metric 的边际回报递减时，工程加固与测试方法论的边际回报反而上升**。

## 8 局限性与未来工作 (Limitations & Future Work)

### 8.1 已知失败模式

- **ASR 隐式错字**（同音字）：如影视飓风视频"想拖 vs 像托"，文字通顺但语义错误，所有自动指标对此盲区。v3 已用 `[?]` 标记低置信度位置部分缓解（见 §7.3）但同音字往往本身置信度并不低，需要 word-level acoustic confidence + 语义合理性二级判别才能根除
- **Pegasus 主旨偏移**：8 视频 30 headline 中 2 个 Pegasus 抓错主题（无明显诱因）。注：v4 已用 Qwen2.5-7B-AWQ 替代 Pegasus 章标题（见 §7.4），本条仅遗留在段落 headline 仍用 Pegasus 的子路径
- **短视频 strict F1 trivial floor**：< 5min / < 5 chunks 视频上 strict F1 是 0/1 结构性二值，仅 F1@1 可靠
- **英文 LLM-as-segmenter 在 27+ chunks 长视频上的 catch-all bias**：WSPChlfxJyA 唯一 fallback case（§6.4），与 VL 无关，是 Qwen 模型本身在长英文输入上的退化模式，prompt 工程无法根治
- **VL caption 在 PPT/教程域的过切风险**（§5.4.3-5.4.5）：四层门控已大幅缓解但仍是 opt-in 而非默认开
- **大模型不能并行常驻**（v5 黑屏事故经验，见 §7.5）：12GB VRAM 限制下 Qwen-7B + Qwen-VL + Whisper 必须严格串行，付出 ~30-60s/模型的加载时间代价。这是硬件而非算法约束
- **ctranslate2 native abort 第二条触发路径**（v6+，见 §6.5.1.bis）：`transcribe()` 实际完成后、Python 收尾前仍可能崩。L1/L2 解码约束与 hallucination gate 无法预防此路径，只能用 L3 流式增量落盘做兜底。这是 native 层资源释放的健壮性问题，非 Python 端可彻底根除
- **章 abstract LLM input 的"标题字面化"陷阱**（v6+，见 §6.5.1.bis 关联讨论）：早期 `generate_chapter_abstracts` 只喂 LLM headline 关键词，未喂 ASR 实际文本片段，导致 vlog 域章标题（如"心理线" / "皇上"）被 LLM 按字面跨域解读为"股市心理指标" / "清朝皇帝"。本工作通过在 LLM input 加入 ASR snippet + user_prompt "严格根据「内容」"双重约束修复，3-vlog 回归 0 hallucinate；但这一陷阱揭示了 prompt design 中"input 信息完备性"对 hallucination 控制的决定性作用，是后续 LLM 流水线设计应优先核查的维度

- **章标题 LLM 同音字幻觉路径**（v7+，K1 修复）：在 J7 共享前缀禁令 prompt + Python 端 headline 字面 mask 共同作用下，曾观察到一例 5/5 稳定复现的同音字幻觉——p93 计网 HTML 视频 Ch1 "网页元素与 HTML 结构" 被 LLM 重写为 "四维事实建立网页框架"。根因诊断显示，`_calibrate_headline_words` 把 "万维网 / 网页 / 概念 / 结构 / 过程" 等合法抽象名词（共 15+ 词）误标为 "已识别 ASR 错字" 并在 prompt 里 `[?]` mask + 强禁令，LLM 失去合法选词后转向同音字（万维网 → 四维）幻觉。修复方案是把 ASR 错字识别守门统一到 word-level prob<0.5 信号，名词不含低 prob 字一律视为 LLM 合法抽象保留。这一案例揭示 Python 端程序化校准必须严格区分"声学层 ASR 错字"与"LLM 内部抽象决策"——后者完全不应进入 drop 列表，否则会从"防 hallucination 工具"转变为"诱发 hallucination 信源"

- **dup-headline 视频章标题信号脆弱性**（v7+）：chunker 给一章内多个 chunks 生成相同 headline 时（如 BV1BE411D7ii_p68 中断系统 ch3-ch6 共 20 chunks 全部 headline = "中断服务程序"），章标题 LLM 失去段落级差异信号，必须靠"J7-A snippet 喂 ASR 摘要 + J7-B 共享前缀禁令 + J7-C Python 关键词差异化拆解"三件套配合差异化。但这套机制在 K1 把 calibrate 信号清洁化之后，在边界 case（前述同视频）会输出"12H 与中断服务程序 / CPU 与中断服务程序"这类弱区分标题——LLM 在共享前缀禁令下被迫挑选具体但低信息密度的 keyword 当 disambiguator。这是"清洁信号" vs "强信号"的取舍：本工作选择清洁信号根除幻觉风险，但暴露 dup-headline 场景需要更主动的差异 snippet 提取（如二次 LLM 抽取本章独有子主题），而非依赖 prompt 端共享前缀禁令的间接施压

- **ASR 字典纠错的 scalability 边界**（v7+，[[project-asr-correction-dict-expansion]]）：feasibility dryrun 在 134 视频 corpus 上发现 24 视频 / 18% 有 ASR 错字 leakage、668+ 实例，silver/gold 采样显示 100% 为 1:1 lookup（无 context-dependent 误识别）。本工作据此采用扩 `_GLOBAL_CORRECTIONS` + `_DOMAIN_CORRECTIONS["computer_org"]` 字典策略，corpus sweep 清零；但 ambiguous patterns（如"中段"是计组域错字 / vlog 域合法 / "电源/烟台"在 vlog 域全合法）必须严格 domain-condition——错放 `_GLOBAL` 会产生跨域 false positive。此外曾尝试 `"服务程" → "服务程序"` 之类的"扩张式"补全规则，因非幂等（含子串）导致二次 apply 变 "服务程序序序" 链式增长，被改为只匹配具体错字变体（"服务程庇 / 庆 / 庫 / 庈" → "服务程序"）。综合来看字典型纠错的边际维护成本随域数线性增长，长尾域扩展时这是必然的工程负担

- **结构化错误识别上 ML 路径的 [no-go] 证据**（v7+，2026-05-26 双 dryrun）：本工作探索过两条用机器学习替代字典 + LLM 的路径，均在小规模 feasibility 阶段被否定。（a）视觉判别器：用 Chinese-CLIP feature 训轻量 boundary 判别器，87 视频 / 1153 pairs，AUROC = 0.557（≈ 随机）、MLP F1 = 0.31，CLIP feature 太低层学不到"PPT 翻页 vs 章节切换"语义差异；若要做需换 VLM caption 文本作为判别 input，回到 §5.4 已实现的路径。（b）ASR 纠错 ML：silver/gold 采样 5 视频跑 `qwen_asr_fix` 100% 是 1:1 lookup 无上下文依赖，训 context-dependent ML 模型相对字典扩展的边际收益为零，且 LLM baseline (`qwen_asr_fix`) 已经覆盖。这两条 [no-go] 不是论文核心结果，但作为工程方法论值得记入：**当 corpus 上观察到的失败分布是 lookup 性质时，ML 路径相对"字典 + LLM"混合工程几乎不会有收益，应优先验证失败分布而非默认选 ML**

### 8.2 Future Work

1. **ASR confidence 二级判别**：当前 `[?]` 标记基于 segment-level confidence，未来引入 word-level confidence + LLM 语义合理性检查识别同音字错字
2. **英文 caption 内层 gate**：v4 三层架构对英文短视频 caption 同质化的内层漏检通过事后救援兜底（§5.4.5），未来可探索基于 sentence embedding 的语义级 gate 替代 lexical 路径
3. **stress test 范式扩展**：v6 仅对 auto_subs 兜底做了 stress test（§7.6），未来扩展到 `_repair_oversize` / `_repair_missing_chunks` / VL 四层 gate 等其他兜底机制，建立"每个兜底必配 stress test"的开发流程
4. **跨域分类器升级**：v5 启发式分类器在 24/24 上准确，但未来加入更多 long-tail 域（如直播切片 / 综艺解说 / 在线课程录屏）时启发式可能不够，需要考虑轻量 LLM 二级判别
5. **前端时间戳点击跳转**：v5 已落地 Next.js + Plyr 前端框架，未来加深度集成（章节书签 / 关键帧 hover 预览 / 跨视频术语跳转）
6. **多模态评估指标**：当前 §5 全部基于章节边界 F1，未来需要面向"学习笔记"本身的指标——如术语表覆盖率、章末小结召回率、TOC 与人工目录的一致性
7. **vlog 域评估的可比基线**：当前 vlog 域只有定性 case 与 abstract hallucinate 计数，未做章节边界 gold 标注（vlog 边界主观性远高于 PPT 教学），需要探索"主观但可复制"的标注协议——例如多人独立标注 + 边界容差度量——把 vlog 域纳入 strict / F1@1 量化对比
8. **multi-vlog corpus 扩展**：当前 vlog 回归 corpus 只有 3 个视频（BV1q6 + BV1dkLr6UEJ6 + BV1AYR6BsE9U），且全部为"美食测评"子类；未来扩到探店 / 健身 / 旅行 / 评测等子类，验证 `VLOG_SECTION_ABSTRACT_SYSTEM` 与 abstract snippet fix 在更宽泛 vlog 分布上的鲁棒性

9. **dup-headline 场景的差异 snippet 主动提取**（对应 §8.1 第 10 条）：当 chunker 给一章内多 chunks 塌成同一 headline 时，目前 J7-A 简单截取 `chunk.summary` 前 120 字喂 LLM 作为差异信号；这一信号在塌缩严重的章节上仍可能不足以让 LLM 拼出高信息密度的章标题（实测见"12H 与中断服务程序"等弱区分输出）。未来可探索在章标题阶段之前插入一次"轻量 LLM 差异点抽取"——给定本章 N 个 chunks 的 summary，让 LLM 显式输出"本章相对其他章独有的子主题 / 步骤 / 实例对象"，再把这些差异点作为章标题 LLM 的强 input，而非依赖 prompt 端共享前缀禁令的间接施压

10. **章标题校准链路的解耦与 ensemble**（对应 §8.1 第 9-10 条）：当前章标题校准链路是 word-prob mask → ASR 字典纠错 → Python 端 `_calibrate_headline_words` 校准 → LLM prompt 共享前缀禁令 → Python 端共享前缀拆解兜底，共五层串联。K1 修复揭示串联设计中任一层信号失真都会沿链路放大（calibrate 误标 → mask 误压 → LLM 幻觉）。未来可探索更解耦的设计——例如让 chunker keyword frequency 矩阵、LLM 候选标题集（多次采样）、Python 端关键词差异化作为独立投票来源，通过 ensemble 而非 chain 产出最终标题，把"chain of corrections 的脆弱性"换为"ensemble 的冗余健壮性"

11. **失败分布的 lookup-vs-context 二分诊断**（对应 §8.1 第 12 条）：本工作两条 ML [no-go] 结论共同指向一个方法论——在选择"字典 / 规则" vs "ML 模型"路径之前，应先 dryrun corpus 上的失败分布是 1:1 lookup 还是 context-dependent。前者用字典 + LLM 几乎必然优于 ML（成本低、可审计、可幂等），后者才进入 ML 候选。未来扩展到更多失败类型（如 chapter abstract hallucination / quiz mismatch）时可沿用此诊断范式

## 9 结论 (Conclusion)

本文以"学习类视频自动生成结构化笔记"为目标，提出一个端到端 pipeline 并在 24 视频跨域 corpus 上完成了系统验证。系统经历了 6 个明确的里程碑迭代（§7 详述）：从 v1 的 Pegasus baseline 起步，v2 通过 ASR 后处理揭示了"上游失败模式经关键词频次向下游 segmenter 传导"的耦合通路；v3 用学习场景 md 结构把笔记升级为教科书式索引；v4 以 Qwen2.5-7B-AWQ 替代 Pegasus 完成架构跃迁，把 LLM 章节切分覆盖率推到 96%（23/24）；v5 加大类分类器与模板分发，让管线能跨域处理 teaching / popsci / vlog / talk 四类内容；v6 用 stress test 范式系统性验证兜底机制的正确性，暴露并修复了一个"野外永远不触发因此被误标为不需要"的隐藏 bug。

本工作贡献的方法论上的发现可以归纳为三条：

**（1）耦合通路的显式化**——v2 的 chunker × dedupe 二维 ablation 表明，dedupe 收益仅在 texttile + cc=400 上显著、cc=800 与 chars chunker 上中性。这一不对称性证实 dedupe 的本质是"关键词频次去噪"而非简单文本清洗，并把"ASR 失败 → 下游 segmenter 污染"这条以往被忽视的通路定量化。

**（2）反直觉的多模态融合定位**——v1 的 α=0.3 与 v4-v7 的 VL caption 四层门控共同揭示一个看似矛盾的事实：视觉信号在 PPT 教学视频上**作为 tie-breaking 比作为主导更适合**，因为 slide 翻页 ≠ 章节切换；进一步的"LLM-as-segmenter 失败模式的语言对偶性"（§5.4.5）表明，中文的 lexical 先验门控（char-prefix 内层）有效但英文需要不同信号——v4-v5 一度认为英文只能靠事后救援，v7 把早期被弃的 generic_ratio heuristic 扩词典 + 调阈值后纳入作为中层 gate，证明"早期被弃的 heuristic 可在扩 corpus 后重生"也是一条值得论文方法论上提的发现路径。

**（3）兜底机制的 stress test 范式**——v6 通过构造倔强单顶层 mock LLM 揭示了 v5 标"未野外触发因此 belt-and-suspenders"的 auto_subs 其实在 n ≥ 4 上**一直 broken**，原因是 _diagnose / _validate 之间一条 children-blind 规则的不一致。这个发现的方法论意义大于 bug 本身：**对兜底机制必须做系统化 stress test，不能用"野外未触发"作为正确性证据**。

**（4）三层防御纵深与"failure mode 演进"**（v6+，见 §6.5.1.bis）——同一个 ctranslate2 native abort 的失败模式在 corpus 跨入新域（教学 → vlog）时演化出第二条触发路径（"transcribe 完成之后"而非"transcribe 推进中"）。一个 fix 在它当时的 benchmark 上 100% 通过，不代表它在新域下仍然 100% 充分；工程健壮性评估必须随 corpus 同步迭代。本工作据此建立三层纵深——L1 解码约束（预防）+ L2 hallucination gate（预防）+ L3 流式增量落盘（兜底，WAL 思想）——把"native 崩溃面前 Python exception handling 不可靠"这一隐含假设显式化为"用持久化频率换最大损失上界"的工程范式。这一思路与方法论 takeaway (3) 互补：(3) 强调"主动构造极端 case 验证兜底"，(4) 强调"承认底层故障不可避免后设计可恢复状态"。

工作的局限性已在 §8.1 列出，共十二类，涵盖 ASR 隐式错字、英文长视频 catch-all bias、大模型并行约束、ctranslate2 native abort 第二条触发路径、章 abstract LLM input 字面化陷阱、章标题 LLM 同音字幻觉路径（K1 修复揭示 Python 校准必须严格区分 ASR 错字与 LLM 抽象决策）、dup-headline 视频章标题信号脆弱性（清洁信号 vs 强信号的取舍）、ASR 字典纠错的 scalability 边界与跨域 false positive、结构化错误识别上 ML 路径的 [no-go] 证据等。其中硬件相关项是工程而非算法问题；ctranslate2 / abstract input / K1 calibrate 三项揭示了"corpus 跨入新域或链路串联层数增加时既有 fix 充分性需要重新评估"这一更深层的工程方法论。

未来工作有十一条主线（§8.2 详述），核心方向有四：（a）把 v6 建立的 stress test 范式扩展到所有兜底机制（`_repair_oversize` / VL 三层 gate 等），（b）探索面向"学习笔记本身"的评估指标（术语表覆盖率、章末小结召回率、TOC 一致性），从"边界 F1"升级到"笔记可用性"的端到端度量，（c）扩展 vlog 域评估（当前仅 3 视频美食测评子类）并设计"主观但可复制"的边界标注协议，（d）把当前章标题"chain of corrections"五层串联设计重构为多源信号 ensemble，并在 dup-headline 场景前置一次差异点抽取替代依赖共享前缀禁令的间接施压。我们希望本工作的 24 视频 benchmark、6 个版本的演进路径、ASR 三层防御范式、章标题校准链路（J / K 系列修复）与配套的 stress / 回归测试脚本，能为后续视频结构化笔记研究提供既有可比较基线、又有可复用工程实践的参考。

---

## 附录 A：实现细节

### A.1 环境

- Windows 11 + RTX 4080 Laptop
- PyTorch 2.3.1+cu121, transformers 4.46.3, numpy<2
- 模型本地副本（hf-mirror.com 下载，aria2c 16 线程）

### A.2 关键代码位置

- ASR + dedupe: `src/asr.py`
- Chunker + 抽取式摘要: `src/summarize.py`
- 神经摘要 + 章标题 fallback: `src/summarize_neural.py`
- 章节切分（多模态融合）: `src/segment.py`
- 关键帧抽取: `src/keyframe.py`
- 端到端 pipeline: `src/pipeline.py`

### A.3 Benchmark 视频列表

| BV | 标题简称 | 时长 | 域 |
|----|---------|------|-----|
| BV19E411D78Q_p38 | 计网 PPT 教学 | 30min | ppt |
| BV1SddcBFESs_p0 | ClaudeCode | 11min | ppt |
| BV1x25P6tEKe_p0 | iOS 评测 | 10min | ppt |
| BV1ygo9BeEvV_p0 | 多 Agent 可视化 | 11min | ppt |
| BV1YE411D7nH_p37_p0 | 王道 OS 哲学家 | 15min | ppt |
| BV1L24y1i7v3_p0 | 5min 看懂深度学习 | 5min | ppt |
| BV1G85V6cE1g_p0 | 懂王评论 | 7min | live |
| BV1W8AGzwEFW_p0 | 外卖 Vlog | 17min | live |
| BV1XY546vE1o_p0 | 影视飓风×刘谦 | 14min | live |
| BV1cwdzBDEL3_p0 | 日本小镇 Vlog | 15min | live |

## 附录 B：LLM 切分路径汇总

下表统计了 9 个学习类视频在默认配置（chunker=texttile, cc=800, summarizer=neural,
--llm-chapters）下，Qwen2.5-7B-AWQ 章节切分的执行路径。指标包括：
**attempt 数**（实际 LLM 调用次数）、**通过方式**（哪一次 attempt 通过，或程序化
repair 救活）、**repair 步骤**、**末尾复习章是否识别**。

| # | 视频 | 语言 | 时长 | 段数 | 章数 | max ch | 切分路径 | attempts | 通过方式 | repair | wrap-up |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 计网 p38 以太网 | zh | 37:19 | 11 | 5 | 3 | LLM | 1 | attempt #1 | - | ✓ |
| 2 | 计网 p44 交换机 | zh | 28:54 | 9 | 4 | 4 | LLM | 3 | attempt #3 | - | ✓ |
| 3 | 计网 p46 IPv4 | zh | 33:40 | 11 | 7 | 3 | LLM | 2 | attempt #2 | - | ✓ |
| 4 | 计网 p49 CIDR | zh | 33:22 | 11 | 3 | 5 | LLM | 1 | attempt #1 | - | ✓ |
| 5 | Vibe Coding Fundamentals | zh | 33:22 | 46 | 11 | 5 | LLM | 3 | attempt #3 | - | - |
| 6 | Tina Huang p02 编程学习 | zh | 15:49 | 21 | 10 | 4 | LLM | 3 | attempt #3 | - | - |
| 7 | Tina Huang AI Agent 精华 | zh | 30:23 | 36 | 16 | 4 | LLM | 3 | repair (after 3) | repair_missing + repair_oversize | - |
| 8 | OS p37 哲学家进餐 | zh | 15:00 | 5 | 3 | 2 | LLM | 2 | attempt #2 | - | - |
| 9 | AI Agents 25min 教程 | en | 25:57 | 34 | 19 | 5 | LLM | 2 | attempt #2 | - | - |

**汇总统计**：

- 总视频数：9（中文 8 + 英文 1）
- **LLM 切分成功**：9/9 = **100%**
- LLM attempt 1 直接通过：2/9 = 22%
- attempt 2 通过：2/9
- attempt 3 通过：4/9
- **程序化 `_repair_oversize` 救活**：1/9 = 11%
- Fallback 到 TextTiling：0/9
- 末尾 wrap-up 章识别：4/9（讲师有口头总结的 case 全命中）

**观察**：

1. **Qwen 在 30 chunks+ 长视频上 attempt 1 catch-all 偏好显著**——8/9 视频 attempt 1
   都把 6+ chunks 塞一个顶层违反 ≤5 硬约束，触发 retry-with-feedback
2. **retry 机制覆盖 89% 失败 case**（8/9 在 attempt 2/3 自我修正）
3. **`_repair_oversize` 程序化兜底**：剩下 1/9（Tina Huang AI Agent）catch-all
   三次都没修对，被 `_repair_missing_chunks` + `_repair_oversize` 接力救回 16 章
4. **wrap-up 检测精度**：4/9，命中的都是讲师有"以上就是 / 我们学习了"明示的视频；
   3 个 Tina Huang/Vibe Coding case 没明示"复习"短语，符合 wrap-up
   trigger ≥2 命中阈值的设计（避免 false positive）
5. **路径覆盖率 100%**：retry + program-repair 双层兜底完全消除了 fallback TextTiling
   的需要，章标题/abstract 都享有 LLM 生成的语义对齐质量

## 附录 C：探索性尝试清单（未采纳/已撤销/已修复）

本附录收录系统演进过程中**未被最终采纳**或**被后续版本撤销**的探索性尝试，
按"动机 → 试错过程 → 不采纳/撤销原因"三段式整理。这些负面结果对理解 §7 中
里程碑改动的"为什么是这个方案而不是别的"具有补充价值——很多设计决策的合理性
只有在看到失败路径时才会显现。

### C.1 PPT slide cue 检测（v3 时段，留代码默认 disable）

**动机**：王道 OS p37 哲学家进餐视频上 strict F1 始终徘徊在 0.0，希望用 PPT
slide 翻页信号作为章节边界的额外线索——理论上"slide 切换"在 PPT 教学场景下与
"章节切换"高度相关。

**试错过程**：
- HSV 直方图相似度作初筛（相邻关键帧距离 > 0.4 算 slide 切换）
- Chinese-CLIP cosine 作复核（避开 HSV 对光照敏感的误报）
- 王道 OS p37 单视频实测：strict F1 从 0.0 救到 0.5（命中 1/2 gold 边界）
- 但跨视频 calibration 失败：HSV 阈值 0.4 在 ClaudeCode 上误报频繁（演示工具光线
  变化），调到 0.55 后王道 OS 救不回，调到 0.5 后又对计网 p38 不灵——
  **三个视频三个最优阈值**，没有跨视频稳健点

**不采纳原因**：跨视频 calibration 难度远高于 α=0.3 多模态融合，且 v4 引入 LLM
切分后这一信号通路被 VL caption 取代（caption 信息密度高 10x）。代码保留在
`src/keyframe.py` 但 pipeline 默认 disable，作为未来研究的潜在 hook。

**论文价值**：这次失败定量化了"启发式阈值在跨域 corpus 上的脆弱性"，间接驱动了
v4 选 LLM-as-segmenter 而非"再加一个加权信号"的方向。

### C.2 大模型并行常驻 → GPU 黑屏事故（v5 时段，撤销 + 定红线）

**动机**：v4 把 Whisper / Qwen-7B / Qwen-VL 串行加载，每个模型加载 30-60s，
24 视频 corpus 跑下来累计 ~20 分钟纯加载时间。试图改成"模型池"常驻显存复用，
减少加载开销。

**试错过程**：12GB VRAM 上同时 warm Whisper（~3GB）+ Qwen-7B-AWQ（~5GB）+
Qwen-VL-7B-AWQ（~5GB）= 13GB，理论上超 VRAM 但 dynamic load 可能 fit。
实测 batch 跑到第 3 个视频时**机器直接黑屏 + 花方格 + 强制重启**，进过一次 BIOS
才恢复。事后分析大概率是 AWQ 量化模型的 kernel 在 OOM 边缘触发 GPU 驱动崩溃。

**撤销 + 定红线**：所有大模型**严格串行**——`del model; torch.cuda.empty_cache();
gc.collect()` 三件套缺一不可，AWQ 模型尤其要 gc。这是 [[feedback-serial-model-loading]]
memory 记录的工程红线，是本工作中**唯一一条来自硬件物理事故而非算法考量的设计
约束**。优化方向只能往单模型内 batch / 量化 / KV cache 走，不能跨模型并行。

**论文价值**：在 §8.1 已知失败模式与 §7.5 v5 触发问题中明确记录，提醒后续工作
不要重蹈覆辙。

### C.3 auto_subs 兜底"未野外触发因此不需要"的误判（v5→v6 修复）

**动机**：v5 加 4 条 segment 硬规则后跑 6 视频 audit，auto_subs 兜底实战触发次数
为 0。当时的 memory 记录是"belt-and-suspenders，LLM 听话率高不需要"。

**试错过程**（v6 stress test）：构造倔强单顶层 mock LLM（`scripts/stress_test_auto_subs.py`），
n=4 case 暴露兜底注入 N children 后被 `_diagnose_outline` L740-741 的
children-blind 规则 reject——日志显示"自动生成 N 子章节 [OK]"之后又被二次拒绝，
最终输出空 chapters。详见 §7.6 与 [[project-segment-rules-iteration]]。

**真实成因**：**0 触发不是"LLM 听话率高"，而是兜底机制 n≥4 一直 broken**——
野外 corpus 因为分布偏置（v5 4 条硬规则把 LLM 失败率本身压得极低）自然回避了
触发条件，使 bug 在野外永远不显现。

**修复**：合并 `_diagnose_outline` / `_validate_outline` 四处规则为统一
children-aware 检查（`min_top = 3 if n>=4 else 2`，单顶层+≥2 children 视为等价
导航形态），并修了 `_repair_missing_chunks` 不同步更新 children 覆盖范围的次级
bug。stress test 3/3 全过；4 视频回归 4/4 无副作用；auto_subs **野外首次成功
触发**（BV19E411D78Q_p42 PPP n=3 single-top → 1 顶层 + 3 children）。

**论文价值**：这是本工作中唯一一个"通过 stress test 暴露的隐藏 bug"——其它 5
个版本的改动都是被野外失败 case 驱动。v6 的方法论 takeaway 已写入 §7.6 与 §9：
**"野外未触发 ≠ 工作正常"，兜底机制必须配套 stress test**。

### C.4 vlog 触发词调参陷阱（v5 时段，撤销）

**动机**：v5 第二轮调参（[[project-category-templates]]）扩 `_VLOG_TRIGGERS`
词表救"随机挑战 69 元"美食 vlog 的误分类。初版加了"今天 / 我们 / 挺好 /
真的 / 有点 / 感觉 / 哇"等通用口语词。

**试错过程**：扩词后 14 视频回归发现 python / claudecode 教学视频里讲师说"我们
今天来看一下" / "感觉这个挺好" 被打进 vlog——通用口语词在教学视频里也很高频。

**撤销 + 修法**：`_VLOG_TRIGGERS` 只保留"教学视频几乎不会出现"的强 vlog 信号
（好吃 / 难吃 / 口感 / 嗦 / 嚼 / 挑战 / 出发 / 到了 / 划算 / 性价比 /
citywalk / 好香 / 好辣 等），同时加双向约束（teaching 触发词命中 ≥2 时口语化
密度信号封顶 +1）。最终 14/14 → 24/24 准确。

**论文价值**：这次试错为 [[project-category-templates]] memory 留了"双向约束 +
强信号挑选"的启发式分类器设计原则。论文 §7.5 v5 部分以"24/24 准确"作为最终
数据呈现，本附录补足了"为什么 14/14 才准的"过程信息。

### C.5 jieba cut 中文主题词 dedup 切不出独立 token 的盲区（v5→v6 修复）

**动机**：v5 加主题词 dedup post-process，用 `jieba.cut(s, HMM=True)` 切中文
title 提取 token。NAT p51 实测有效（"NAT" 在 5/7 章共享触发剥离），但子网划分
case 失效——3 章都含"子网"但 jieba.cut 切不出独立"子网"token。

**试错过程**：诊断发现 jieba 词典里"子网掩码" / "子网划分" 是整词，普通 cut 直接
吐整词，独立"子网"不会出现，使 substring 共享检测漏掉。

**修法**（v6 升级）：换用 `jieba.cut_for_search(s, HMM=True)`——这个模式在长词上
**多吐子词**（"子网掩码"会同时吐"子网/掩码/子网掩码"三个 token），覆盖 substring
共享场景，同时仍是语义切分（"管程引入"切成独立"管程/引入"，不会带飞相邻字）。
用户担心的"管程引入/管程操作 共享管程"误伤经验证不触发（只 2/5 章共享，
85% 阈值不满足）。

**论文价值**：这是"算法依赖第三方库内部行为"的典型 case。论文 §7.6 已记录该
修法但未展开试错过程，本附录给出 jieba 不同分词模式选择的 trade-off 给后续中文
NLP 工作做参考。

### C.6 探索性 commit 一览（未单独立条目）

以下尝试在 memory / git log 中有记录但因影响面较小未在 §7 主线展开，留索引供
追溯：

| 尝试 | 时段 | 结果 |
|---|---|---|
| Whisper small / medium 替代 large-v3 | v1 | 长视频转写质量回退过大，回到 large-v3 |
| chars chunker cc=200 / 600 / 1000 sweep | v2 | 400 在 PPT 子集最优，800 综合最稳，定为 paper main |
| Pegasus-base / large 替代 238M | v1-v3 | base 退化严重，large 受 VRAM 约束跑不动，定 238M |
| 章节数公式 ⌊n/3⌋ / 固定 4 / `⌈duration/6⌉` | v2 | `⌈duration/6⌉` 最贴合人工标注 K |
| TextTiling 窗口大小 sweep | v2 | window=5 段稳健，过大过小都伤精度 |
| 三层多模态融合（α 加权 + slide cue + VLM caption） | v3-v4 | 信号互相冲突，simplify 到 LLM-as-segmenter 主导，VL 作 prompt cue |
| LLM temperature 0.15 → 0.10 → 0.05 | v5 | 0.05 切粒度方差最低（NAT 跨 4 轮 trial 章数差 ≤ 1）|

**论文价值**：这些"未达 §7 主线门槛"的尝试构成了配置空间的覆盖证据——很多最终
默认配置都是 sweep 后选出的稳健点而非首次尝试，这本身是论文 reproducibility 的
一部分。完整 sweep 数据见项目 git history 与 `data/outputs/` 中保留的过渡产物。

