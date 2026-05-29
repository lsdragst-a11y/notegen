# Corpus 状态盘点（2026-05-26）

验收前快照。32 个视频按"类型 × 质量"分类，标出哪些可以演示、哪些需要重跑。

## 总览

| 维度 | 数量 | 占比 |
|------|------|------|
| **总视频** | 32 | 100% |
| 学习类 | 22 | 69% |
| Vlog 类 | 10 | 31% |
| **质量分布** | | |
| ★★★★+ 好 | 19 | 59% |
| ★★★ 中 | 4 | 13% |
| ★★ 差 | 9 | 28% |

## 学习类 22 个

### ★★★★+ 好（12 个，55%）— 章标题贴切

| ID | 标题 | 章数 | 备注 |
|----|------|------|------|
| **BV1BE411D7ii_p68_p0** | 王道计组 p68 中断系统 | 7 | **演示首选**，J7 三件套最新落地（2026-05-26） |
| **BV19E411D78Q_p93_p0** | 王道计网 p93 万维网 WWW | 5 | K1 修复后 ch1 无幻觉 |
| BV1BE411D7ii_p66_p0 | 王道计组 p66 IO 接口 | 5 | 干净 |
| BV1BE411D7ii_p67_p0 | 王道计组 p67 IO 查询 | 5 | 干净 |
| BV1BE411D7ii_p70_p0 | 王道计组 p70 DMA | 4 | 干净 |
| BV19E411D78Q_p78_p0 | 王道计网 p78 TCP 报文段 | 4 | 含 · 本节复习 |
| BV19E411D78Q_p81_p0 | 王道计网 p81 TCP 流量控制 | 5 | 干净 |
| BV19E411D78Q_p85_p0 | 王道计网 p85 TCP 拥塞控制 | 7 | 5/7 章共享"拥塞"主题（合法），含 · 本节复习 |
| BV19E411D78Q_p92_p0 | 王道计网 p92 电子邮件 | 5 | 含 · 本节复习 |
| EH5jx5qPabU_p0 | AI Agents in 25 Minutes (n8n) | 13 | 英文 demo 候选 |
| BV1p5wuzQEz8_p2_p0 | Tina Huang｜如何学习编程 | 10 | 双语播客类 |
| BV141Ly6LE7x_p0 | AI 早报 2026-05-20 | 7 | 英文章标题 |

### ★★★ 中（3 个，14%）— 有小瑕疵但能用

| ID | 标题 | 章数 | 问题 |
|----|------|------|------|
| BV19E411D78Q_p38_p0 | 王道计网 p38 以太网 IEEE 802.3 | 6 | ch3 "全双共通性" 错字、ch5 疑问句、ch6 口语化 |
| BV1BE411D7ii_p69_p0 | 王道计组 p69 中断处理 | 3 | 章数偏少 |
| BV1GofdBZEW7_p0 | 33 分钟 Vibe Coding | 11 | 多章 generic 标题（"分析与计算思考" 等） |

### ★★ 差（7 个，32%）— 待重跑

详见下文 §"待跑清单"。

## Vlog 类 10 个

### ★★★★+ 好（7 个，70%）

| ID | 标题 | 章数 |
|----|------|------|
| BV1paLF6LEKN_p0 | 美国 $1 美元房子（底特律） | 4 |
| BV1Q3dHBSEAY_p0 | 日本顶级熟成河豚 | 9 |
| BV1EBdcBrEea_p0 | 一万八千元 8 个显卡盲盒 | 5 |
| BV1BpLg6wEMk_p0 | 190 块 vs 9000 块炒菜机器人 | 5 |
| BV1eboQBCEqj_p0 | 世界最大迪士尼游轮 | 5 |
| BV1QQ5x6eEZh_p0 | 泡面实力排行 | 5 |
| BV13BREBrEjU_p0 | 69 元菜单第 6 个食物 | 5 |

### ★★★ 中（1 个，10%）

| ID | 标题 | 章数 | 问题 |
|----|------|------|------|
| BV19SRSBeE6F_p0 | 北极超市 | 2 | 章数偏少（视频本身短） |

### ★★ 差（2 个，20%）

| ID | 标题 | 章数 | 问题 |
|----|------|------|------|
| BV175RvBAEgi_p1_p0 | 128 元可口可乐自助餐 | 1 | 单章，未切分 |
| BV1G85V6cE1g_p0 | 懂王访华轰 20 | 2 | 章标题带「主题:」前缀异常 |

## 待跑清单（下次重跑这 7 个学习类差视频）

排序依据：本地 ASR cache 是否在 → 时长从短到长（短的先跑确认 pipeline 没问题）。

### A 组：本地有 ASR cache，只重跑下游（4 个，每个约 5-15 分钟）

