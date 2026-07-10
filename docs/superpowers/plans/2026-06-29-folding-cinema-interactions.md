# Folding Cinema Interactions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the first Folding Cinema interaction slice: an interactive homepage fold scrubber, citation-to-video evidence tracing, and a branded generation progress ritual.

**Architecture:** Add focused client-only interaction components under `web/components/interactive/`. Keep business state in existing page components; new motion components receive only progress, DOM coordinates, timecodes, and status labels. Motion uses the existing `framer-motion` dependency and Warm Fold tokens, with reduced-motion fallbacks for every animated surface.

**Tech Stack:** Next.js 16 App Router, React 19, TypeScript, Tailwind CSS 4 utilities, Framer Motion, Lucide React, Vitest.

---

## File Structure

- Create: `web/components/interactive/motionModel.ts`
  - Pure helpers for fold progress and generation stage mapping.
- Create: `web/components/interactive/FoldingHeroStage.tsx`
  - Client-only homepage hero visual controlled by pointer/touch/range input.
- Create: `web/components/interactive/CitationJumpLayer.tsx`
  - Client-only fixed overlay and hook for ephemeral citation jump visuals.
- Create: `web/components/interactive/GenerationCompanion.tsx`
  - Client-only branded job progress surface driven by existing job events.
- Create: `web/components/interactive/__tests__/motionModel.test.ts`
  - Unit coverage for progress clamping and stage mapping.
- Modify: `web/app/page.tsx`
  - Replace the current static product preview with `FoldingHeroStage`.
- Modify: `web/components/NoteWorkspace.tsx`
  - Wire citation jump visual events to the video panel without changing existing seek behavior.
- Modify: `web/components/ChatPanel.tsx`
  - Pass the clicked citation element into `onSeek` so the overlay can draw from the source chip.
- Modify: `web/app/generate/page.tsx`
  - Replace the generic progress bar/stage chips with `GenerationCompanion`, while preserving diagnostics and redirect behavior.
- Modify: `web/test/setup.ts`
  - Add a stable `matchMedia` shim for reduced-motion tests.
- Create: `PRODUCT.md`
  - Strategic product context required by the design tooling.

## Task 1: Motion Model Foundation

**Files:**
- Create: `web/components/interactive/motionModel.ts`
- Create: `web/components/interactive/__tests__/motionModel.test.ts`
- Modify: `web/test/setup.ts`

- [ ] **Step 1: Add tests for fold and generation state mapping**

Create `web/components/interactive/__tests__/motionModel.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import {
  clampFoldProgress,
  getFoldPhase,
  getGenerationVisualState,
} from "../motionModel";

describe("Folding Cinema motion model", () => {
  it("clamps fold progress to the visual range", () => {
    expect(clampFoldProgress(-1)).toBe(0);
    expect(clampFoldProgress(0.42)).toBe(0.42);
    expect(clampFoldProgress(2)).toBe(1);
  });

  it("maps hero progress to three readable phases", () => {
    expect(getFoldPhase(0.1)).toBe("import");
    expect(getFoldPhase(0.45)).toBe("fold");
    expect(getFoldPhase(0.82)).toBe("note");
  });

  it("maps running jobs to a processing step", () => {
    expect(getGenerationVisualState({ stage: "asr", percent: 38, error: null }).activeStep).toBe("transcribe");
  });

  it("maps terminal states without faking progress", () => {
    expect(getGenerationVisualState({ stage: "done", percent: 88, error: null }).status).toBe("done");
    expect(getGenerationVisualState({ stage: "running", percent: 52, error: "network" }).status).toBe("failed");
  });
});
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```powershell
cd web
npm test -- components/interactive/__tests__/motionModel.test.ts
```

Expected: fail because `motionModel.ts` does not exist.

- [ ] **Step 3: Add the pure motion model**

Create `web/components/interactive/motionModel.ts`:

```ts
export type FoldPhase = "import" | "fold" | "note";
export type GenerationStep = "receive" | "transcribe" | "structure" | "archive";
export type GenerationStatus = "queued" | "running" | "done" | "failed";

export interface GenerationVisualInput {
  stage: string;
  percent: number;
  error: string | null;
}

