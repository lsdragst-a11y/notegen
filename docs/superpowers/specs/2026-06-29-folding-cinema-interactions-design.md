# Folding Cinema Interactions Design

## Context

NoteGen 的现有前端已经形成了三条清晰主线：

- 品牌：折叠笔记页 + 时间播放指针形成 `N`。
- 首页：电影感入口，讲述“导入视频 → 时间线解析 → 笔记生成 → 可追问”。
- 工作台：NotebookLM 式三栏结构，强调阅读、引用、seek、问答效率。

用户选择了 **A. 折叠影院 / Folding Cinema**，并明确反馈“艺术感还不够，需要一些动态的互动性的创新”。因此，本设计不继续增加静态装饰，而是把“视频被折成笔记”升级成一套可参与的动态交互系统。

## Design Goal

让用户在关键路径中感受到同一个品牌动作：

> 视频是一段连续时间，NoteGen 把它折叠成可复习、可追问、可回放的笔记页。

这套互动必须服务产品动作，而不是独立炫技：

- 首页：用户能“亲手”把视频折成笔记。
- 工作台：用户点击引用时，能看到答案回到视频证据。
- 生成流程：用户等待时，能看到视频被逐段接收、解析、归档。

## Approved Direction

主方向：**折叠影院 / Folding Cinema**

视觉道具只保留五类，避免新增无关装饰：

- 折叠纸页：代表笔记、章节、归档。
- 播放指针：代表时间定位、证据回跳。
- 时间胶片：代表视频连续时间。
- 书签/飘带：代表保存、遮挡、确认、进度。
- 证据光线：代表引用从文本回到视频。

辅助气质：吸收少量 **档案工坊 / Archive Atelier** 的温暖纸张与长期复习感。
不把 **记忆星图 / Memory Constellation** 作为全站母题，只允许它在未来的“复习关系”或“问答关联”功能中局部出现。

## Interaction System

### 1. Timeline Fold Scrubber

**Surface:** 首页首屏 / cinematic hero

用户在首页首屏拖动或移动播放指针时，视频帧、章节卡和笔记页发生联动：

- 左侧视频帧随指针推进滑入。
- 中间时间线被播放指针切开。
- 右侧纸页从胶片中折出，形成章节卡和摘要卡。

This makes the hero interactive instead of purely presentational.

**Behavior:**

- Desktop pointer move controls progress from `0` to `1`.
- Touch devices use a draggable horizontal scrubber.
- On first load, play a short auto-demo once, then yield to user control.
- `prefers-reduced-motion: reduce` shows three static states: import, fold, note.

**Component boundary:**

- `FoldingHeroStage`
- `FoldScrubber`
- `FoldedFrameStack`

### 2. Citation Wormhole

**Surface:** note workspace citations, timestamp chips, QA answers

When a user clicks a citation or timestamp, the app already seeks the video. The new interaction visualizes the trace:

- A thin coral beam starts at the clicked citation.
- It travels toward the video player.
- The player shows a brief locating ring at the target time.
- The active chapter rail item gets a synchronized pulse.

**Behavior:**

- Duration: 500-700ms.
- Desktop uses a DOM-rect beam between source and video region.
- Mobile uses local highlight only, because cross-screen beam can feel chaotic.
- Keyboard activation must trigger the same feedback.

**Component boundary:**

- `CitationJumpLayer`
- `useCitationJump`
- `VideoLocatePulse`

### 3. Generation Ritual

**Surface:** create notebook / upload / queue history

Current loading/progress can feel like waiting. The generation ritual turns waiting into visible progress:

- A paper companion “receives” the video.
- A timeline lights up in segments as backend stages run.
- On success, the page folds shut and moves into the notebook library.
- On failure, the page stops at a red timestamp marker with retry affordance.

**Behavior:**

- Maps existing job stages to stable visual states.
- Does not fake progress; unknown progress uses indeterminate timeline shimmer.
- Failure state is calm, not a violent shake.
- Reduced motion swaps folding movement for color/label changes.

**Component boundary:**

- `GenerationCompanion`
- `ProcessingTimeline`
- `JobStageGlyph`

### 4. Evidence Fold Lens

**Surface:** chapter rail, key points, glossary terms, citation chips

Hover/focus on a knowledge item can open a small fold lens:

- One side shows the generated note.
- The other side shows the source timecode, quote, or transcript snippet.
- The fold edge visually connects them.

This reinforces grounded AI without making the workspace noisy.

**Behavior:**

- Trigger on hover, focus, and explicit “view evidence”.
- Delay open by ~120ms to avoid flicker.
- Close on Escape and outside pointer.
- Never obscure the active input area.

**Component boundary:**

- `EvidenceFoldLens`
- `EvidencePreviewCard`

### 5. Living Notebook Deck

**Surface:** `/notebooks`

Notebook cards should feel like small folded video dossiers:

- Hover gently opens the top fold and reveals 2-3 chapter slivers.
- Search/filter changes reorder cards with a soft physical motion.
- Public example cards use “sample reel” treatment; private cards use “personal archive” treatment.

**Behavior:**

- Desktop hover only; mobile remains static.
- Motion must not move layout dimensions.
- Cards reserve visual space to avoid layout shift.

