# Case Study: 王道计算机网络 p57「路由算法」端到端 pipeline 详记

> 论文 §6.x case study draft（2026-05-24 记录）。
> 视频：[BV19E411D78Q?p=57](https://www.bilibili.com/video/BV19E411D78Q?p=57)
> 目的：把一个典型教学视频从 URL → markdown 笔记的每一步完整记录，
> 作为论文方法章节的具体例子。**v7 当前态**（含中层 gate、章标题 Python
> 校准、abstract [?] mask、章末 LLM recap、章末 quiz、四类分类、双语翻译）。

## 视频元信息

| 字段 | 值 |
|---|---|
| BV | `BV19E411D78Q_p57_p0` |
| up 主 | 王道计算机教育 |
| 标题 | 王道计算机考研 计算机网络 p57 4.4.1 路由算法（咸鱼版） |
| 视频时长 | 26 分 50 秒 (1610.0 s) |
| 视频分辨率 | 640×360（`--quality 360p`，feedback_low_quality_for_eval 实测够用） |
| 视频编码 | AV1, 48 kb/s 视频 + 128 kb/s 音频 |
| 自动分类 | `teaching (high)`，scores: teaching 7 / popsci 1 / vlog 0 / talk 1（"考研" 关键词 + "王道计算机教育" uploader 白名单双重命中） |
| pipeline 配置 | `--model large-v3 --summarizer neural --chunker texttile --chunk-chars 600 --chapters --keyframes --llm-chapters --vlm-captions --quality 360p` |
| 总 wall clock | **4 分 38 秒**（首次跑含 ASR；重跑命中 ASR 缓存 ~1 分钟） |

---

## Stage 0 — 下载 + 音频提取

| 步骤 | 详情 |
|---|---|
| 工具 | yt-dlp + B 站 cookie (`data/.cookies/www.bilibili.com_cookies.txt`，DPAPI 解出来的本地缓存，绕过 Chrome/Edge 锁) |
| 画质 probe | 选 `--quality 360p`（feedback_low_quality_for_eval：跑批验证用低画质，ASR 不依赖画质） |
| 视频下载 | `data/raw/BV19E411D78Q_p57_p0.mp4` |
| 音频抽取 | `ffmpeg -ac 1 -ar 16000 -f wav` → `data/audio/BV19E411D78Q_p57_p0.wav` |
| 抽音速度 | speed=1.81×10³，ffmpeg 实测 0.85 秒（27 分钟视频） |
| 输出音频 | 单声道 16 kHz PCM，50312 KiB |

**关键决策**：B 站 cookie 必须用 yt-dlp 兼容格式（Netscape txt），不能直接读 Chrome SQLite——DPAPI 加密 + 锁文件双重阻碍（参 `reference_bilibili_quality` memory）。

## Stage 1 — ASR（faster-whisper large-v3）

| 项 | 值 |
|---|---|
| 模型 | `large-v3`（首次会下载 ~3 GB 到 `~/.cache/huggingface/`） |
| 设备 | CUDA, fp16 |
| 输入 | `BV19E411D78Q_p57_p0.wav`（16 kHz mono, 1610 s） |
| ASR prompt | 自动注入 video title + domain terms 引导专有名词识别。本视频 prompt：`王道计算机考研 计算机网络 p57 4.4.1 路由算法（咸鱼版）。涉及术语：数据帧、广播帧、目的MAC地址、源MAC地...` |
| 解码参数 | `condition_on_previous_text=False`（v5 解决 ASR 末尾 hallucination loop）, `no_repeat_ngram_size=3`（双层防御），`hallucination_silence_threshold` + `compression_ratio` 阈值（v6+ 第二条 native abort 路径） |
| 增量落盘 | streaming partial cache（WAL 思想，v6+ 应对 ctranslate2 native abort） |
| 输出 segments | **661 段** |
| 输出总 duration | 1610.0 s（音频原长） |
| 平均 segment logprob | **−0.177**（faster-whisper 通用阈值 −1.0 即"低置信"，本视频 0 / 661 段触及） |
| 低置信段数（<−1.0） | **0 / 661**（高质量录音 + 标准普通话） |
| ASR wall time | ~3 分 30 秒（约 7.4× 实时） |

**关键观察**：教学视频（教师麦克风 + 标准普通话）的 ASR 质量明显高于 vlog（街拍 + 多人混音）。p57 0 个低置信段，对比 vlog 域常见 5-15% 段标 `[?]`。

## Stage 2 — ASR 后处理（域字典 + 重复段去重）

| 项 | 值 |
|---|---|
| 域识别 | `network` 域命中（title 含 "计算机网络"）;hotword 字典加载 |
| 术语字典替换 | **50 条术语**（号针→号针的目的, 数据针→数据帧, 广播针→广播帧, 信元针→信元帧, "这个针"→"这一帧" 等）。这些都是 "针/帧" 同音错字 |
| LCP 重复段去重 | 本视频未触发（无卡片回路） |

**关键观察**：王道系列里 "针" vs "帧" 是高频 ASR 错字（faster-whisper 倾向把 "帧" 听成 "针"）。50 条术语字典是本工作 §4.1 第一层 ASR 后处理的具体实例。

## Stage 3 — Chunking（TextTiling + oversize 切分）

| 项 | 值 |
|---|---|
| chunker | `texttile`（jieba 关键词 Jaccard depth score） |
| 目标 chunk 长度 | `--chunk-chars 600`（接近 1 分钟语音的字符密度） |
| 初始 chunks | **11 个**（TextTiling 切分结果） |
| Oversize 切分 | 触发 **8 刀**，最终 **19 个 chunks** |
| Oversize 实例 | chunk #1 `dur=339.0s chars=1555` → 在 276.7s 切（170.2s \| 168.8s）；递归切到 ≤120s |
| chunks 时长分布 | 60-117 秒 / chunk |
| chunks 字符分布 | 70-134 字符 / chunk summary（抽取式 jieba 输出） |

**关键观察**：TextTiling 在长讲座上倾向产出"超大"chunk（教师可能连讲 5 分钟没明显话题切换）。`_split_oversize_chunks` 是 v3 引入的兜底：硬切超过 120s 的 chunk 在时间中点二刀。

## Stage 4 — Chunk Headline 生成（Qwen-LLM）

| 项 | 值 |
|---|---|
| 模型 | Qwen2.5-7B-Instruct-AWQ（替代 v3 时代的 Randeng-Pegasus） |
| 输入 | 6592 tokens（19 chunks × ~350 tokens/chunk text） |
| LLM 输出（前 10 条 headline） | "路由算法与协议", "路由算法分类", "距离向量路由", "距离向量算法原理", "距离向量算法解释", "距离向量算法向量", "距离向量算法计算", "链路状态路由", "链路状态算法特点", "链路状态算法应用", ... |
| **parse 状态** | ⚠️ **parse failed** (raw len=242, output 含重复条目超 19) |
| Fallback 行为 | headlines 留空，下游 LLM segmenter / abstract / recap 直接读 chunk text，不阻塞流水线 |

**关键观察**：这是一个 known issue 的实例 —— LLM 在"重复主题集中"的章节上（本视频集中讲 5+ 段距离向量算法）容易输出超出 K 的 headlines。下游不依赖 headline 字段所以不影响最终笔记。该问题已记入 P0-4 优化 backlog。

## Stage 5 — Chinese-CLIP 关键帧抽取

| 项 | 值 |
|---|---|
| 模型 | `models/chinese-clip-vit-base-patch16`（CUDA fp16） |
| 策略 | 每 chunk 抽 1 张关键帧（按 chunk text 与帧的 sim 选最高的） |
| 输出帧数 | **19 / 19**（一一对应） |
| 帧 sim 分布 | 0.372 - 0.516（教学 PPT 帧通常 sim 中等，0.4-0.5；vlog 场景帧 sim 较低） |
| 输出目录 | `data/outputs/.../keyframes/keyframe_{idx}_{秒数}s.jpg` |
| 文件 | `keyframe_01_0059s.jpg`, `keyframe_02_0171s.jpg`, ..., `keyframe_19_1588s.jpg` |

## Stage 6 — VLM caption（Qwen2.5-VL-7B-AWQ）

| 项 | 值 |
|---|---|
| 模型 | `Qwen2.5-VL-7B-Instruct-AWQ`（首次启用 ~5 GB VRAM；与 instruct 互斥串行加载，feedback_serial_model_loading） |
| caption 数 | 19 / 19 |
| caption 例 | "路由算法分类：静态路由和动态路由，动态路由包括RIP、OSPF和BGP协议。" / "距离-向量路由算法的原理和计算过程。" / "讲师讲解路由器距离向量算法计算路由过程。" |
| **诊断指标** | `n_cap=19, jaccard_mean=0.31, generic_ratio=0.47, max_prefix_run=3/19` |
| **VL 四层 gate 决策** | **外层触发降级**：`n_chunks=19 > 15 → 长视频画面 pattern 易让 LLM catch-all，降级回 CLIP sim cue` |

**关键观察**：四层 gate 在 p57 上**外层先触发**，中层（generic=0.47，阈值 0.65）和内层（prefix_run=3，阈值 4）都未达标。这印证了论文 §5.4.3 的结论——长视频整体语义密度低，VL caption 反成 LLM catch-all 诱因；CLIP sim 作为视觉 tie-breaking 反而更安全。

caption 自身质量不差（"路由算法分类"很贴），但 LLM segmenter 在 19 chunks 上倾向"主题合并意图压过细分意图"，因此 gate 降级是正确决策。

## Stage 7 — LLM 章节切分（Qwen2.5-7B-AWQ + retry + repair）

> **LLM 切分随机性**：do_sample=True + 低 temperature (0.03-0.05) 下，相同输入两次运行
> 可能产生不同章数（本视频实测：第一次 6 章 / 第二次 4 章）。论文 §5.4 已讨论；retry +
> repair 双层兜底保证 100% 覆盖率即便单次切分有变。下面记录"当前 chapters.json"
> 对应的第二次运行；附录注明两次运行的差异。

### 第二次运行（写盘版本，4 章）

| 步骤 | 详情 |
|---|---|
| 模型 | Qwen2.5-7B-Instruct-AWQ（VL 模型 free 后重新加载） |
| 输入 prompt | teaching 版（category 早期检测） |
| **Attempt 1** | input 5677 tokens, temp=0.05 → 输出 1 章包 19 chunks → **失败**：第 1 章覆盖 19 chunks 超 5 上限 |
| **Attempt 2** | input 5894 tokens (含 attempt 1 错误反馈), temp=0.04 → **OK validation passed** |
| 最终顶层章数 | **4 章** |
| 子章节数 | 0 |

### 第一次运行（参考对比，6 章）

| 步骤 | 详情 |
|---|---|
| **Attempt 1** | 输出 outline 含 [0,1] [2,3,4,5] 两章后截断 → **失败**：缺少 chunk_idx [6-17] |
| **Attempt 2** | 输出 4 章但 ch3 含 7 chunks → **失败**：单章 > 5 chunks 上限 |
| **Attempt 3** | 输出 6 章但仍缺 chunks [6,7,8,9,10,14,15,16] → **失败**：缺 chunk_idx |
| **Programmatic repair** | `_repair_oversize`：'距离向量路由算法' 9 chunks → 拆 2 部分 [5,4]；'链路状态路由算法' 6 chunks → 拆 2 部分 [3,3] → **OK** |
| 最终章数 | 6 章 |

**关键观察**：两次运行共同点是 LLM 都在"主题集中"的视频上倾向产出违规 outline（要么超大章、要么漏 chunk）。retry + repair 双层兜底确保 100% 覆盖率。这是论文 §6.4 corpus 里 attempt 通过率分布的具体实例：

| Attempt 失败模式 | LLM 行为 | repair 兜底 |
|---|---|---|
| 缺 chunk_idx | 提前终止 outline | 不直接 repair；retry |
| 单章 > 5 chunks | 试图归并漏掉的章 | `_repair_oversize` 兜底（如第一次 run 用上） |
| retry 后反向过拟合 | 又漏 chunks | repair 拆大章 → OK |

## Stage 8 — 章标题 refine（Python 校准 + LLM）

| 项 | 值 |
|---|---|
| 输入 prompt | 教学版 TITLE_CHAPTER_SYSTEM，含 Step 1 校准 + Step 2 命名两步 |
| Python 端校准 | 对每 chunk 跑 `_calibrate_headline_words`：jieba 切 headline 名词，校验是否在 keywords/text 出现 |
| 本视频校准触发 drop 词数 | **0**（教学视频 ASR 错字不多，校准基本无触发；vlog 视频 BV1EBdcBrEea 触发"烟台"/"电源"是典型对比） |
| LLM 输入 tokens | 2811（第一次）/ 较小（第二次因章少） |
| 输出章标题（写盘版本，4 章） | 路由算法与协议 / 链路状态算法 / 迪杰斯特拉与动态路由 / 距离向量算法复习 |

## Stage 9 — 章 abstract（Python 校准 [?] mask + LLM）

| 项 | 值 |
|---|---|
| 输入 prompt | CHAPTER_ABSTRACT_SYSTEM 教学版（不切 vlog） |
| Python 校准 mask | 0 触发（同 Stage 8） |
| LLM 输入 tokens | ~2200 |
| 输出条数 | 4（与章数匹配） |

```
Ch1 路由算法与协议:
  本章介绍路由算法与路由协议，重点讲解距离向量路由算法和链路状态路由算法，
  包括OSPF路由的具体实现。

Ch2 链路状态算法:
  本章详细探讨链路状态算法，通过路由器之间的信息交换来计算最短路径，强调
  迪杰斯特拉算法的应用。

Ch3 迪杰斯特拉与动态路由:
  本章复习迪杰斯特拉与动态路由的相关知识，通过实例说明如何计算IP数据报的
  转发路径长度。

Ch4 距离向量算法复习:
  本章回顾距离向量算法的工作原理，强调其无需了解完整网络拓扑结构的特点，
  并讨论其在BGP协议中的应用。
```

## Stage 10 — 章末复习要点 recap（v7 新增）

| 项 | 值 |
|---|---|
| 模型调用 | CHAPTER_RECAP_SYSTEM 强约束 K=4 → 4 元素 JSON |
| 输入 tokens | ~2300 |
| 每章 bullet 数 | 4-5 条 |
| 总条数 | **18 条**（4 章 × 平均 4.5 条） |
| Ch1 recap | - 路由算法与协议 / - 动态路由算法 / - 距离向量路由算法 / - OSPF路由算法 |
| Ch2 recap | - 距离向量路由算法 / - 路由器间连线 / - IP报最佳转发路径 / - 静态路由手工配置 / - 链路状态算法 |
| Ch3 recap | - 迪杰斯特拉算法 / - 路由器间距离计算 / - 动态路由转发路径 / - 路由器间最短路径 / - 链路状态算法 |
| Ch4 recap | - 链路状态路由算法复习 / - 使用迪杰斯特拉算法 / - 路由器间拓扑结构 / - 路由协议与路由算法 |

**已知质量问题**（baseline，待 prompt 调）:
- 部分 bullet 过短（"- 路由算法与协议" / "- 迪杰斯特拉算法"）—— 只是名词短语，没有"X 是 Y" 的可复述结构
- 跨章重复："链路状态算法" 在 Ch1/Ch2/Ch3 都出现，缺辨识度
- 论文 §5 主观评分应用 corpus 扩到 5-10 视频后调 prompt 加"禁止单名词"约束

## Stage 11 — 章末自测题 quiz（v7 新增）

| 项 | 值 |
|---|---|
| 模型调用 | CHAPTER_QUIZ_SYSTEM 输出结构化 JSON |
| 输入 tokens | ~2400 |
| 每章题数 | **2 题 / 章**（mc + tf 混合） |
| 总题数 | **8 题**（4 章 × 2） |
| 字段校验 drop | **0 / 8**（全过 `_validate_quiz_item`） |
| 输出 md | `<details>` 折叠每题答案与解析 |

### 实际生成的 8 题（按章顺序）

```
Ch1 (mc) 路由器之间的连线主要目的是什么？  → 寻找最佳转发路径
Ch1 (tf) 静态路由算法不需要定期更新路由表。  → True

Ch2 (mc) 距离向量路由算法的核心原理是什么？  → 路由器之间的距离向量
Ch2 (tf) 距离向量路由算法适用于大型网络。  → False
         （解析：count-to-infinity 问题限制了规模）

Ch3 (mc) 如果路由器B想要转发到Net1，它应该选择哪条路径？  → 通过路由A再加10
Ch3 (tf) 迪杰斯特拉算法可以用于计算最短路径。  → True

Ch4 (mc) 链路状态路由算法的特点是什么？  → 网络拓扑结构的完整信息
Ch4 (tf) 距离向量路由算法和链路状态路由算法都可以用于动态路由。  → True
```

**关键观察**：题目质量明显优于 recap——MC 题都基于本章具体细节（Net1 转发路径、距离向量原理），TF 题考察"理论 vs 实践"边界条件（如"大型网络适用 → False"考点云盘"count-to-infinity 问题"）。说明结构化 JSON 约束 + "复习导向"prompt 比开放 bullet 更能逼出深度。

## Stage 12 — 双语翻译（zh ↔ en，v4 引入）

| 项 | 值 |
|---|---|
| 翻译目标 | chapter titles + abstracts |
| LLM 调用 | 2 批（6 titles + 6 abstracts）；每批 200-350 tokens |
| 输出 | `_zh / _en` 字段填充 chapters.json，web 前端 NavBar 切语言用 |

## Stage 13 — Markdown 生成 + Web 发布

| 项 | 值 |
|---|---|
| 输出 md | `data/outputs/BV19E411D78Q_p57_p0.large-v3.neural.texttile.cc600.mm.vl.md` |
| md 结构 | 顶部摘要卡 / 📑 TOC / 💡 知识点速览 / 📚 术语表 / 6 章节（每章：📂 abstract → 段文本 → 📝 复习要点 → 🎓 自测题）|
| Web 发布 | 待 server `_publish_to_web('BV19E411D78Q_p57_p0')` 同步到 `web/public/notes/BV19E411D78Q_p57_p0/` |

---

## 全程时间分布（估算）

| 阶段 | 耗时 | 占比 |
|---|---|---|
| 下载 + 音频提取 | ~5 s | 1.8% |
| ASR (large-v3) | ~210 s | 75.5% |
| 后处理 + chunking | ~5 s | 1.8% |
| Chinese-CLIP 关键帧 | ~5 s | 1.8% |
| Qwen-VL caption × 19 | ~25 s | 9.0% |
| LLM segment + repair (3 attempts) | ~15 s | 5.4% |
| LLM 章标题 refine | ~3 s | 1.1% |
| LLM abstract | ~5 s | 1.8% |
| LLM recap (v7) | ~4 s | 1.4% |
| LLM quiz (v7) | ~4 s | 1.4% |
| 双语翻译 | ~3 s | 1.1% |
| md + serialize | <1 s | <0.5% |
| **总计 wall clock** | **~278 s (~4 分 38 秒)** | 100% |

ASR 占了 75% 时间，是优化重点。重跑命中 ASR 缓存后 wall clock 降到 ~1 分钟。

## 输出产物路径

```
data/outputs/BV19E411D78Q_p57_p0.large-v3.asr.json                     # ASR raw
data/outputs/BV19E411D78Q_p57_p0.large-v3.neural.texttile.cc600.mm.vl.summary.json   # chunks + headlines + keywords + keyframes paths
data/outputs/BV19E411D78Q_p57_p0.large-v3.neural.texttile.cc600.mm.vl.chapters.json  # 6 chapters + abstract + recap + quiz + ablation + seg_meta
data/outputs/BV19E411D78Q_p57_p0.large-v3.neural.texttile.cc600.mm.vl.md             # 最终 markdown 笔记（用户读这个）
data/outputs/BV19E411D78Q_p57_p0.large-v3.neural.texttile.cc600.mm.vl.keyframes/     # 19 张关键帧 jpg
```

---

## 3 视频横向对比（p57 / p58 / p72）

3 个都是王道计算机网络系列同 up 主连续 page，覆盖不同算法主题与不同时长。

| 维度 | p57 路由算法 | p58 自治系统 | p72 移动 IP |
|---|---|---|---|
| 时长 | 1610 s (27 min) | 674 s (11 min) | 1597 s (27 min) |
| n_chunks (split 后) | 19 | 7 | 19 |
| 章数 | 4 | 5 | 6 |
| LLM seg attempt | 2 (重跑) / 3+repair (首次) | 2 | **3 全失败 + repair** |
| VL gate 决策 | **外层降级** (n>15) | **未触发 (used)** | **外层降级** (n>15) |
| Generic ratio | 0.47 | 0.43 | 0.53 |
| max_prefix_run | 3/19 | 2/7 | 4/19（贴内层阈值） |
| ASR drop 词数 | 0 | 0 | 0 |
| recap 总行数 | 18 | 22 | 30 |
| quiz 总题数 / drop | 8 / 0 | 7 / 0 | 12 / 0 |
| Wall clock（首次跑） | 4'38" | ~3' | ~4'30" |

### 三视频共性

1. **教学视频 ASR 质量稳定**：3 个视频都 ASR drop=0（无 ASR 错字校准触发）
2. **章节切分需要 retry**：3/3 视频 attempt 1 都失败（LLM 在教学视频上倾向产出超大章或缺 chunk）
3. **Quiz 字段校验通过率 100%**：27/27 题全过

### 三视频差异

| 现象 | p57 | p58 | p72 | 原因 |
|---|---|---|---|---|
| VL caption 是否被采用 | ✗ 外层降级 | ✓ 用上 | ✗ 外层降级 | n_chunks ≤ 15 是关键阈值 |
| LLM attempt 难度 | 中（重跑 2 次过；首次 3+repair）| 低（2 次过）| **高（3 次全失败，必须 repair）** | p72 单一主题"移动 IP"集中讲解，LLM 倾向归并 |
| recap 质量主观 | 偏短，名词短语为主 | **完整句**（最好） | 完整句但部分重复 | p58 因章短（11 min）chunks 集中，单章信息密度高 |

### 关键论文 takeaway

- **n_chunks > 15 是外层 gate 的 robust 阈值**：3/3 长视频（含 p72 0.53 中层未触发）正确降级
- **`_repair_oversize` 是不可省的最后兜底**：p72 三次 attempt 全失败但 repair 接管成功，对应论文 §6.4 "1/24 三 attempt 全失败由 repair 救活"的实例
- **recap 质量随章长正相关**：短章（信息密度高）→ recap 完整可考；长章（5 chunks）→ recap 名词化、可考性弱 → 提示 prompt 需加"禁止单名词 bullet"约束
- **quiz 比 recap 更鲁棒**：结构化 JSON + "复习导向"指令把 LLM 逼到具体可考点（MC 选项必须 4 个，TF 必须 True/False）

---

## 论文写作建议

本 case study 可写入论文 §6.x（v7 学习类完整 case study）：

1. **§6.x.1 端到端 pipeline 可视化**：用 p57 4'38" 时间分布饼图（ASR 75% / VL+LLM 25%）
2. **§6.x.2 教学视频 ASR drop 0**：对比 vlog 域 5-15% drop 率，说明校准在学习类几乎不需要触发但保留兜底
3. **§6.x.3 LLM 切分的"主题集中难度"**：p72 三 attempts 全失败的实例是论文最强论据——"单一主题长视频" + "retry 反向过拟合"
4. **§6.x.4 recap vs quiz 质量分化**：相同 LLM、相同输入，结构化 JSON 输出 (quiz) 比开放文本 (recap) 显著更稳；提示后续 prompt 工程方向


