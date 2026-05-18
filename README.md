# NoteGen — 学习类视频结构化笔记生成

输入一个视频链接（B 站 / YouTube / 本地文件），自动产出带时间戳跳转的结构化 Markdown 学习笔记：TOC、按章节组织的知识点摘要、术语表、章末小结、关键帧、中英双语字段。

本项目同时是一篇本科毕业论文/课程项目的实证 codebase，论文 draft 在 `paper/draft.md`，24 视频 cross-domain benchmark 在 §6.4。

## 特性

- **多模态章节切分**：文本 TextTiling（jieba 关键词 Jaccard 距离 + depth score）与视觉 Chinese-CLIP 相似度融合，α=0.3 默认。在新方案中视觉信号升级为 Qwen2.5-VL-7B caption 自然语言喂给 segment LLM，并由**三层自适应 gate** 防止 PPT 教学视频中 slide flip 误判
- **ASR 后处理两层修复**：基于视频 metadata 自动构建术语字典 + 基于 LCP 的连续重复段去重（处理 faster-whisper "卡片回路"失败模式）
- **学习场景专用 md 结构**：5 类元素——顶部摘要卡、HTML 锚点 TOC、按章节组织的知识点速览、跨段投票术语表、抽取式章末小结
- **双语输出**：ASR 后验校正 lang，Qwen 翻译填 `_zh`/`_en` 字段，前端 toggle 切换
- **程序化 robust 化**：LLM 章节切分 3 attempts retry-with-feedback + `_repair_oversize / _repair_missing` 兜底，最终 fallback TextTiling
- **评估闭环**：10 视频 strict / F1@1 章节切分 benchmark + 24 视频 mm.vl 架构泛化（96% LLM 切分覆盖率）

## Pipeline

```
URL → 下载 (yt-dlp) → 抽音频 (ffmpeg 16kHz mono)
    → ASR (faster-whisper large-v3) → 后验 lang 校正 + 术语词典 + LCP 去重
    → 字符 chunker / TextTiling
    → 关键帧抽取 (Chinese-CLIP) + 可选 VLM caption (Qwen2.5-VL-7B-AWQ)
    → 章节切分 (Qwen2.5-7B-AWQ 三层 gate)
    → 章节标题/摘要 + 双语翻译
    → 学习场景 md 渲染（TOC / 术语表 / 章末小结）
```

## 当前状态

| 模块 | 状态 |
|------|------|
| ASR + 后处理 | ✓ 落地 |
| TextTiling / chars chunker | ✓ 双 chunker 在 benchmark 上同时报告 |
| 神经摘要 (Pegasus) | ✓ 老路径保留，`--llm-chapters` 默认跳过 |
| LLM 章节切分 (Qwen2.5-7B-AWQ) | ✓ 三层 gate + retry + repair + fallback |
| 多模态融合（CLIP-sim cue） | ✓ |
| VLM caption (Qwen2.5-VL-7B-AWQ) | ✓ 三层 gate（外层 n>15 / 内层 prefix_run / 救援） |
| 中英双语 | ✓ ASR 后验校正 lang + Qwen 翻译 |
| 学习场景 md 结构 | ✓ TOC / 术语表 / 章末小结 / 知识点 / 摘要卡 |
| 关键帧抽取 | ✓ 每章 1 帧 |
| Next.js 前端 demo | ✓ 双语 toggle / lightbox / 时间戳跳转 |
| 论文 §1-§8 + 附录 A/B | ✓ Markdown draft 完成，定稿前转 LaTeX |
| 24 视频 mm.vl benchmark | ✓ `scripts/aggregate_eval.py --mode section6-4` 一键刷 |

## 快速开始

### 环境

- Windows 11 + NVIDIA GPU（已在 RTX 4080 Laptop / 12GB VRAM 验证）
- Python 3.10
- ffmpeg（PATH 中可调用）
- 浏览器登录态供 yt-dlp 借 cookies（B 站 / YouTube 反爬）

### 安装

```powershell
# 1. 创建 venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. 装依赖
pip install -r requirements.txt

# 3. 模型本地副本（默认从 hf-mirror.com 下载到 models/）
#    Qwen2.5-7B-AWQ / Qwen2.5-VL-7B-AWQ / faster-whisper-large-v3 /
#    chinese-clip-vit-base-patch16 / Randeng-Pegasus-238M-Summary-Chinese
#    见 paper/draft.md 附录 A.1
```

### 跑一个视频

```powershell
# 默认配置：TextTiling + LLM 切分 + 关键帧 + VL caption 三层 gate + 双语
.\.venv\Scripts\python.exe src/pipeline.py "https://www.bilibili.com/video/BV1xxxx" `
    --summarizer neural --chunker texttile --chunk-chars 800 `
    --chapters --keyframes --mm-alpha 0.3 `
    --llm-chapters --vlm-captions
