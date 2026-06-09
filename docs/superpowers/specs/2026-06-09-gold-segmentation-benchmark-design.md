# 30 视频 Gold 切分基准（Segmentation Gold Benchmark）设计

日期：2026-06-09
状态：设计已与用户对齐，待评审 → writing-plans

## 背景与目标

当前章节切分评估只有 `scripts/eval_segmentation.py`：11 视频、gold 内联在脚本里、按 **chunk 序号**标、评的是**旧 TextTiling+alpha** 路径（`ablation.multimodal_boundaries`），且**强制 K = gold 章数**（把正确章数喂给模型）。它无法衡量当前生产用的 **LLM 自适应切分**，gold 也随 chunker/chunk_chars 变化而失效。

本项目建立一个**标准化、冻结、可复现**的 30 视频 gold 切分基准，作为：
1. 衡量当前 LLM 切分路径在人工 gold 上的边界准确度；
2. roadmap #4「章节切分混合系统」的**量化标尺**（改完能对比收益）；
3. roadmap #5 技术白皮书的评测数据来源。

承接 [[project-roadmap-2026-06-09]] 第 2 项、[[project-appendix-b-aggregator]]、[[project-corpus-status-2026-05-26]]。

## 关键决策（已与用户确认）

| 维度 | 决策 |
|---|---|
| gold 单位 | **时间戳（秒）**，chunker 无关，可直接评 LLM 时间轴路径 |
| K 协议 | **free-K 为主**（系统自适应定 K，同生产）+ **given-K oracle** 参考（拆解「该切几章」与「边界放哪」两类误差） |
| 指标 | **Boundary P/R/F1@容差 + Pk + WindowDiff** |
| 语料 | 学习为主（~22）+ 少量 Vlog（~6）+ 英文（~2），共 **30**；主指标只汇总 learning 子集，Vlog/英文分档作 OOD 参考 |
| 标注 | **半自动**：LLM 输出作 silver 草稿 → 人工校正 |
| 架构 | **B**：拆出可复用指标模块 + 独立 gold 文件 + 跑批脚本 |
| 数据集 | **冻结 manifest**（`data/gold/manifest.json`），benchmark 读 manifest 决定集合，**不动态扫目录** |

**Gold 权威性声明**：`data/gold/*.gold.json` 中经人工校正的 gold 是**唯一权威**。LLM silver 草稿仅为标注辅助（降低纯手标工作量），不具任何权威性；`draft_source` 字段仅作审计追溯。标注时草稿边界附近的原始转写 snippet 会**独立列出**，要求标注者据原文判断，避免被草稿锚定。

## 组件与边界

```
src/seg_eval.py                    纯函数指标库（无 IO）。输入输出皆为「秒为单位边界 list + 视频时长」。
                                   #4 混合系统可直接 import 复用。
data/gold/manifest.json            冻结的 30 视频清单（权威集合定义）
data/gold/<video_id>.gold.json     每视频独立 gold（时间戳边界 + 元信息）
scripts/make_gold_draft.py         半自动：扫候选 → 出 silver 草稿 + 带时间戳转写 → 协助构建 manifest 与 gold 草稿
scripts/benchmark_segmentation.py  跑批：读 manifest，free-K + given-K，调 seg_eval，出 JSON + md 报表
scripts/test_seg_eval.py           指标库单测（toy 用例手算核对 + 退化情形）
scripts/eval_segmentation.py       标注为 legacy，保留（旧 TextTiling 数据可复现），不删不改逻辑
```

**模块边界**：`seg_eval.py` 是纯函数、无文件/网络/subprocess 依赖，因此可单测、可被 #4 直接调用；跑批逻辑（pipeline 调用、ASR cache、文件读写）全在 `benchmark_segmentation.py`，不混入指标库。

## 数据格式

### manifest.json（冻结集合）

```json
{
  "schema_version": 1,
  "created": "2026-06-09",
  "description": "frozen 30-video segmentation gold benchmark set",
  "videos": [
    {"video_id": "BV1BE411D7ii_p68_p0", "domain": "learning", "gold": "data/gold/BV1BE411D7ii_p68_p0.gold.json"}
  ]
}
```

- benchmark **只**遍历 manifest.videos，集合不随本地 `data/raw`/`data/outputs` 变化而漂移。
- `make_gold_draft.py` 可扫目录**协助**初次构建 manifest（列候选、标 domain、报凑不满 30 的缺口），但一旦 manifest 提交即冻结；改动集合需显式决策（必要时 bump `schema_version`）。
- `domain` ∈ `{learning, vlog, english}`。

### gold.json（每视频）

