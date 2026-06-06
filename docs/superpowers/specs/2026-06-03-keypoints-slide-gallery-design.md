# 设计：知识点速览 → 幻灯片画廊网格（Slide Gallery Grid）

日期：2026-06-03
状态：已实现（替代同日被否的「内容时间轴」方案）

## 背景与动机

笔记页右栏的「💡 知识点速览」原本是**文字主导**的卡片列表：每张卡左侧一个
80×56 的关键帧缩略图，右侧塞满时间、⭐🎯、headline、summary 预览、keywords
chip。缩略图太小、被文字淹没，幻灯片内容根本看不清——这正是用户反馈
"可视化程度太低" 的根。

**先前走偏的方案**：我提议在右栏顶部加一条贯穿全片的「内容时间轴」（章节色带
+ 关键帧刻度 + 播放头）。用户否决，理由：**左栏已有跳段**（`ChapterNav` chips +
`ChapterDetailCard` 上下章 + 播放器进度条），右侧再来一条章节导航是冗余。

**改定方向**：可视化精力转回「知识点速览」本身——把关键帧幻灯片**升为卡片主体**，
做成「视觉学习板」式的画廊网格。图为主、文为辅。

范围：**只动 Web 前端渲染层**。不碰 `src/` 管线、不碰 `.md` 生成、不改
`chapters.json`/`summary.json` 数据结构。零新模型、零幻觉风险。

## 数据形状（已存在）

全部来自 `summary: Chunk[]`（`page.tsx::fetchNote` → `NotesContent` 已透传）：

- `keyframe { rel, time, score }` —— 幻灯片大图，URL `/notes/<noteId>/keyframes/<rel>`。
- `headline`(+`_zh`/`_en`) —— 卡片标题（走 `pickByLang`）。
- `summary`(+lang) / `text`(+lang) —— 一句话说明（`summary` 优先，缺则 `text` 截 80 字）。
- `start` —— 时间角标 + `onSeek` 目标。
- `chunkMarks(c)` → `Mark[]`（emphasis/hard）—— ⭐🎯 角标，仅 `showMarks`（teaching）。

## 架构

两处改动，**不新增组件**：

### 1. `web/components/NotesContent.tsx` — 知识点速览改画廊

`showKnowledgePoints` 分支（teaching/popsci）的卡片网格由
`grid-cols-1 md:grid-cols-2`（左图右文）重写为：

- **响应式列**：`grid-cols-1 sm:grid-cols-2 xl:grid-cols-3`（窄屏 1 列、平板 2 列、宽屏 3 列）。
- **卡片 = `apple-card overflow-hidden flex flex-col`**（去内边距，图片顶满边）：
  - **顶部幻灯片大图**：`aspect-video`（16:9）、`object-cover`、`dark:brightness-90`，
    hover 轻微放大 + 半透明遮罩 + Expand 图标。
    - 有 `keyframe` → 整图是按钮，**点击 → 开 Lightbox**（`setLbIdx(lbi)`，`stopPropagation`）。
    - 无 `keyframe` → 渐变占位块 + Clock 图标（保持网格整齐）。
    - **时间角标**（左下）：`formatTime(c.start)`，黑底半透明。
    - **⭐🎯 角标**（右上，仅 emphasis/hard）：白底圆形小徽章。
  - **底部文字区** `p-3.5`：headline（`font-semibold` `line-clamp-2`）+ 一句话说明
    （`line-clamp-2`，`summary` 优先）。keywords chip **删除**（图为主、减文字噪声）。
  - **整卡点击 → `onSeek(c.start)`**（跳转）；当前 chunk `ring-2`；emphasis 卡金色描边。
- vlog/talk 分支（`VlogTimeline`）**保留不动**。
- `filterStopwords` import 随 keywords 删除而移除（已无引用）。

### 2. `web/components/OverviewHero.tsx` — 删冗余章节比例条

- **删除**原 line 69-98 的「章节构成」比例条整块（功能与左栏章节导航重复）。
- props 由 `{ overview, chapters, currentTime, onSeek }` 退化为 `{ overview }`；
  连带清理 `span`/`curIdx` 计算、`formatTime` import、`Chapter` type import。
- OverviewHero 退化为纯「散文总结 + 你将学到」。
- `NotesContent` 对 `<OverviewHero>` 的调用同步去掉三个 prop。

## 数据流

`page.tsx::fetchNote` → `NotesContent`（算 `showMarks`/`lbIdxByChunk`/`currentChunkIdx`）
→ 画廊卡片：位置/内容纯由 `summary[i]` 字段派生，无新 state。Lightbox（`lbIdx` /
`lightboxItems` / `lbIdxByChunk`）**全部复用**，点图开灯箱、点卡跳转，与播放器联动。

## 交互模型

| 元素 | 点击 | hover |
|---|---|---|
| 幻灯片大图 | 开 Lightbox 定位该帧 | 放大 + 遮罩 + Expand 图标 |
| 卡片其余区域 | `onSeek(c.start)` 跳转 | 卡片上浮 `y:-3` |
| ⭐🎯 / 时间角标 | （`pointer-events-none`，不拦点击） | — |

## 边界

- 无 `keyframe` → 渐变占位 + Clock 图标，卡片不塌。
- 关键帧加载失败 → 浏览器默认（信任现有 keyframes 资源，已被旧卡片消费验证）。
- 窄屏 → 单列；图 16:9 自适应宽度。
- 非 teaching（popsci）→ 无 ⭐🎯，画廊仍渲染；vlog/talk 仍走 VlogTimeline。

## 测试与验收

- `npx tsc --noEmit` 通过 ✓（OverviewHero 改 props 后调用处无残留报错）。
- `npm run dev` 浏览器走查：
  - **teaching 中文（BV1YE411D7nH_p61_p0）**：画廊大图清晰、2-3 列响应式、当前段高亮、
    ⭐🎯 角标定位、点图开灯箱、点卡跳转；OverviewHero 旧比例条已消失。
  - 英文 note：headline/说明走 EN、布局不崩。
  - vlog 类：确认仍是 VlogTimeline、无 ⭐🎯。
  - 暗色/亮色、窄屏不溢出。

## 非目标（YAGNI）

- 不做右侧章节时间轴（冗余，见背景）。
- 不在卡片上保留 keywords chip（降噪）。
- 不碰 `src/` 管线、`.md`、数据结构。
- 不引图表/可视化库。

## 关联

- [[project-web-frontend]]：Web 前端架构（Next.js 16 + Plyr + Apple 风格）。
- [[project-bilingual-toggle]]：`pickByLang` 双语机制（headline/说明复用）。
- [[project-quiz-dedup]]：上一个「Web 渲染层补 gap」设计（同类只动前端）。
