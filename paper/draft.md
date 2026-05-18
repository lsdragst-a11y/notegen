# 基于深度学习的网课视频摘要与笔记生成系统

> 论文 draft，2026-05-15 起草。Markdown 版本用于内容收集与迭代，定稿前转 LaTeX。

---

## 摘要 (Abstract)

学习类视频（网课、技术讲座、考研专业课）是当代知识获取的主要载体之一，但视频媒介与"复习友好"的目标存在结构性矛盾：信息按时间顺序线性铺开，缺乏目录、术语索引与章末小结。本文提出一个端到端 pipeline，将学习类视频自动转换为结构化 Markdown 笔记。系统由四个核心模块组成：（1）多模态章节切分，融合文本 TextTiling 与视觉 Chinese-CLIP 距离，α=0.3 在 10 视频 cross-domain benchmark 上稳健；（2）学习场景专用 markdown 结构，含目录、术语表、章末小结等 5 类元素；（3）ASR 后处理两层修复——基于视频 metadata 的术语字典注入与基于共同前缀长度（LCP）的连续重复段去重；（4）跨域 benchmark 与同时报告 strict / F1@1 的评估方法论。实验显示 TextTiling 相对 chars chunker 在实拍子集上 strict F1 提升 +0.35；ASR 去重在王道 OS 哲学家进餐视频上把 F1@1 从 0.50 提升到 1.00，在计网 p38 上把 strict F1 从 0.25 提升到 0.75。我们进一步识别出 dedupe × chunker 的耦合关系：去重的收益本质上是关键词频次去噪，仅在语义 chunker 上显现，揭示了 ASR 上游失败模式如何通过关键词分布传导到下游分段算法。所有代码、benchmark 标注与实验结果开源。

**关键词**：视频笔记生成；多模态章节切分；ASR 后处理；TextTiling；学习场景

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

本文剩余部分组织如下：§2 综述相关工作；§3 给出系统架构概览；§4 详述四个核心方法模块；§5-6 给出量化评估与 case studies；§7 讨论局限性与 future work；§8 总结。

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
   等）→ BV1S6kQBNEJq 0.36，仍低于经验阈值 0.50，**漏判**
3. **最终采纳两层结构阈值**：
   - **外层 n_chunks > 15**：长视频整体语义密度低，画面 pattern 单一
   - **内层 prefix-run 同质化**：n_chunks ≤ 15 但出现 ≥4 个共享 10 字前缀的连续
     caption 且剩余 chunks ≥ 3 时也降级

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

**最终配置**：`--vlm-captions` 默认 disable；启用时两层自适应：
1. 外层 `n_chunks > 15` → 降级 (4/9 案例)
2. 内层 `max_prefix_run ≥ 4 且 (n - run) ≥ 3` → 降级 (1/9 案例，即 p44)

三个 ablation 字段：`vlm_captions`（用户开了 flag）、`vlm_captions_used`
（实际是否用了 caption）、`vlm_degraded_reason`（降级原因）。9 视频 ablation
实测：**4 used / 5 downgraded（外层 4 + 内层 1）**；启用且切更细的 1/4（OS
哲学家进餐）；降级避开过度切分风险的最显著反转是 EH5jx5qPabU（32 → 9 章），
最显著局部回归修复是 p44（3 次 attempts → 1 次 attempt + 0 repairs）。

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

**完整三层架构**：
1. **外层** `n_chunks > 15` 先验降级——粗粒度防过度切分（4/9 中文 + 1/3 英文）
2. **内层** `max_prefix_run ≥ 4 且 (n - run) ≥ 3` 先验降级——caption 高度同质引发漏 chunks（1/9 中文，p44；英文漏检）
3. **救援** LLM 全失败后事后降级——内层漏检的英文 case 兜底（1/3 英文，FwOTs）

新增 ablation 字段 `vl_rescue_used`，区分"先验门控降级"vs"事后救援降级"
（`vlm_degraded_reason='rescue_after_llm_fail'`）。

**跨语言验证结论**：
- 中文：两层先验门控 9/9 准确（包括 1 次内层捕获 p44）
- 英文：外层正确触发于长视频；内层漏检短视频语义同构 case；救援层兜底
- 三层架构能识别"VL 是不是凶手"——救援层不会拯救与 VL 无关的失败
  （WSPChlfxJyA 的 catch-all 是 [[english-support]] 中 Qwen-EN bias 的独立问题）

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
最后 5 行为 2026-05-18 新增的扩 corpus 案例，进一步验证三层 gate 在更宽分布下的
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
| FwOTs4UxQS4 (en) | 11 | 6 | **救援** | #2 | 内层漏检 → 事后救援唯一命中 case |
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
| 救援触发 | 1/24 |
| 外层 gate 降级 | 6/24 |
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

**(b) 救援层唯一命中 — FwOTs**