```json
{
  "schema_version": 1,
  "video_id": "BV1BE411D7ii_p68_p0",
  "local_source": "data/raw/BV1BE411D7ii_p68_p0.mp4",
  "duration": 2705.0,
  "domain": "learning",
  "label": "王道计组 p68 中断系统",
  "boundaries_sec": [364.9, 773.0, 1190.8, 1515.5, 1935.8, 2308.7],
  "n_segments": 7,
  "annotated_by": "human",
  "draft_source": "llm:vl.chapters",
  "notes": ""
}
```

- `boundaries_sec`：**段开始时间**，升序，**不含**视频起点 0 与片尾。
- 不变量：`n_segments == len(boundaries_sec) + 1`。
- `local_source`：跑 pipeline 用的**本地媒体路径**（视频或音频）。命名用 `local_source` 而非 `audio`，因为生产默认路径含 keyframes/VLM 视觉信号，**纯音频文件不足以跑视觉路径**——benchmark 若评生产默认路径，须指向带画面的视频源。
- `draft_source`：草稿来源（如 `llm:vl.chapters`），仅审计用。

## 指标定义（`seg_eval.py`，纯时间制）

### Boundary P/R/F1 @tolerance

- TP = pred 与 gold 之间在 **±tolerance 秒**内的**最大一对一匹配数**。每个 pred、每个 gold 至多匹配一次。
- **匹配算法（写死，避免 nearest-greedy 漏配）**：pred、gold 各自升序排序后，用双指针做 **earliest-compatible** 匹配——遍历 gold（i）与 pred（j）两指针：
  - 若 `pred[j] < gold[i] - tol`：该 pred 无法再匹配任何后续 gold（gold 递增），`j++` 丢弃；
  - 否则若 `pred[j] <= gold[i] + tol`：命中，TP++，`i++; j++`；
  - 否则（`pred[j] > gold[i] + tol`）：该 gold 无 pred 可配，`i++`。

  对一维点集 + 对称容差窗口，该 earliest-compatible 双指针**等于最大二分匹配**。**禁止**实现成「每个 pred 取最近 gold」的 nearest-greedy（会在边界密集时少算 TP）。单测必含一个 nearest-greedy 会漏配、双指针能配满的用例。
- `FP = len(pred) - TP`，`FN = len(gold) - TP`。
- `P = TP/len(pred)`，`R = TP/len(gold)`，`F1 = 2PR/(P+R)`。
- 主容差 **±15s**，附报 **±30s**。

### Pk / WindowDiff（离散规则写死，保证可复现）

- **单元化**：`n = ceil(duration)`，得到 `n` 个 1s 单元，索引 `0 .. n-1`。
- **边界映射（写硬，after-semantics 对齐 nltk）**：每个边界 `b`，先丢弃 `b <= 0` 或 `b >= duration`（起点/片尾不是内部边界），再 `u = floor(b)`，保留 `1 <= u < n`，置 **`B[u-1] = 1`**。语义：边界落在单元 `u-1` 与单元 `u` 之间（= 单元 `u-1` 之后），与 nltk boundary-string「位置 j 之后有边界」一致。同一位置多边界去重为 1。
  - **为何 `u-1` 而非 `u`**：若写 `B[u]=1`（「单元 u 起始处」语义）再用 nltk 的 `B[i:i+k]` 计数，mask 相对 nltk 约定整体右移 1 位，窗口刚跨边界时会错算（edge off-by-one）。`B[u-1]` 让 mask 直接就是合法 nltk 输入。
- **窗口** `k = max(1, round(平均真段长_单元 / 2))`，平均段长 = `n / (len(gold)+1)`，每视频按 gold 自算；算出后 clamp 到 `[1, n]`。**单段 gold（gold=[]）也走同一公式**（= `round(n/2)`），不特殊钳到 1。
- **滑窗（nltk 规范）**：`positions = n - k + 1`，`i = 0 .. n-k`（即 `range(n-k+1)`，**修正草稿里 `n-k-1` 的 off-by-one**）。WindowDiff 比较窗口 `B[i:i+k]` 内 ref/hyp 边界计数差（unweighted: `min(1, |Δ|)`）、Pk 比较该窗口内「是否有边界」的异同，均按 nltk 标准定义。clamp 后 `positions >= 1` 恒有窗口；仅当 `duration <= 0` 致 `n` 退化时按 `0.0` 兜底。
- **实现来源**：优先复用 `nltk.metrics.segmentation.pk` / `windowdiff`（若环境已装）作为权威实现，否则按上述约定 vendored 实现，并在单测中与 nltk（或手算）对齐，钉死 off-by-one。
- Pk、WindowDiff 越低越好。

### 退化定义（明确写死，单测覆盖）

