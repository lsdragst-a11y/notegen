# Quiz Web 渲染 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把已存在但未渲染的章末自测题（quiz）做成可答题、有即时反馈的交互式组件，渲染进 Next.js 笔记页的章节卡片。

**Architecture:** 三处改动——`lib/types.ts` 补 `Quiz`/`QuizQuestion` 判别联合类型；新建 client 组件 `components/ChapterQuiz.tsx`（每题独立 `useState`，点选即反馈，无计分）；`components/NotesContent.tsx` 在章卡 chunk chips 之后加默认折叠的「本章自测」toggle。纯前端、无网络、无持久化，不碰分段管线与 `.md` 生成。

**Tech Stack:** Next.js 16, React 19, TypeScript 5, framer-motion 12, lucide-react, Tailwind v4（CSS vars 主题）。

**测试说明（重要）：** web 项目**无 JS 单元测试框架**（package.json 仅有 dev/build/start/lint）。引入 vitest/jest 属本次范围外的 YAGNI。因此本计划的验证门是：(1) `npm run build`（Next.js 构建内含 `tsc` 类型检查，会因类型不匹配 fail）；(2) `npm run lint`（eslint，会因 unused var / 未定义引用 fail）；(3) dev server 浏览器人工走查。每个实现任务以「build + lint 通过」为绿灯，最后一个任务做浏览器验收。

---

## File Structure

- **`web/lib/types.ts`**（修改）：在 `Chapter` interface 加 `quiz?: Quiz`；文件内新增 `QuizQuestion` 判别联合 + `Quiz` interface。单一职责：全站共享类型定义。
- **`web/components/ChapterQuiz.tsx`**（新建）：交互式 quiz 渲染。内部拆 3 个组件——`ChapterQuiz`（外层 map）、`McQuestion`（单选题）、`TfQuestion`（判断题）、`Explanation`（解析展开复用）。单一职责：一个章的 quiz 交互。
- **`web/components/NotesContent.tsx`**（修改）：在每个章卡内挂折叠 toggle + `<ChapterQuiz>`。已是笔记主渲染组件，只新增一处条件块，不重构。

数据形状（runtime 已透传，`page.tsx::fetchNote` → `bundle.chapters[].quiz`）：
- mc：`{ type:"mc", q, options:string[], answer_idx:number, explanation? }`
- tf：`{ type:"tf", q, answer:boolean, explanation? }`
- 已用 p68 实测确认：8 章全有 quiz，mc 键 = q/options/answer_idx/explanation，tf 键 = q/answer/explanation。quiz 文本无 `_zh`/`_en`，按源语言原样渲染；只有 UI chrome 文案跟随 `lang`。

---

## Task 1: 补 Quiz 类型

**Files:**
- Modify: `web/lib/types.ts:36-47`（`Chapter` interface）

- [ ] **Step 1: 在 `Chapter` interface 内加 `quiz` 字段**

把 `web/lib/types.ts` 第 36-47 行的 `Chapter` interface：

```ts
export interface Chapter {
  title: string;
  title_zh?: string;
  title_en?: string;
  start: number;
  end: number;
  indices: number[];
  abstract?: string;
  abstract_zh?: string;
  abstract_en?: string;
  children?: Chapter[];
}
```

改为（仅在 `children?` 后加一行 `quiz?: Quiz;`）：

```ts
export interface Chapter {
  title: string;
  title_zh?: string;
  title_en?: string;
  start: number;
  end: number;
  indices: number[];
  abstract?: string;
  abstract_zh?: string;
  abstract_en?: string;
  children?: Chapter[];
  quiz?: Quiz;
}
```

- [ ] **Step 2: 在 `Chapter` interface 之后新增 quiz 类型定义**

在 `Chapter` interface 的闭合 `}` 之后、`export interface Overview` 之前，插入：

```ts
export type QuizQuestion =
  | { type: "mc"; q: string; options: string[]; answer_idx: number; explanation?: string }
  | { type: "tf"; q: string; answer: boolean; explanation?: string };

export interface Quiz {
  questions: QuizQuestion[];
}
```