**Component boundary:**

- `NotebookDeckCard`
- `ChapterSliverPreview`

## Motion Rules

Motion is allowed only when it communicates one of these actions:

- fold
- locate
- save
- process
- reveal evidence

Hard limits:

- At most 1-2 active motion subjects per view.
- No looping attention animation in the workspace except active video/playback state.
- No bounce/elastic motion.
- Prefer ease-out for entrances and ease-in for exits.
- Every animation has a reduced-motion fallback.

Suggested timing:

- Micro feedback: 120-180ms.
- Citation jump: 500-700ms.
- Hero fold demo: 1200-1800ms.
- Generation stage transition: 300-450ms.

## Architecture

The interaction system should be additive and isolated:

- Existing `BrandMark`, `AccountCompanion`, `LandingTimelineVisuals`, `NoteWorkspace`, and `ChatPanel` stay intact initially.
- New motion-heavy pieces live in focused components.
- Heavy homepage-only interactions should be dynamically imported if bundle analysis shows cost.
- Workspace interaction layers must not own note data; they only receive event coordinates, note ids, timecodes, and state labels.

Recommended modules:

- `web/components/interactive/FoldingHeroStage.tsx`
- `web/components/interactive/CitationJumpLayer.tsx`
- `web/components/interactive/GenerationCompanion.tsx`
- `web/components/interactive/EvidenceFoldLens.tsx`
- `web/components/interactive/NotebookDeckCard.tsx`
- `web/components/interactive/usePrefersReducedMotion.ts`

## Data Flow

### Homepage

`LandingPage` passes no backend data. `FoldingHeroStage` owns local interaction progress:

`pointer/touch input → progress value → frame stack transform + timeline position + folded page state`

### Workspace Citation Jump

Existing click handlers already know the target time. The new layer adds a visual event:

`citation click → onSeek(time) → dispatchCitationJump({ sourceRect, targetTime }) → video pulse + rail pulse`

The visual event is ephemeral. It should not enter global app state.

### Generation

Existing job/runtime data drives the companion:

`HistoryItem.runtime.metrics + status → visual stage model → ProcessingTimeline + companion state`

If runtime metrics are missing, fall back to `queued`, `running`, `done`, `failed`.

## Accessibility

The dynamic layer must improve perception without making the app harder to use:

- All interactions remain operable by keyboard.
- Citation jump does not rely on color only; active citation and player region also receive focus/label updates.
- `prefers-reduced-motion` disables beams, folding transforms, and continuous loops.
- Generated progress has text labels for queue/running/done/failed states.
- Evidence lens uses `role="dialog"` only when it traps focus; otherwise it remains a non-modal disclosure.

## Performance

Key constraints:

- Animate `transform`, `opacity`, and paint-cheap properties when possible.
- Do not animate layout dimensions.
- Reserve space for dynamic content to avoid CLS.
- Homepage visual stage can be heavier; workspace must remain fast.
- Run bundle analysis before shipping anime.js or another motion library. Current stack already has Framer Motion, so default to existing dependency unless a specific effect clearly requires another library.

## Testing Strategy

Automated tests:

- Unit tests for reduced-motion fallbacks.
- Interaction tests for keyboard activation of citations and evidence lens.
- Contract tests ensuring workspace content is not hidden behind motion layers.
- Regression test for mobile no-horizontal-overflow.

Manual/browser QA:

- Homepage: pointer/touch scrubber, reduced-motion mode, mobile static fallback.
- Workspace: click citation, keyboard activate citation, verify seek still works.
- Generation: queued/running/done/failed visual states.
- Notebook library: card hover on desktop, static behavior on mobile.

## Implementation Phases

### Phase 1: Foundation

- Add shared interaction tokens and motion constants.
- Add reduced-motion utility.
- Add visual layer primitives: paper fold, playhead, locator pulse.

### Phase 2: Homepage Fold Scrubber

- Build `FoldingHeroStage`.
- Replace or augment the current landing cinematic section.
- Validate mobile and reduced-motion behavior.

### Phase 3: Citation Wormhole

- Add visual citation jump layer to `NoteWorkspace`.
- Wire QA citation chips and timestamp links into the visual event.
- Keep existing seek behavior as source of truth.

### Phase 4: Generation Ritual

- Build `GenerationCompanion`.
- Use it in create/history progress surfaces.
- Map backend job states to visual states.

### Phase 5: Optional Polish

- Add Evidence Fold Lens.
- Add Living Notebook Deck hover treatment.
- Run browser smoke and Lighthouse/a11y checks.

## Non-Goals

- Do not turn the workspace into a cinematic scroll experience.
- Do not add continuous decorative particles or generic animated backgrounds.
- Do not introduce anime.js unless Framer Motion cannot express the approved interaction within acceptable bundle cost.
- Do not change backend job semantics for visual polish.

## Open Decision

Recommended first build slice:

1. Timeline Fold Scrubber
2. Citation Wormhole
3. Generation Ritual

This set covers first impression, core learning interaction, and long-running task feedback. Evidence Fold Lens and Living Notebook Deck can follow after the first three prove the motion language works.