| 情形 | Boundary F1 | Pk / WindowDiff |
|---|---|---|
| `pred == []` 且 `gold == []`（皆单段） | **1.0**（P=R=1.0） | **0.0**（两个单段 mask 完全一致） |
| 仅一边为空 | **0.0** | 按定义照常计算（一边全无边界、一边有） |
| `gold` 单段（无边界），pred 有边界 | 照常（R 分母按 len(gold)=0 时 R 定义为 0；F1=0） | `k` 仍按同一公式算（= `round(n/2)`）再 clamp 到 `[1, n]`；`positions = n-k+1 >= 1` 恒有窗口，得确定值，不抛异常（**不**特殊钳到 1） |

- 所有除零按上表显式处理（`max(denom, eps)` 不足以表达语义时用条件分支）。

## 跑批协议

`benchmark_segmentation.py`：

- 读 `data/gold/manifest.json` → 逐 video 读 gold.json → 用 `local_source` 跑 pipeline（`--local`），复用已有 ASR cache。
- **画质口径**：`--quality` 在 `--local` 模式下被忽略（仅 URL 下载模式生效，见 `worker_tasks.py:106`、`pipeline.py`），故 benchmark **不声明画质控制**——以 manifest 冻结的 `local_source` 文件本身为准（要 360p 则在准备 local source 时预降采样，不靠运行时 flag）。注：[[feedback-low-quality-for-eval]] 的 360p 偏好针对 URL 模式跑批，本基准走冻结本地源，不适用。
- **pipeline 参数与 web worker 完全对齐**（`worker_tasks.py:_build_cmd`）。固定 flags：
  ```
  --local --chunker texttile --summarizer neural --keyframes --llm-chapters --vlm-captions
  ```
  即评的是**真实生产默认路径**（含 keyframes/VLM 视觉信号，会影响切分），不是裁剪过的纯文本路径。
- **`chunk_chars` 按视频时长自适应**（与 worker 一致，**非固定 800**）：worker 不用 CLI 默认值，而是调 `SC.adaptive_chunk_chars(dur)`（`worker_tasks.py:118-127` / `service_common.py:34`）——`dur<600s→400`、`600≤dur<1500s→600`、`dur≥1500s→800`。benchmark 须对每个视频用 `gold.duration` 走同一函数算出 `chunk_chars` 再传 `--chunk-chars`，否则切分粒度与生产不符。每视频实际用的 `chunk_chars` 记入结果行（见 §产出）。
  - **预检（fail-fast）**：因 `chunk_chars` 全靠 `gold.duration`，stale gold（时长写错）会静默跑偏粒度而无报错。跑批启动先对所有 manifest 视频用 `SC.probe_duration(local_source)`（ffprobe）校验 `gold.duration`，偏差超阈值（`> max(30s, 5%)`）即中止并报哪个视频；ffprobe 失败（返回 0）则跳过该校验不阻断。
- 两个条件：
  - **free-K**：传 **bare `--chapters`**（无数值，与 worker 一致）→ LLM 自适应定 K；LLM 失败时仍能走 TextTiling fallback 出章节。
  - **given-K（oracle）**：约束 LLM 章数 = `n_segments = len(boundaries_sec) + 1`。
- **关键实现前提（given-K 当前不生效，必须先补）**：`_do_llm_chapters` 调 `segment_hierarchical(...)`（`pipeline.py:1215`）**未传 target K**——现在 `--chapters N` 只在 LLM 失败 fallback TextTiling 时才约束章数（`segment_llm.py`）。实现本基准前须给 `segment_hierarchical` 增加**可选 `target_chapters` 参数**并从 CLI（如 `--chapters N` 的数值形态）透传：**生产默认不传**（保持 free-K 自适应），**仅 benchmark given-K 传**。这是 free-K 与 given-K 能真正区分的前提。
- pred 边界 = chapters.json 中各 chapter 的 `start`（秒），去掉首章 `start`（≈0，与 gold「不含起点」对齐；阈值在 plan 阶段钉死，如 `< 1.0s` 视为起点）。
- **产物快照（free-K/given-K 同 stem 会互相覆盖）**：`_output_stem`（`pipeline.py:469`）不编码 `--chapters` 数值或 condition，故同视频两条件写同一个 `*.chapters.json`、后跑覆盖先跑。跑批须**每个 condition 跑完立刻读 pred**，并把该 chapters.json 快照到 condition 专属路径（如 `data/outputs/benchmark/<video_id>.<condition>.chapters.json`）。主结果（pred 边界）已落 benchmark JSON、不依赖最终 chapters.json；快照仅为 debug/replay 方便。

## 产出

### 原始数据 `data/outputs/benchmark_segmentation.json`

逐 video 逐条件（free-K / given-K）记录每个容差下的 **TP/FP/FN/P/R/F1**（@15、@30）、**Pk**、**WindowDiff**，外加 **pred_n_segments**、**gold_n_segments**、**k_error**（= `pred_n_segments - gold_n_segments`，带符号）、**chunk_chars**（该视频自适应算出的值，复现关键），以及 pred/gold 边界、domain。`k_error` 与 free-K↔given-K 的指标差一起，量化「自适应定 K 的代价」。每行形如：