- [ ] **Step 3: 类型检查**

Run: `cd web && npm run build`
Expected: 构建成功（PASS）。`Chapter` 引用了下方定义的 `Quiz`（TS interface 提升，前向引用合法）。若报 `Cannot find name 'Quiz'`，确认 Step 2 的 `Quiz`/`QuizQuestion` 已写入同文件。

> 注：此 task 不单独 commit，与 Task 2 一起提交（types 在没有消费者时改动很小，且 Task 2 的组件依赖这些类型）。

---

## Task 2: 新建 ChapterQuiz 交互组件

**Files:**
- Create: `web/components/ChapterQuiz.tsx`

- [ ] **Step 1: 写组件文件**

新建 `web/components/ChapterQuiz.tsx`，完整内容：

```tsx
"use client";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check, X } from "lucide-react";
import type { Quiz, QuizQuestion } from "@/lib/types";
import { useLang } from "./LangContext";

const GREEN = "#30d158";
const RED = "#ff375f";

function Explanation({ text }: { text?: string }) {
  if (!text) return null;
  return (
    <motion.div
      key="exp"
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      exit={{ opacity: 0, height: 0 }}
      className="mt-2 overflow-hidden text-xs leading-relaxed
                 text-[var(--fg-secondary)] border-l-2 border-[var(--border)] pl-3"
    >
      {text}
    </motion.div>
  );
}

function McQuestion({ q, idx }: { q: Extract<QuizQuestion, { type: "mc" }>; idx: number }) {
  const [selected, setSelected] = useState<number | null>(null);
  const answered = selected !== null;
  return (
    <div className="rounded-xl bg-[var(--bg-muted)] p-3">
      <div className="mb-2 text-sm font-medium text-[var(--fg)]">
        <span className="mr-1.5 text-[var(--fg-tertiary)] tabular-nums">{idx + 1}.</span>
        {q.q}
      </div>
      <div className="flex flex-col gap-1.5">
        {q.options.map((opt, oi) => {
          const isCorrect = oi === q.answer_idx;
          const isChosen = oi === selected;
          let style: React.CSSProperties = {};
          let icon: React.ReactNode = null;
          if (answered && isCorrect) { style = { borderColor: GREEN, color: GREEN }; icon = <Check size={13} />; }
          else if (answered && isChosen && !isCorrect) { style = { borderColor: RED, color: RED }; icon = <X size={13} />; }
          return (
            <button
              key={oi}
              onClick={() => setSelected(oi)}
              style={style}
              className="flex items-center gap-2 rounded-lg border border-[var(--border)]
                         px-3 py-2 text-left text-sm transition-colors hover:border-[var(--accent)]"
            >
              <span className="w-4 shrink-0">{icon}</span>
              <span>{opt}</span>
            </button>
          );
        })}
      </div>
      <AnimatePresence>{answered && <Explanation text={q.explanation} />}</AnimatePresence>
    </div>
  );
}

function TfQuestion({ q, idx }: { q: Extract<QuizQuestion, { type: "tf" }>; idx: number }) {
  const { lang } = useLang();
  const [selected, setSelected] = useState<boolean | null>(null);
  const answered = selected !== null;
  const choices: { val: boolean; label: string }[] = [
    { val: true, label: lang === "en" ? "True" : "对" },
    { val: false, label: lang === "en" ? "False" : "错" },
  ];
  return (
    <div className="rounded-xl bg-[var(--bg-muted)] p-3">
      <div className="mb-2 text-sm font-medium text-[var(--fg)]">
        <span className="mr-1.5 text-[var(--fg-tertiary)] tabular-nums">{idx + 1}.</span>
        {q.q}
      </div>
      <div className="flex gap-2">
        {choices.map(c => {
          const isCorrect = c.val === q.answer;
          const isChosen = c.val === selected;
          let style: React.CSSProperties = {};
          let icon: React.ReactNode = null;
          if (answered && isCorrect) { style = { borderColor: GREEN, color: GREEN }; icon = <Check size={13} />; }
          else if (answered && isChosen && !isCorrect) { style = { borderColor: RED, color: RED }; icon = <X size={13} />; }
          return (
            <button
              key={String(c.val)}
              onClick={() => setSelected(c.val)}
              style={style}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)]
                         px-4 py-1.5 text-sm transition-colors hover:border-[var(--accent)]"
            >
              {icon}{c.label}
            </button>
          );
        })}
      </div>
      <AnimatePresence>{answered && <Explanation text={q.explanation} />}</AnimatePresence>
    </div>
  );
}

export default function ChapterQuiz({ quiz }: { quiz: Quiz }) {
  return (
    <div className="mt-3 flex flex-col gap-2">
      {quiz.questions.map((q, i) =>
        q.type === "mc"
          ? <McQuestion key={i} q={q} idx={i} />
          : <TfQuestion key={i} q={q} idx={i} />
      )}
    </div>
  );
}
```

