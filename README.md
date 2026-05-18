# NoteGen — 基于深度学习的网课视频摘要与笔记生成系统

输入一个视频链接（B站 / YouTube / 本地文件），自动产出带时间戳的结构化学习笔记。

## Pipeline

```
URL → 下载视频 → 抽音频 → ASR 转写（带时间戳）
    → 章节切分 → 段落摘要 → 关键帧抽取 → Markdown 笔记
```

## 当前进度

- [x] 项目骨架
- [x] Week 1: baseline pipeline 跑通（large-v3 ASR + 抽取式摘要，10-15% 压缩比）
- [x] 神经摘要接入（Randeng-Pegasus-238M）：生成段落小标题 + jieba 抽取式正文
- [x] Week 2 文本侧 baseline：章节切分（关键词 Jaccard + TextTiling depth score），章节标题用层次化 Pegasus 摘要
- [x] 关键帧抽取：Chinese-CLIP 给每段抽 8 帧、选与 headline cosine 最高那帧嵌入笔记
- [x] ASR 专有名词错字两层修复：yt-dlp metadata → initial_prompt + 术语后处理词典
- [x] **Week 2 多模态章节切分（论文核心创新点）**：复用 CLIP image features，文本 Jaccard 距离 + 视觉 cosine 距离 min-max 归一化后加权融合（α=0.3 默认）；保留 ablation 数据到 chapters.json
- [x] 评估闭环 + 4 视频 cross-domain benchmark（PPT 教学 × 2 + 实拍 Vlog × 2，手标 gold），P/R/F1 + 容差 ±1 段 F1@1
- [ ] Week 3+: 前端（Next.js + 时间戳跳转）/ 论文初稿 / 答辩

## 快速开始

### 环境要求
- Windows 11 + NVIDIA GPU（已在 RTX 4080 Laptop 验证）
- Python 3.10（通过 Miniconda 管理）
- ffmpeg

### 安装

```powershell
# 1. 创建并激活环境
conda create -n notegen python=3.10 -y
conda activate notegen

# 2. 安装依赖
pip install -r requirements.txt
```

### 运行 baseline

```powershell
python src/pipeline.py "https://www.bilibili.com/video/BVxxxxxxx"
```

## 目录结构

```
notegen/
├── data/
│   ├── raw/        # 原始视频
│   ├── audio/      # 抽取的音频（16kHz mono wav）
│   └── outputs/    # 转写与笔记 JSON
├── src/
│   ├── download.py    # yt-dlp 下载 + ffmpeg 抽音频
│   ├── asr.py         # faster-whisper 语音识别
│   ├── segment.py     # 章节切分（待实现）
│   ├── summarize.py   # 段落摘要
│   └── pipeline.py    # 串联入口
├── notebooks/      # 实验草稿本
├── configs/        # 配置文件
└── requirements.txt
```