```json
{
  "video_id": "...", "domain": "learning", "condition": "free-K",
  "chunk_chars": 800,
  "pred_boundaries_sec": [...], "gold_boundaries_sec": [...],
  "pred_n_segments": 8, "gold_n_segments": 7, "k_error": 1,
  "tol15": {"tp": 5, "fp": 2, "fn": 1, "P": 0.71, "R": 0.83, "F1": 0.77},
  "tol30": {"tp": 6, "fp": 1, "fn": 0, "P": 0.86, "R": 1.0, "F1": 0.92},
  "pk": 0.18, "windowdiff": 0.21
}
```

文件头记录**运行元信息**：

```json
{
  "metrics_version": 1,
  "run_at": "2026-06-09T...",
  "commit": "<git short hash>",
  "model": "Qwen2.5-7B-AWQ",
  "provider": "local",
  "static_pipeline_args": ["--local","--chunker","texttile","--summarizer","neural","--keyframes","--llm-chapters","--vlm-captions"],
  "chunk_chars_rule": "adaptive_chunk_chars(duration): <600s->400, <1500s->600, else 800",
  "chapters_arg": {"free-K": "--chapters (bare)", "given-K": "--chapters <n_segments>"},
  "results": [ ... ]
}
```

- `commit`：跑批时的 git short hash（结果可追溯到代码版本）。
- `model`/`provider`：切分所用模型与来源。
- `static_pipeline_args`：所有视频共用的固定 flags（与 `worker_tasks.py:_build_cmd` 一致；**不含** `--chunk-chars` 与 `--chapters`，二者逐视频/逐条件变化）。
- `chunk_chars_rule`：自适应规则（实际值逐视频记在结果行的 `chunk_chars`）。
- `chapters_arg`：两条件下 `--chapters` 的形态（bare vs 数值）。

### 报表 `paper/segmentation_benchmark.md`

- 分档均值表（learning / vlog-OOD / english）× 两条件（free-K / given-K）× 指标（F1@15、F1@30、Pk、WD）。
- free-K vs given-K 对比小节（量化「自适应定 K 的代价」）。
- 供 roadmap #5 白皮书直接引。

## 测试

`scripts/test_seg_eval.py`（纯函数，离线，秒级）：

- Boundary F1：完美命中、全错、部分容差边界命中、贪心不重复配对。
- Pk / WindowDiff：toy 序列手算核对、完美切分=0、near-miss 惩罚小于全错。
- 退化输入：上表三类全覆盖（双空=1.0、单空=0.0、gold 单段稳定返回）。
- `k`/positions 边界情形（极短视频、单段 gold、`k >= n`）：均稳定返回、不抛异常。

## 范围与 YAGNI

- **不做**：web 标注 UI、txt/mm/vl 多路径全量 ablation（指标库可复用，但不在本基准主线）、动态语料、超过 30 的扩容。
- **不改变生产默认行为**：老 `eval_segmentation.py` 逻辑仅标 legacy（不删不改）；生产 pipeline 默认路径行为不变——新增的 `target_chapters` 仅 benchmark given-K 显式传，默认 `None` 时切分逻辑与现状零差异。
- 英文视频可能仅 ~2 个，作分档参考，样本少不强求统计显著。

## 实施顺序（交 writing-plans 细化）

1. `src/seg_eval.py` + `scripts/test_seg_eval.py`（指标库先行，TDD，离线可验）。
2. **给 `segment_hierarchical` 加可选 `target_chapters`** + CLI `--chapters N` 数值形态透传（生产默认不传，benchmark given-K 才传）；改动需保证 bare `--chapters`（free-K）行为不变。加最小单测验证「传 target_chapters 时 LLM 被约束、不传时自适应」。
3. `scripts/make_gold_draft.py` → 产出 manifest 候选 + silver 草稿 + 带时间戳转写。
4. 人工校正 gold（用户动作）→ 冻结 `data/gold/manifest.json` + 30 个 `*.gold.json`。
5. `scripts/benchmark_segmentation.py` 跑批（free-K + given-K）→ JSON + `paper/segmentation_benchmark.md`。
6. 首轮结果 review，按需迭代容差/k 约定。

> **风险提示**：评生产默认路径含 `--vlm-captions`，30 视频 × 2 条件跑批 GPU 耗时显著（VLM + LLM 串行，见 [[feedback-serial-model-loading]]）。given-K 复用 free-K 已有 ASR/VLM cache 可省一半重算；plan 阶段需明确 cache 复用策略与预估时长。