export interface GenerationVisualState {
  status: GenerationStatus;
  activeStep: GenerationStep;
  safePercent: number;
  label: string;
}

export function clampFoldProgress(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Math.min(1, Math.max(0, value));
}

export function getFoldPhase(progress: number): FoldPhase {
  const safe = clampFoldProgress(progress);
  if (safe < 0.34) return "import";
  if (safe < 0.68) return "fold";
  return "note";
}

export function getGenerationVisualState(input: GenerationVisualInput): GenerationVisualState {
  const stage = input.stage.toLowerCase();
  const safePercent = Math.min(100, Math.max(0, Math.round(input.percent || 0)));

  if (input.error || stage === "failed" || stage === "interrupted" || stage === "error") {
    return { status: "failed", activeStep: "archive", safePercent, label: "处理遇到问题" };
  }

  if (stage === "done") {
    return { status: "done", activeStep: "archive", safePercent: 100, label: "笔记已归档" };
  }

  if (stage.includes("queue") || safePercent < 12) {
    return { status: "queued", activeStep: "receive", safePercent, label: "接收视频" };
  }

  if (stage.includes("asr") || stage.includes("whisper") || safePercent < 60) {
    return { status: "running", activeStep: "transcribe", safePercent, label: "转写声音" };
  }

  if (stage.includes("summary") || stage.includes("chapter") || safePercent < 88) {
    return { status: "running", activeStep: "structure", safePercent, label: "折叠章节" };
  }

  return { status: "running", activeStep: "archive", safePercent, label: "整理归档" };
}
```

- [ ] **Step 4: Add a `matchMedia` test shim**

Append this to `web/test/setup.ts`:

```ts
if (!window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  });
}
```

- [ ] **Step 5: Run focused tests**

Run:

```powershell
cd web
npm test -- components/interactive/__tests__/motionModel.test.ts
```

Expected: pass.

## Task 2: Homepage Timeline Fold Scrubber

**Files:**
- Create: `web/components/interactive/FoldingHeroStage.tsx`
- Modify: `web/app/page.tsx`

- [ ] **Step 1: Implement `FoldingHeroStage`**

Create a client component that uses `useMotionValue` for continuous pointer progress and `useReducedMotion` for the static fallback. The component must expose a range input so touch and keyboard users can control the same fold progress.

Core API:

```ts
export function FoldingHeroStage(): JSX.Element
```

The component renders:

- a film strip on the left
- a central timeline and playhead
- folded note cards on the right
- a visible scrubber input labelled "控制视频折叠进度"

- [ ] **Step 2: Replace `ProductPreview` with the new stage**

In `web/app/page.tsx`, import:

```ts
import { FoldingHeroStage } from "@/components/interactive/FoldingHeroStage";
```

Then replace:

```tsx
<ProductPreview />
```

with:

```tsx
<FoldingHeroStage />
```

Keep the rest of the homepage copy, nav, and section IDs unchanged.

- [ ] **Step 3: Remove unused imports and local preview code**

Remove `Play` from the icon imports if it is no longer used. Remove the `ProductPreview` function only after confirming no references remain.

- [ ] **Step 4: Verify homepage compiles**

Run:

```powershell
cd web
npm run lint -- app/page.tsx components/interactive/FoldingHeroStage.tsx
```

Expected: no lint errors for touched files.

## Task 3: Citation Wormhole

**Files:**
- Create: `web/components/interactive/CitationJumpLayer.tsx`
- Modify: `web/components/NoteWorkspace.tsx`
- Modify: `web/components/ChatPanel.tsx`

- [ ] **Step 1: Add the citation jump hook and layer**

Create `CitationJumpLayer.tsx` with:

```ts
export interface CitationJumpEvent {
  id: number;
  sourceRect: DOMRect;
  targetRect: DOMRect;
  targetTime: number;
}

export function useCitationJump(): {
  jump: CitationJumpEvent | null;
  triggerJump: (source: HTMLElement | null, target: HTMLElement | null, targetTime: number) => void;
};