要点：
- mc 的 `selected` 是 `number | null`，tf 是 `boolean | null`，各题独立 state，无跨题计分。
- 答错时同时标红选中项（X）+ 标绿正确项（Check），让用户看到答案；可再点改答案。
- `Explanation` 仅在答题后 + 有 explanation 时展开，framer-motion 高度淡入。
- `McQuestion` 不引入 `useLang`（选项文本无中英之分），只 `TfQuestion` 用 `lang` 切「对/错」「True/False」。避免 eslint unused-var。
- 判别联合用 `Extract<QuizQuestion, {type:"mc"}>` 让 TS 在分支内收窄 `answer_idx`/`answer`。

- [ ] **Step 2: 类型检查 + lint**

Run: `cd web && npm run build && npm run lint`
Expected: 两者均 PASS。常见 fail：`'lang' is assigned but never used`（说明误在 McQuestion 引了 useLang，删掉）；`Cannot find name 'Quiz'`（Task 1 未完成）。

- [ ] **Step 3: 提交 types + 组件**

```bash
cd "E:/claudeproject/notegen"
git add web/lib/types.ts web/components/ChapterQuiz.tsx
git commit -m "feat(web): add Quiz types + interactive ChapterQuiz component"
```

---

## Task 3: 接入 NotesContent 章卡

**Files:**
- Modify: `web/components/NotesContent.tsx:8`（import）、`:320-321`（注入点）

- [ ] **Step 1: 加 import**

`web/components/NotesContent.tsx` 第 8 行现为：

```tsx
import GlossaryList from "./GlossaryList";
```

在其后加一行：

```tsx
import ChapterQuiz from "./ChapterQuiz";
```

（`ChevronDown` 已在第 4 行的 lucide-react import 中，无需再加。）

- [ ] **Step 2: 注入折叠 toggle**

定位章卡 chunk chips 的 ternary 结束处。第 320-321 行现为：

```tsx
              )}
            </motion.div>
```

第 320 行 `)}` 闭合的是 `{hasChildren ? (...) : (...)}` 三元；第 321 行 `</motion.div>` 闭合章卡。在这两行**之间**插入 quiz toggle，使其成为：

```tsx
              )}
              {ch.quiz?.questions?.length ? (
                <details className="group mt-3">
                  <summary className="flex cursor-pointer list-none items-center gap-2
                                      text-sm font-semibold text-[var(--fg)]">
                    <ChevronDown
                      size={14}
                      className="transition-transform group-open:rotate-0 -rotate-90"
                    />
                    {lang === "en" ? "🎓 Chapter Quiz" : "🎓 本章自测"}
                    <span className="text-xs font-normal text-[var(--fg-tertiary)]">
                      {ch.quiz.questions.length} {lang === "en" ? "questions" : "题"}
                    </span>
                  </summary>
                  <ChapterQuiz quiz={ch.quiz} />
                </details>
              ) : null}
            </motion.div>
```

