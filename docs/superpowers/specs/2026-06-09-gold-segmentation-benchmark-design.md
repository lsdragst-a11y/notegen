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
  "audio": "data/raw/BV1BE411D7ii_p68_p0.large-v3.m4a",
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
- `draft_source`：草稿来源（如 `llm:vl.chapters`），仅审计用。

## 指标定义（`seg_eval.py`，纯时间制）

### Boundary P/R/F1 @tolerance

- pred 边界落在某未配对 gold 边界 **±tolerance 秒**内算 TP；贪心一对一配对，gold 不重复占用。
- `P = TP/len(pred)`，`R = TP/len(gold)`，`F1 = 2PR/(P+R)`。
- 主容差 **±15s**，附报 **±30s**。

### Pk / WindowDiff

- 把 `[0, duration]` 时间轴按 **1s 网格**离散为 boundary mask（每个 1s 单元末尾是否为段边界）。
- 按标准定义滑窗计算；窗口 `k = round(平均真段长_秒 / 2)`（文献惯例，每视频按 gold 自算；`k` 最小值钳到 1）。
- Pk、WindowDiff 越低越好。

### 退化定义（明确写死，单测覆盖）

| 情形 | Boundary F1 | Pk / WindowDiff |
|---|---|---|
| `pred == []` 且 `gold == []`（皆单段） | **1.0**（P=R=1.0） | **0.0**（两个单段 mask 完全一致） |
| 仅一边为空 | **0.0** | 按定义照常计算（一边全无边界、一边有） |
| `gold` 单段（无边界），pred 有边界 | 照常（R 分母按 len(gold)=0 时 R 定义为 0；F1=0） | 稳定返回：`k` 钳到 1，mask 仅 pred 有边界，给出确定值，不抛异常 |

- 所有除零按上表显式处理（`max(denom, eps)` 不足以表达语义时用条件分支）。

## 跑批协议

`benchmark_segmentation.py`：

- 读 `data/gold/manifest.json` → 逐 video 读 gold.json。
- 复用 ASR cache（`--local`），跑批 **`--quality 360p`**（[[feedback-low-quality-for-eval]]）。
- 评**生产默认 LLM 路径**：`--summarizer neural --chunker texttile --llm-chapters`（与 web 默认一致）。txt vs mm 对比留作 `seg_eval` 可复用的后续 ablation，不在本基准主线。
- 两个条件：
  - **free-K**：不传 `--chapters`，LLM 自适应定 K。
  - **given-K（oracle）**：传 `--chapters = n_segments = len(boundaries_sec) + 1`。
- pred 边界 = chapters.json 中各 chapter 的 `start`（秒），去掉首章 start≈0（与 gold「不含起点」对齐）。

## 产出

### 原始数据 `data/outputs/benchmark_segmentation.json`

逐 video 逐条件（free-K / given-K）记录：pred 边界、gold 边界、F1@15、F1@30、Pk、WindowDiff、domain，并在文件头记录**运行元信息**：

```json
{
  "metrics_version": 1,
  "run_at": "2026-06-09T...",
  "commit": "<git short hash>",
  "model": "Qwen2.5-7B-Instruct-AWQ",
  "provider": "local-vllm",
  "pipeline_args": ["--summarizer","neural","--chunker","texttile","--llm-chapters","--quality","360p"],
  "results": [ ... ]
}
```

- `commit`：跑批时的 git short hash（结果可追溯到代码版本）。
- `model`/`provider`：切分所用模型与来源。
- `pipeline_args`：实际传给 pipeline 的参数。

### 报表 `paper/segmentation_benchmark.md`

- 分档均值表（learning / vlog-OOD / english）× 两条件（free-K / given-K）× 指标（F1@15、F1@30、Pk、WD）。
- free-K vs given-K 对比小节（量化「自适应定 K 的代价」）。
- 供 roadmap #5 白皮书直接引。

## 测试

`scripts/test_seg_eval.py`（纯函数，离线，秒级）：

- Boundary F1：完美命中、全错、部分容差边界命中、贪心不重复配对。
- Pk / WindowDiff：toy 序列手算核对、完美切分=0、near-miss 惩罚小于全错。
- 退化输入：上表三类全覆盖（双空=1.0、单空=0.0、gold 单段稳定返回）。
- `k` 钳位（极短/单段视频）。

## 范围与 YAGNI

- **不做**：web 标注 UI、txt/mm/vl 多路径全量 ablation（指标库可复用，但不在本基准主线）、动态语料、超过 30 的扩容。
- **不改**：老 `eval_segmentation.py` 逻辑（仅标 legacy）、生产 pipeline 行为。
- 英文视频可能仅 ~2 个，作分档参考，样本少不强求统计显著。

## 实施顺序（交 writing-plans 细化）

1. `src/seg_eval.py` + `scripts/test_seg_eval.py`（指标库先行，TDD，离线可验）。
2. `scripts/make_gold_draft.py` → 产出 manifest 候选 + silver 草稿 + 带时间戳转写。
3. 人工校正 gold（用户动作）→ 冻结 `data/gold/manifest.json` + 30 个 `*.gold.json`。
4. `scripts/benchmark_segmentation.py` 跑批 → JSON + `paper/segmentation_benchmark.md`。
5. 首轮结果 review，按需迭代容差/k 约定。
