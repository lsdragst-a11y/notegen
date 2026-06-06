# 设计：知识点细看弹窗 + 全局书签

日期：2026-06-03
状态：已实现（接在「知识点幻灯片画廊」之后的第二轮增强）

## 背景与动机

幻灯片画廊落地后，用户提了两点：

1. **每张卡的一句话说明被 `line-clamp-2` 截断，想看完整内容看不到**——需要把单条
   「拉出来细看」（完整摘要 + 转写原文 + 关键词 + 大图）。
2. **想要书签功能**：重要的知识点 / 章节能收藏，攒成一个**书签页面**，方便回看；
   且**收藏这个动作本身不要跳转视频**（"不需要移动视频"）。

范围：纯前端。静态站无后端、无登录，书签只能存浏览器 `localStorage`。

设计决断（经用户确认）：细看用**弹窗 Modal**；书签用**全局书签页**（导航栏入口，跨所有笔记）。

## 架构

### 1. 细看弹窗 `web/components/KeyPointModal.tsx`（新建）

- props：`chunk / chunkIdx / noteId / noteTitle / marks / onClose / onSeek`。
- 黑底遮罩 + 居中 `apple-card`（`max-w-2xl max-h-[88vh]` 可滚），framer-motion 弹入；
  Esc / 点遮罩关闭。复用 Lightbox 的遮罩观感。
- 内容：关键帧大图（16:9）→ 时间区间 + ⭐🎯 + **收藏按钮** + **跳转按钮**（跳转后关闭）
  → 完整标题 → **完整摘要（不截断）** → 关键词 chips → **转写原文**（`<details>` 折叠）。
- 文本走 `pickByLang`（headline/summary/text/keywords 都按当前 lang）。

### 2. 书签存储 `web/lib/bookmarks.ts`（新建）

- `localStorage` key `notegen.bookmarks`，值为 `Bookmark[]`。
- `Bookmark = { key, noteId, noteTitle, kind:"chunk"|"chapter", idx, title, title_en?, time, keyframeRel?, addedAt }`；
  `key = bookmarkKey(noteId, kind, idx)` 唯一。**title 存 zh + en 两份**，书签页按 lang 显示。
- 纯函数：`getBookmarks / isBookmarked / toggleBookmark / removeBookmark`；写入后派发
  `BOOKMARKS_EVENT`。
- hooks：`useBookmarksList()` / `useIsBookmarked(key)`——订阅本页事件 + 跨标签页 `storage` 事件，实时同步。

### 3. `web/components/BookmarkButton.tsx`（新建）

- 收藏切换按钮，`stopPropagation`——**点书签不触发卡片点击/跳转**（满足"不移动视频"）。
- 已收藏=accent 色 + 实心 fill；样式（背景/尺寸）由调用处 className 给，融入各处底色。

### 4. `web/components/NotesContent.tsx`（接入）

- 知识点卡片**点击行为由 seek 改为打开 KeyPointModal**（细看）；快速跳转仍走图上 ▶ 按钮。
- 每张卡图**左上角**常显 BookmarkButton（chunk 书签）；每个**章节卡头部**加 BookmarkButton（chapter 书签）。
- 末尾渲染 `<KeyPointModal>`，`detailIdx` state 控制开关。

### 5. 深链定位 `VideoPlayer` + `notes/[id]/page.tsx`

- VideoPlayer 加 `startTime?` prop：播放器就绪后（`ready`/`loadedmetadata`/`canplay` 兜底，命中即止）seek 一次。
- 笔记页从 `?t=秒` 读 startTime（`window.location.search`，SSR-safe），传给播放器并初始化 `currentTime`。
- 书签页的跳转链接即 `/notes/<id>?t=<秒>`。

### 6. `NavBar` + `web/app/bookmarks/page.tsx`

- NavBar 加「书签」入口（Bookmark 图标 + `useBookmarksList().length` 实时计数徽标）。
- 书签页：按笔记分组（组内按时间升序、组间按最近收藏降序），每条显示缩略图/章节图标 +
  类型徽标（知识点/章节）+ 时间 + 标题，点击 → `/notes/<id>?t=`，带移除按钮；空态有引导。

## 交互模型（更新后的知识点卡）

| 元素 | 点击 |
|---|---|
| 卡片主体（图背景 / 文字区） | 打开细看弹窗 |
| 图上 ▶ | `onSeek(start)` 快速跳转 |
| 图上 ⤢ | 开 Lightbox |
| 图左上 🔖 | 收藏/取消（不跳转） |
| 弹窗内 跳转按钮 | seek + 关弹窗 |

## 边界

- 无 keyframe → 弹窗不显大图、书签页用图标占位。
- `localStorage` 不可用（隐私模式）→ try/catch 静默降级，功能不报错只是不持久。
- 深链 `?t=` 非法/缺失 → startTime=0，正常从头播。
- lang 切换 → 弹窗/书签页标题跟随；书签数据存双语，切换不丢。

## 测试与验收

- `npx tsc --noEmit` 通过 ✓。`/`、`/bookmarks`、`/notes/<id>?t=120` 均 200 ✓。
- 浏览器走查（待用户确认）：点卡开弹窗看全文 + 折叠转写；收藏知识点/章节不跳转；
  NavBar 计数 +1；书签页分组列出、点条跳到对应时间；移除生效；中/EN 切换文案正确；暗/亮、窄屏。

## 非目标（YAGNI）

- 不做账号/云同步（静态站，localStorage 足够）。
- 不做书签标签/备注/排序自定义。
- 弹窗内不再套 Lightbox（图够大；浏览全部帧仍走卡片 ⤢）。

## 关联

- [[project-web-frontend]]：Web 前端架构。
- [[project-bilingual-toggle]]：`pickByLang` 双语（弹窗/书签标题复用）。