要点：
- `<details>` 不带 `open` → 默认折叠，镜像 glossary 折叠块（同文件 327-341 行）的 ChevronDown 旋转交互。
- `ch.quiz?.questions?.length` 短路：无 quiz / 空 questions 的章整块不渲染。
- 放在 chunk chips 之后、章卡闭合之前，对 hasChildren 与 flat 两种章都生效（quiz 挂在顶层章）。
- summary/题数文案跟随 `lang`（`lang` 已在第 29 行 `const { lang } = useLang()` 取到）。

- [ ] **Step 3: 类型检查 + lint**

Run: `cd web && npm run build && npm run lint`
Expected: PASS。若报 `Property 'quiz' does not exist on type 'Chapter'` 说明 Task 1 未生效；若报 `ChapterQuiz` 未定义说明 Step 1 import 漏了。

- [ ] **Step 4: 提交接入**

```bash
cd "E:/claudeproject/notegen"
git add web/components/NotesContent.tsx
git commit -m "feat(web): render chapter quiz toggle in NotesContent"
```

---

## Task 4: 浏览器验收（不 commit，人工走查）

**Files:** 无改动；起 dev server 实测。

- [ ] **Step 1: 起 dev server**

Run: `cd web && npm run dev`
Expected: `Local: http://localhost:3000`（或 3001 若占用）。

- [ ] **Step 2: 走查 p68（中文）**

浏览器开 `http://localhost:3000/notes/BV1BE411D7ii_p68_p0`，滚到章节区。逐项确认：
- 每个有 quiz 的章底部出现折叠的「🎓 本章自测 (N 题)」，**默认收起**。
- 点开展开题目。MC：点选项 → 选对该项标绿✓；选错该项标红✗且正确项也标绿；解析展开。
- TF：点「对/错」→ 反馈同上。
- 再点别的选项 → 答案可改。
- 折叠/展开 ChevronDown 旋转正常。

- [ ] **Step 3: 走查英文 note**

开一个英文 note（如 `http://localhost:3000/notes/EH5jx5qPabU`，若该 note 无 quiz 则任选一个有 quiz 的英文 note；无英文 quiz note 时，在 p68 页右上切到 EN 验证 chrome 文案）。确认：
- 题干按源语言原样显示（不被翻译）。
- 切到 EN：toggle 显示「🎓 Chapter Quiz」「N questions」，TF 按钮显示「True/False」。
- 切回中文：显示「本章自测」「N 题」「对/错」。

- [ ] **Step 4: 走查无 quiz 的章**

开一个 vlog/talk 类 note（无 quiz 字段的章），确认章卡底部**不出现** quiz toggle，无空白块、布局正常。

- [ ] **Step 5: 关 dev server**

确认验收通过后停掉 dev server（Ctrl+C / 关闭后台进程）。

> 若发现视觉/交互问题，回到对应 Task 修复后重跑 build+lint，再重新走查。验收全绿即完成。

---

## Self-Review

**Spec coverage**（对照 `docs/superpowers/specs/2026-06-01-quiz-web-render-design.md`）：
- 3 处改动（types / ChapterQuiz / NotesContent）→ Task 1/2/3 ✓
- 默认折叠 toggle + 条件短路 → Task 3 Step 2 ✓
- MC/TF 点选反馈 + 改答案 + 解析展开 → Task 2 Step 1 ✓
- 双语只动 chrome、题干原样 → Task 2（TfQuestion lang）+ Task 3（summary lang）✓
- 验收 p68 / 英文 / 无 quiz 章 + build → Task 4 ✓
- 非目标（不计分 / 不翻译 / 不碰管线）→ 计划内无相关代码 ✓

**Placeholder scan：** 无 TBD/TODO；每个 code step 含完整代码；命令含预期输出。✓

**Type consistency：** `Quiz`/`QuizQuestion`（Task 1）↔ ChapterQuiz import（Task 2）↔ `ch.quiz`（Task 3）一致；`answer_idx`(mc)/`answer`(tf) 与实测数据键名一致。✓