```

输出在 `data/outputs/<video_id>.large-v3.neural.texttile.mm.vl.md`。

### 批量跑

复用 `scripts/run_5_new_videos.py` 模板，改 `VIDEOS` 列表。脚本带 retry-once 兜底（ASR 释放阶段偶发 Windows STATUS_FATAL_APP_EXIT，cache 命中后再跑一次绕过）。

## 目录结构

```
notegen/
├── src/
│   ├── pipeline.py          串联入口
│   ├── download.py          yt-dlp + ffmpeg
│   ├── asr.py               faster-whisper + LCP dedupe + 术语修正
│   ├── summarize.py         chars/TextTiling chunker + 抽取式摘要
│   ├── summarize_neural.py  Pegasus 摘要（旧路径）
│   ├── segment.py           α-fused 章节切分（旧路径，TextTiling depth score）
│   ├── segment_llm.py       Qwen LLM 切分 + retry + repair + fallback
│   ├── keyframe.py          Chinese-CLIP 关键帧选择
│   └── caption_vl.py        Qwen2.5-VL caption + 三层 gate
├── scripts/
│   ├── aggregate_eval.py    论文表自动生成（appendix-b / mm-compare / section6-4）
│   ├── eval_*.py            各类评估脚本（strict/F1@1、α sweep、dedupe ablation 等）
│   ├── run_5_new_videos.py  batch template（含 retry-once）
│   └── prepare_web_demo.py  把跑好的视频导出到 web/public/notes/
├── paper/
│   ├── draft.md             论文主体（§1-§8 + 附录 A/B）
│   ├── appendix_b.md        LLM 切分路径表（aggregate_eval 自动生成）
│   ├── mm_ablation.md       §5.4 多模态 ablation 对比表
│   └── section_6_4_auto.md  §6.4 24 视频 corpus auto-aggregated
├── web/                     Next.js 前端 demo（双语、lightbox、时间戳跳转）
├── server.py                简易 FastAPI 后端（跑 pipeline 给前端轮询进度）
├── data/                    （gitignored）raw mp4 / audio wav / outputs JSON
├── models/                  （gitignored）本地模型副本，~18GB
└── configs/                 yaml 配置
```

## 评估与论文

论文 draft 在 `paper/draft.md`，结构：

| §  | 主题 |
|----|------|
| 1  | 引言 / 任务挑战 / 四项主要贡献 |
| 2  | 相关工作（视频摘要、文本分段、多模态、ASR 后处理） |
| 3  | 系统架构 |
| 4  | 方法（ASR 后处理 / 多模态章节切分 / 章标题 fallback / 学习 md 结构） |
| 5  | 评估（10 视频主表 / α sweep / 多模态 ablation / 章标题打分 / LLM 覆盖率） |
| 6  | Case Studies（OS dedupe / 计网 p38 / 多视频均值 / 24 视频架构泛化） |
| 7  | 局限性 + future work |
| 8  | 结论 |
| 附录 A | 实现细节、benchmark 列表 |
| 附录 B | LLM 切分路径汇总（auto） |

扩 corpus 后一键刷 §6.4：

```powershell
.\.venv\Scripts\python.exe scripts/aggregate_eval.py --mode section6-4 --out paper/section_6_4_auto.md
```

## 前端 demo

```powershell
# 1. 把跑好的视频导出到 web/public/notes/<video_id>/
.\.venv\Scripts\python.exe scripts/prepare_web_demo.py

# 2. 起前端
cd web
npm install
npm run dev
```

访问 `http://localhost:3000`，看视频笔记列表、双语切换、关键帧 lightbox、时间戳点击跳转。

## 已知局限

- ASR 同音字隐式错字（"想拖" vs "像托"）自动指标盲区，需要 word-level confidence 过滤（已落地，待扩规模评估）
- Pegasus 主旨偏移在小样本上 30 个 headlines 中观察到 2 例
- 短视频 (n_chunks < 5) 上 strict F1 是 0/1 二值化，方法论上同时报告 F1@1
- 英文 27+ chunk 视频上 Qwen 偶发 catch-all bias（24 视频 corpus 中 1/24 触发 fallback）
- Windows 上 faster-whisper 退出阶段偶发 STATUS_FATAL_APP_EXIT，已加 batch retry-once 兜底

## 开源声明

代码、benchmark gold 标注、评估脚本均开源。视频原始素材受版权保护，benchmark 列表（BV 号 / YouTube ID）在 `paper/draft.md` 附录 A.3 供独立复现。