| 优先级 | ID | 时长 | 当前章标题问题 | ASR cache |
|-------|----|------|--------------|-----------|
| 1 | **BV19E411D78Q_p42_p0** | 9 min | ch2「关于ppp协议的数字数字·字节填充法实现透明传输」字面拼接 | ✓ `data/outputs/BV19E411D78Q_p42_p0.large-v3.asr.json` |
| 2 | **BV19E411D78Q_p44_p0** | 29 min | 4/4 章都是「·」拼接的双 headline 字面串 | ✓ `data/outputs/BV19E411D78Q_p44_p0.large-v3.asr.json` |
| 3 | **BV19E411D78Q_p51_p0** | 36 min | ch3「微信」是 ASR 错字漏入；其他章如「IP地址」「局域网」等 generic | ✓ `data/outputs/BV19E411D78Q_p51_p0.large-v3.asr.json` |
| 4 | **BV1S6kQBNEJq_p0** | 30 min | ch1「模块与茶文化」幻觉（吴恩达 AI Agent 课程精华） | ✓ `data/outputs/BV1S6kQBNEJq_p0.large-v3.asr.json` |

**重跑命令**（pipeline 默认会复用 ASR cache 不传 `--force-asr` 即可）：

```bash
.venv/Scripts/python.exe src/pipeline.py \
  "https://www.bilibili.com/video/BV19E411D78Q?p=42" \
  --summarizer neural --chunker texttile --chapters --keyframes \
  --llm-chapters --vlm-captions --learning-mode --lang zh --quality 360p
```

注意：
- p51 的 ch3「微信」需要补 `_DOMAIN_CORRECTIONS["network"]` 错字字典（候选词：路由/网关/网络的某个变体——重跑前先扫 ASR cache 看实际错字是什么），参考 §6.5.3 加字典模式
- 必须 `--learning-mode`（保留 TOC / 术语表 / 章末小结）
- `--vlm-captions` 让 J7 看到内容差异，对修字面拼接有用

### B 组：本地无源文件，需重新下载（3 个，每个约 15-25 分钟）

| 优先级 | ID | 时长 | URL | 当前章标题问题 |
|-------|----|------|-----|--------------|
| 5 | **claudecode**（BV1SddcBFESs） | 11 min | https://www.bilibili.com/video/BV1SddcBFESs | 2 章字面拼接「10分钟学会claude code 基础操作·如何手动打开」 |
| 6 | **python**（BV1Sz4y1U77N） | 21 min | https://www.bilibili.com/video/BV1Sz4y1U77N | 3 章字面拼接「python基础:python基础·python教程」 |
| 7 | **linear-algebra**（BV1Vi5Q66EYo） | 17 min | https://www.bilibili.com/video/BV1Vi5Q66EYo | 3 章「我是二三考研的我是二二年·八百八的基础题」全 chunk-headline 字面串 |

**重跑命令**：

```bash
.venv/Scripts/python.exe src/pipeline.py \
  "https://www.bilibili.com/video/BV1Sz4y1U77N" \
  --summarizer neural --chunker texttile --chapters --keyframes \
  --llm-chapters --vlm-captions --learning-mode --lang zh --quality 360p
```

注意：
- 这 3 个的 web 端 id 是 custom slug（python/claudecode/linear-algebra），但 meta.json 里的 `id` 字段是真实 BV 号——重跑后 publish 路径会按 `BV1Sz4y1U77N_p0` 命名，需要 manually 把 web/public/notes/python 目录 rename 或写迁移脚本。或者：跑完后保留旧 id，靠 `_apply_chapter_titles.py`（J7 落地脚本）只更新 chapter title 部分

## 演示建议（验收用）

主演示：**BV1BE411D7ii_p68_p0 王道计组 p68 中断系统**
- 7 章贴切，最新 J7+K1 修复全套生效
- 含双语 toggle（title_zh/title_en）、abstract、recap、quiz、章末 · 本节复习
- 关键帧 + TOC + 术语表（看 md）

备演示：
- **BV19E411D78Q_p93_p0** 万维网 — 展示 K1 修复（ch1 "四维事实" → "万维网实例与组成"）
- **BV19E411D78Q_p85_p0** TCP 拥塞控制 — 展示长视频 7 章 + 视频整体主题守门（5 章合法共享"拥塞"前缀）
- **EH5jx5qPabU_p0** AI Agents 25 min — 英文 demo

回避演示：
- 上述"待跑清单"7 个全部
- p51 NAT（ch3 微信）、python/claudecode/linear-algebra（章标题字面拼接）

## 关联

- J7 三件套修法 → `paper/draft.md` §6.7.1
- K1 word-prob 守门 → `paper/draft.md` §6.7.2
- ASR 字典扩充模式 → `paper/draft.md` §6.5.3
- 重跑工具 → `scripts/_apply_chapter_titles.py`（J7 落地，仅重跑 refine_chapter_titles + 同步前端）