export function CitationJumpLayer({ jump }: { jump: CitationJumpEvent | null }): JSX.Element | null;
```

The visual layer is fixed, pointer-events-none, and disappears after roughly 700ms. Reduced motion should render only a brief target pulse.

- [ ] **Step 2: Widen `ChatPanel` seek callback**

Change the prop type from:

```ts
onSeek: (sec: number) => void;
```

to:

```ts
onSeek: (sec: number, sourceElement?: HTMLElement | null) => void;
```

Change citation buttons from:

```tsx
onClick={() => onSeek(c.start)}
```

to:

```tsx
onClick={(event) => onSeek(c.start, event.currentTarget)}
```

Keyboard activation still triggers the button click and supplies the same current target.

- [ ] **Step 3: Wire the workspace overlay**

In `NoteWorkspace.tsx`, import:

```ts
import { CitationJumpLayer, useCitationJump } from "@/components/interactive/CitationJumpLayer";
```

Create:

```ts
const { jump, triggerJump } = useCitationJump();

const seekFromCitation = useCallback((sec: number, sourceElement?: HTMLElement | null) => {
  seek(sec);
  triggerJump(sourceElement ?? null, mainWrapRef.current, sec);
}, [seek, triggerJump]);
```

Pass `seekFromCitation` only to `ChatPanel`. Keep existing `seek` for chapter rail, transcript, keyboard shortcuts, and mini player.

Render the overlay near the bottom of the main component:

```tsx
<CitationJumpLayer jump={jump} />
```

- [ ] **Step 4: Verify no business behavior changed**

Run:

```powershell
cd web
npm test -- test/note-workspace-layout.test.ts
```

Expected: pass.

## Task 4: Generation Ritual

**Files:**
- Create: `web/components/interactive/GenerationCompanion.tsx`
- Modify: `web/app/generate/page.tsx`

- [ ] **Step 1: Implement `GenerationCompanion`**

Component API:

```ts
export interface GenerationCompanionProps {
  stage: string;
  percent: number;
  error: string | null;
  message: string;
  title?: string;
  elapsed: number;
}

export function GenerationCompanion(props: GenerationCompanionProps): JSX.Element
```

The component uses `getGenerationVisualState` and renders:

- a paper companion receiving/folding/archiving state
- four stage chips: 接收视频, 转写声音, 折叠章节, 整理归档
- a progress timeline that uses real backend percent only
- a calm failure marker when `error` is present

- [ ] **Step 2: Replace the generic generate progress area**

In `web/app/generate/page.tsx`, import:

```ts
import { GenerationCompanion } from "@/components/interactive/GenerationCompanion";
```

After the title/message/meta block, render:

```tsx
<GenerationCompanion
  stage={progress.stage}
  percent={progress.percent}
  error={error}
  message={error ?? progress.msg}
  title={meta.videoTitle}
  elapsed={elapsed}
/>
```

Remove the old progress bar and four generic stage chips from the card to avoid duplicate progress language. Keep metrics, history details, failure retry navigation, and redirect timing unchanged.

- [ ] **Step 3: Verify generation page compiles**

Run:

```powershell
cd web
npm run lint -- app/generate/page.tsx components/interactive/GenerationCompanion.tsx
```

Expected: no lint errors for touched files.

## Task 5: Full Verification And Browser Check

**Files:**
- No new files expected.

- [ ] **Step 1: Run the focused Vitest set**

Run:

```powershell
cd web
npm test -- components/interactive/__tests__/motionModel.test.ts test/note-workspace-layout.test.ts app/__tests__/landing-model.test.ts
```

Expected: pass.

- [ ] **Step 2: Run lint**

Run:

```powershell
cd web
npm run lint
```

Expected: pass or only pre-existing warnings that are unrelated to touched files.

- [ ] **Step 3: Run production build**

Run:

```powershell
cd web
npm run build
```

Expected: Next.js build succeeds.

- [ ] **Step 4: Browser smoke**

Run the dev server and inspect:

```powershell
cd web
npm run dev
```

Open:

- `/` and scrub the hero timeline with pointer and range input.
- `/generate?job=missing` and verify the failure state is calm and readable.
- one existing `/notes/[id]` route, click a QA citation when available, and verify the seek still happens.

Expected: no console errors from the new components, no mobile horizontal overflow, and reduced-motion mode degrades to static or local highlights.
