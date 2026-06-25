# NoteGen 前端重设计方案（NotebookLM 风格）

> 2026-06-25 v1 收敛更新：`FluidBG.tsx`、`ParticleBG.tsx`、`AskBar.tsx`
> 已确认无运行代码引用并删除。核心页面已完成 Warm Fold token 迁移：
> `ChatPanel`、`NoteWorkspace`、`CreateNotePanel`。剩余未完成项集中在浏览器
> walkthrough、截图/GIF、a11y 复查和可提交工作树收敛。

> 2026-06-10 · 参照 [NotebookLM](https://notebooklm.google/) · 配套视觉稿见会话内 mockup
> 范围：首页（笔记本库）+ 笔记详情（三栏工作台）两个核心页，其余页面只做 token 级统一
> 2026-06-15 状态更新：P0/P1 主体已落地，实际产品入口调整为 `/` 精简 landing、
> `/notebooks` 登录后笔记本库、`/notes/[id]` 三栏工作台、`/s/[token]` 分享只读页。
> QA 不再是占位，已由 `ChatPanel` 接入后端异步问答。

## 1. 设计原则

从 NotebookLM 提炼出四条，作为后续所有 UI 决策的依据：

1. **内容即界面**。去掉营销感元素（粒子背景、大字 hero），登录后直接面对笔记库；未登录首页压缩为一屏精简介绍 + 公开示例。
2. **三栏心智模型**：来源（输入）/ 笔记（产出）/ 工具（操作）。NoteGen 映射为：章节与视频来源 / 笔记内容 / 播放器与工具。
3. **安静的视觉**：大圆角、低对比细边框、单一品牌蓝、克制阴影。装饰让位给内容。
4. **AI 产出可溯源**：每个知识点、术语、QA 回答都带时间戳跳转——对应 NotebookLM 的 citation 心智，这也是论文的卖点。

## 2. Design tokens（`web/app/globals.css`）

| Token | 现状 | 新值（light / dark） | 说明 |
|---|---|---|---|
| `--bg` | 纯白/纯黑 | `#f8fafd` / `#1f1f20` | NotebookLM 的"纸面感"页面底色 |
| `--bg-elevated` | — | `#ffffff` / `#28292a` | 卡片表面，与页面底色拉开一档 |
| `--accent` | `#0a84ff`（Apple 蓝） | `#0b57d0` / `#a8c7fa` | Google 蓝；全站唯一强调色，删除多色 accent |
| `--radius-card` | 混用 | `16px` | 卡片统一 |
| `--radius-modal` | 混用 | `24px` | 弹层/面板 |
| chips | 混用 | `999px` 全圆 | filter、category、工具按钮 |
| 阴影 | 多档 | 仅 hover 一档 `0 1px 3px rgba(0,0,0,.08)` | 静止态靠边框分层，不靠阴影 |
| 标题字重 | 600/700 混用 | 500 | NotebookLM 全站无重字重 |

**删除方向**：`FluidBG.tsx`、`ParticleBG.tsx` 不再服务核心产品流；确认无引用后可删。NotebookLM 没有装饰背景。

## 3. 页面结构

### 3.1 入口：首页 + 笔记本库

现状问题：landing（`page.tsx`）、`dashboard`、`library`、`history` 四处分散，入口重复。

当前结构：

- `/` 保留为精简 landing：未登录强调产品入口和公开示例，已登录用户引导进入 `/notebooks`。
- `/notebooks` 是登录后的笔记本库。`dashboard`、`library` 保留为跳转路由，统一 redirect 到 `/notebooks`。
- 顶栏：logo · 全局搜索 · 主题切换 · 用户菜单（历史任务入口收进用户菜单）。
- 内容区：filter chips（全部 / 我的 / 公开示例）+ 排序；grid 首位是「新建笔记本」虚线卡（点击弹 panel，合并 `generate` 页的 URL/上传/画质选择逻辑），其后是笔记卡。
- 笔记卡：category 色系图标 + 标题（2 行截断）+ 元信息行（日期 · N 章 · 时长）+ category chip。不放缩略图——NotebookLM 卡片靠排版而非图片，也省掉首页加载几十张 keyframe。

### 3.2 笔记详情 = 三栏工作台

栅格：`lg:grid-cols-[260px_minmax(0,1fr)_400px]`，三栏各自 `overflow-y-auto`，整页不滚（NotebookLM 的关键手感：三栏独立滚动）。

| 栏 | 内容 | 来源组件 |
|---|---|---|
| 左 · 来源 | 视频来源卡（B 站/YouTube/本地文件名）→ 章节垂直列表（当前章高亮、随播放滚动）→ 逐字稿入口 | `ChapterNav` 垂直化改造 |
| 中 · 笔记 | OverviewHero → 知识点卡 grid（2 列）→ 章节详情（含小测折叠）→ 术语表折叠 → `ChatPanel` 问答 | `NotesContent` + `ChatPanel` |
| 右 · 视频与工具 | sticky：VideoPlayer + ChapterChip + 章节色带 → 工具组（书签 / Markdown 导出 / Word 导出 / 分享 / 双语切换） | `VideoPlayer`、`ChapterChip`、`LangToggle`、`BookmarkMenu`、`web/lib/export.ts` |

响应式：`<lg` 时右栏视频上移为顶部 sticky（即现有布局），左栏收成抽屉（顶栏汉堡键唤起），`MiniPlayer` 仅在此断点下保留。

### 3.3 组件映射

| 现组件 | 去向 |
|---|---|
| `NavBar` | 简化：工作台内不再放书签/历史链接，避免再出现重叠 bug |
| `ChapterNav`（横向 chip 条） | 改左栏垂直列表 |
| `ChapterDetailCard` | 并入中栏章节详情区 |
| `NotesContent`（419 行） | 拆为 `OverviewSection` / `KeyPointsGrid` / `ChapterSection` / `GlossarySection`，每个 ≤150 行 |
| `Spotlight` | 保留，⌘K 全局搜索是加分项 |
| `MiniPlayer` | 仅 `<lg` 断点 |
| `FluidBG` / `ParticleBG` | 核心流不再依赖；确认无引用后删除 |
| `VlogTimeline` / `ChapterQuiz` / `Lightbox` / `KeyPointModal` | 不动，换容器即可 |
| `AskBar` | 旧占位组件；真实入口已由 `ChatPanel` 承接，确认无引用后可删 |

## 4. 实施清单（3 个独立可验收的批次）

**P0 · tokens + 入口收敛** ✅ 主体完成
- [x] `globals.css`：token 与视觉基调已统一
- [x] `/` 精简 landing，`/notebooks` 承接登录后笔记本库
- [x] `dashboard`、`library` 保留 redirect
- [x] 「新建笔记本」panel 复用 `CreateNotePanel`
- [ ] 确认 `FluidBG`/`ParticleBG` 无引用后删除

**P1 · 三栏工作台** ✅ 主体完成
- [x] `notes/[id]/page.tsx` 收敛到 `NoteWorkspace`
- [x] lg 三栏布局与 `<lg` 抽屉/mini player 回落
- [x] 章节、逐字稿、视频 seek 联动
- [x] 右栏工具组：书签 / Markdown / Word / 分享 / 双语
- [x] QA 由 `ChatPanel` 接入真实接口

**P2 · 打磨** 进行中
- [x] 加载骨架和错误态已收敛到 `WorkspaceSkeleton` / `WorkspaceError`
- [x] 移动端左栏抽屉已实现
- [ ] 浏览器 smoke：视频播放、seek、分享、导出、QA 轮询、书签同步
- [ ] a11y：三栏 landmark、章节列表 `aria-current`、Lighthouse a11y ≥ 90
- [ ] 删除确认无引用的旧视觉组件和 `AskBar`
- 验收：`npx tsc --noEmit` 通过；浏览器 smoke 记录写入 `docs/memory/`

## 5. QA 接口（已落地，2026-06-11）

GPU 串行约束下走异步队列（RQ "qa" 高优队列，插队在排队 pipeline 任务前）：

```
POST /api/notes/{id}/ask        # require_user；公开笔记所有登录用户可问，私有仅 owner
  body: { "question": str (≤500), "lang": "zh" | "en" }
  resp: { "qa_id": str }        # 409=该用户已有进行中 QA；503=Redis 不可用

GET  /api/qa/{qa_id}            # 轮询（前端 1.5s 间隔，10min 封顶）
  resp: { "status": "queued"|"running"|"done"|"failed",
          "queue_ahead"?: int,  # queued 时给排队位
          "result"?: { "answer": str,
                       "citations": [ { "chunk_idx": int, "start": float, "quote": str } ] },
          "error"?: str }
```

实现：`src/qa.py`（BM25 检索 jieba 分词 + Qwen 生成 + 引用校验，检索层独立可换 bge-m3），
`worker_tasks.run_ask` 在 worker 进程内直接执行——**模型常驻**，首问冷加载 ~1min，
后续问题秒级；每个 pipeline 任务开跑前 `unload_qa_model()` 让出 VRAM（worker 串行
保证不并发）。前端 `ChatPanel.tsx` 渲染会话 + 时间戳引用 chip（点击 onSeek）。
`src/qa.py` 的 CLI 入口保留作手动调试。
