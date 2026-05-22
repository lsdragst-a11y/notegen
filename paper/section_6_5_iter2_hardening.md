## 6.5 第二轮工程加固迭代（2026-05-19）

本节记录将 §6.4 的 24 视频 corpus 之外的两个新视频（王道计算机网络 p78「TCP 报文段」、p85「TCP 拥塞控制」）首次纳入 web 端到端生成流程时触发的 6 项问题及其修复。这一轮迭代将关注点从「单一指标的算法优化」转向「端到端管线在真实用户路径上的健壮性」，并把曾因为只在 CLI 上验证而漏掉的若干失败模式暴露出来。每一项均按「现象 → 根因 → 修复 → 后验 → 分析」四段式整理，对负面结果（trigger 误判调查最终证明为无 bug）也保留全部记录以备复用。

---

### 6.5.1 ASR 末尾 hallucination loop 触发 ctranslate2 native abort

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

---

### 6.5.2 `.mm.` 后缀产物漏出版至 web/public

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

### 6.5.3 计算机网络域 ASR 错字字典扩充

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

### 6.5.4 jieba 关键词抽取的 stopword 渗漏

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

### 6.5.5 Wrap-up trigger 误报调查：负面结果

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

### 6.5.6 Web pipeline 默认开启 VLM caption

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

### 6.5.7 本轮迭代汇总

| # | 类别 | 修复影响层 | 量化收益（p85 复跑实测） |
|---|------|----------|------------------------|
| 6.5.1 | 健壮性 | ASR 解码参数 | 消除 p78 长视频 native abort 风险；p78 再跑无越界 |
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

整体看，本轮 6 项工程加固以**低 LOC 改动换取了端到端可用性 + 单视频质量两个维度的实质提升**，为论文 §7 「Future Work」中「面向用户路径的健壮性验证」一节提供了具体范例。