FwOTs (n=11 英文) 是三层架构中唯一触发救援的 case。原因：英文 caption 5-8
（"The presenter explains... / The video explains... / The diagram illustrates...
/ The process involves..."）句法模板化但内容同质（都讲"compiling/summarizing/
posts"），LLM 在 word-bag 之上的语义层做主题归并漏 chunks。三种 lexical 指标
（char-prefix、char-Jaccard@.7、word-Jaccard@.2）的 max consecutive run 均不足以
触发先验降级——任何 lexical heuristic 都救不了。事后救援检测到"VL 用了但 3
attempts + repair 全失败"后自动 retry 不带 caption，从原 fallback TextTiling 5
章救回 LLM 6 章。

**(c) 三层架构外的失败 — WSPChlfxJyA**

WSPChlfxJyA (n=27 英文) 是 24 视频中唯一 fallback 到 TextTiling 的 case。三层
架构在该 case 上行为正确：外层 gate 因 n>15 触发，VL caption 未喂；但 sim cue 路径
attempt 2/3 仍持续 missing 9 个 chunks（chunk [10-13, 18-22]），repair_missing
覆盖不全。同视频 mm-only（纯文本）路径表现一致 fallback——证明问题与 VL 无关，
而是 [[english-support]] 章节记录的 **Qwen 在英文 27+ chunk 视频上的 catch-all
模型 bias**，是与本节多模态架构正交的独立失败模式。三层架构能"识别 VL 是不是
凶手"——救援层不触发于该 case（VL 已被外层降级），避免了浪费 retry budget 在
错误方向上。

**采纳的默认配置**（写入 src/pipeline.py 三层）：
1. 外层 `n_chunks > 15` → caption 不喂 LLM
2. 内层 `max_prefix_run ≥ 4 且 (n - run) ≥ 3` → caption 不喂 LLM
3. 救援：LLM 3 attempts + repair 全失败 + VL 在用 → 自动一次 retry without caption

24 视频实测净时间增量 < 2% (6 视频先验降级节省 ~caption 时间，1 视频救援增 ~10s
LLM)，换 96% LLM 切分覆盖率。新增 5 视频未引入任何 fallback / repair / 救援，
全部走 LLM 主路径（1 × attempt 1 + 2 × attempt 2 + 2 × attempt 3）。

## 7 局限性与未来工作 (Limitations & Future Work)

### 7.1 已知失败模式

- **ASR 隐式错字**（同音字）：如影视飓风视频"想拖 vs 像托"，文字通顺但语义错误，所有自动指标对此盲区。需要 ASR confidence + word_timestamps 过滤来缓解
- **Pegasus 主旨偏移**：8 视频 30 headline 中 2 个 Pegasus 抓错主题（无明显诱因），属于模型自身瓶颈
- **短视频 strict F1 trivial floor**：< 5min / < 5 chunks 视频上 strict F1 是 0/1 结构性二值，仅 F1@1 可靠

### 7.2 Future Work

1. ASR confidence 过滤同音字错字
2. 跨语言（英文教学视频）pipeline 验证
3. 前端：Next.js + 视频播放器时间戳跳转
4. ~~扩 benchmark 到 20+ 视频~~（2026-05-18 完成，见 §6.4 24 视频架构泛化）

## 8 结论 (Conclusion)

本文针对学习类视频笔记生成场景提出一个端到端 pipeline，并在 10 视频 cross-domain benchmark 上系统验证了四项设计决策。**多模态章节切分**的 α=0.3 设定揭示了一个反直觉的发现——在 PPT 教学这类 slide 翻页频繁的视频上，视觉信号作为 tie-breaking 比作为主导更适合，因为 slide 边界与话题边界并不一致。**学习场景 md 结构**通过引入术语表、章末小结、TOC 等元素，使笔记从"流水转写"升级为"教科书索引"，是本工作面向应用的核心交付物。**ASR 两层后处理**——尤其是连续重复段去重——揭示了上游 ASR 失败模式如何通过关键词频次传导污染下游分段算法这一被以往工作忽视的耦合通路，且去重对 texttile 显著、对 chars 中性这一不对称性证实了"关键词频次去噪"才是其作用机制。

我们的工作存在几点局限。ASR 同音字错误（如"想拖 vs 像托"）的隐式错字所有自动指标均失效，需要 word-level confidence 过滤作为下一步缓解。Pegasus 主旨偏移在小样本上 30 个 headlines 中观察到 2 例，属于神经摘要模型自身瓶颈，受限于本工作算力规模不便重训。短视频上 strict F1 的结构性 0/1 二值化使评估对长尾视频不友好，方法论上我们已经建议同时报告 F1@1。

未来工作有三条主线：（a）ASR confidence 过滤同音字错字并在 md 中用 `[?]` 标记低置信度位置（已在 2026-05-15 落地，待扩规模评估）；（b）跨语言 pipeline 验证，把当前管道扩展到英文教学视频，重点考察 TextTiling 在英文 ASR 转写上的迁移性；（c）前端展示层，将 markdown 笔记接入 Next.js + 视频播放器，实现真正的"时间戳点击跳转"。我们希望本工作的 benchmark、代码与 ablation 方法论能为后续学习类视频结构化笔记的研究提供可比较的基线。

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

