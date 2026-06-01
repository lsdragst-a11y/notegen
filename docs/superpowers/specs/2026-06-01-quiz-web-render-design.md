# 设计：章末自测题（quiz）渲染上 Web 前端

日期：2026-06-01
状态：已批准（待写实现计划）

## 背景与动机

quiz 数据（章末自测题）目前只在两个地方存在：

1. `data/outputs/*.md` 可下载笔记里的「🎓 本章自测」`<details>` 折叠块（由 `summarize._format_chapter_quiz` 渲染）。
2. `web/public/notes/*/chapters.json` 的 `quiz` 字段——**但 Web 前端完全不读取也不渲染它**。

也就是说，live demo（claude.ai/code 风格的 Next.js 站点）的访客看不到自测题。这是一个架构 gap：数据已经备齐、已经过质量加固（见 [[project-quiz-dedup]] 跨章去重，commit f05399a），却没有出口。本设计补上这个出口——把 quiz 渲染进 Web 章节卡片，做成可答题、有即时反馈的交互式自测。

范围明确收窄：**只动 Web 前端渲染层**。不碰分段管线（`src/`）、不碰 `.md` 生成、不改 quiz 数据结构。

## 数据形状（已存在，runtime 已可用）

`web/public/notes/<id>/chapters.json` 每个 chapter 对象上有可选 `quiz` 字段：

```json
{
  "title": "...", "start": 0, "end": 120, "abstract": "...",
  "quiz": {
    "questions": [
      { "type": "mc", "q": "...", "options": ["A","B","C","D"], "answer_idx": 2, "explanation": "..." },
      { "type": "tf", "q": "...", "answer": false, "explanation": "..." }
    ]
  }
}
```

- `type: "mc"`：单选，`options` 4 项（也可能 2-4），`answer_idx` 是正确项下标，`explanation` 可选。
- `type: "tf"`：判断，`answer` 是 boolean，`explanation` 可选。
- 不是所有章都有 quiz（仅 teaching/popsci 类生成；约 12/35 note 有）。无 quiz 的章 `quiz` 字段缺省。
- quiz 文本**没有** `_zh`/`_en` 双语字段（与 title/abstract 不同）——按源语言原样渲染。

`page.tsx` 的 `fetchNote(id)` 已经把整个 chapter 对象透传给 `NotesContent`，所以 `quiz` 字段在 runtime 已经到位，只是类型与渲染缺失。

## 架构

三处改动：

### 1. `web/lib/types.ts` — 补类型

`Chapter` interface 加可选 `quiz` 字段，新增判别联合类型：

```ts
type QuizQuestion =
  | { type: "mc"; q: string; options: string[]; answer_idx: number; explanation?: string }
  | { type: "tf"; q: string; answer: boolean; explanation?: string };

interface Quiz { questions: QuizQuestion[] }

// Chapter 内追加：
//   quiz?: Quiz;
```

### 2. `web/components/ChapterQuiz.tsx` — 新建交互组件（client component）

独立的 `"use client"` 组件，`props: { quiz: Quiz }`。

- 遍历 `quiz.questions`，每题一个块。
- 每题用 `useState` 管自己的 `selected` 状态（mc 存选中下标 `number | null`；tf 存选中布尔 `boolean | null`）。**无跨题计分、无"提交"按钮**（YAGNI）。
- **MC 渲染**：题干 + 4 个 option 按钮（纵向）。点击 → 锁定该选项为 `selected`：
  - 选中且正确 → 绿色 ✓
  - 选中且错误 → 红色 ✗，同时把正确项也标绿（让用户看到答案）
  - 未选中项保持中性
  - 选了之后展开 `explanation`（若有）
  - 可再点别的选项改答案（`selected` 更新）
- **TF 渲染**：题干 + 「对」「错」两个按钮，反馈逻辑同 MC。
- 反馈用语义色：正确 `#30d158`（绿）、错误 `#ff375f`（红）；揭示用 framer-motion 淡入展开。
- UI chrome 文案（正确/错误/解析/对/错）跟随 `LangContext` 的 `lang` 切换（中/EN）；题干本身按源语言原样显示。

### 3. `web/components/NotesContent.tsx` — 接入

在每个章节卡片（`<motion.div className="apple-card p-5">`，约 line 229-323）的 chunk chips 块**之后**、卡片 `</motion.div>` 之内，加一个折叠 toggle：

```tsx
{ch.quiz?.questions?.length ? (
  <details className="...">
    <summary>🎓 本章自测 ({ch.quiz.questions.length})</summary>
    <ChapterQuiz quiz={ch.quiz} />
  </details>
) : null}
```

- **默认折叠**（`<details>` 不带 `open`），镜像现有 glossary 折叠块（NotesContent line 327-341）的样式与交互。
- 章无 quiz 时整块不渲染（条件短路）。
- toggle summary 文案「本章自测 / Chapter Quiz」跟随 `lang`。

## 数据流

`page.tsx::fetchNote` → `NoteBundle.chapters[]`（含 `quiz`）→ `NotesContent` map → 条件渲染 `<details>` + `<ChapterQuiz quiz={ch.quiz}/>` → `ChapterQuiz` 内部各题 `useState` 管交互。纯前端、无网络、无持久化。

## 错误处理 / 边界

- `quiz` 缺省或 `questions` 为空 → 不渲染 toggle（条件短路，已覆盖）。
- mc `options` 少于预期（2-4 项）→ 按实际长度渲染，不假设 4。
- `answer_idx` 越界（理论不该发生，数据已 validate）→ 不特判，信任上游（边界在管线生成时已校验）。
- `explanation` 缺省 → 答题后不展开解析块。

## 测试与验收

- `npm run build`（含 `tsc` 类型检查）通过——确认 types.ts 联合类型与组件 props 对齐。
- `npm run dev` 起本地站，浏览器实测：
  - **p68（中文，BV1BE411D7ii_p68_p0）**：有 12 题 quiz（去重后），逐章展开、答对答错反馈、解析展开、改答案均正常。
  - **一个英文 note**（如 EH5jx5qPabU）：确认题干英文原样、UI chrome 跟随 EN、布局不崩。
  - 切换中/EN 看 toggle/反馈文案是否跟随 `lang`。
  - 无 quiz 的章（如 vlog 类）确认不渲染 toggle、布局无空块。
- 按全局约定：UI 改动必须在浏览器里实际走查 golden path + 边界后才算完成。

## 非目标（YAGNI）

- 不做跨题计分 / 进度条 / "提交全部" / 成绩汇总。
- 不做 quiz 双语翻译（数据无双语字段，不在本次范围）。
- 不碰 `src/` 分段管线、不改 `.md` 生成、不改 quiz 数据结构或生成逻辑。
- 不做答题状态持久化（localStorage 等）。

## 关联

- [[project-quiz-dedup]]：quiz 跨章去重（prompt + Python，commit f05399a），并首次发现「web 不渲染 quiz」的 gap——本设计正是该 memory 标注的「下一个质量候选」。
- [[project-web-frontend]]：Web 前端架构（Next.js 16 + Plyr + Apple 风格）。
- [[project-bilingual-toggle]]：`LangContext` / `pickByLang` 双语机制。
