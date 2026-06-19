# NoteGen Warm Fold P0 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved Warm Fold brand assets, font variables, light/dark semantic tokens, and accessible visual primitive components without migrating or restyling existing business pages.

**Architecture:** Add a new `--wf-*` semantic layer beside the untouched legacy design system. Generate reproducible SVG assets and outlined wordmark geometry from the approved logo construction, then render the same geometry through `BrandMark`. Implement small native-element React primitives that depend only on Warm Fold tokens and protect them with focused tests and migration guards.

**Tech Stack:** Next.js 16, React 19, TypeScript, Tailwind CSS 4 global CSS, `next/font`, clsx, Lucide React, Vitest, React Testing Library, jsdom, opentype.js.

---

## Execution Guardrails

The worktree is already dirty. In particular, `web/app/layout.tsx` and `web/app/globals.css` contain user changes that are not part of P0.

- Never run `git add .`, `git add -A`, `git checkout --`, `git reset --hard`, or `git restore`.
- Snapshot the two dirty target files before editing.
- Edit the current working files so the user's changes remain present locally.
- When committing those two files, build the staged blob from `HEAD` plus only the marked P0 additions. Do not stage their complete working-tree versions.
- Stage all new P0 files by explicit path.
- Do not modify any business page or existing business component.

Final allowed implementation paths:

```txt
web/app/layout.tsx
web/app/globals.css
web/package.json
web/package-lock.json
web/public/brand/**
web/components/brand/**
web/components/ui/**
web/test/**
web/vitest.config.ts
web/scripts/build-brand-assets.mjs
web/scripts/validate-warm-fold.mjs
```

## Task 1: Protect The Dirty Worktree And Install The Test Harness

**Files:**
- Modify: `web/package.json`
- Modify: `web/package-lock.json`
- Create: `web/vitest.config.ts`
- Create: `web/test/setup.ts`
- Create: `web/test/setup.test.ts`

- [ ] **Step 1: Snapshot the dirty target files outside the source tree**

Run from the repository root:

```powershell
New-Item -ItemType Directory -Force .codex-run/p0-baseline | Out-Null
Copy-Item web/app/layout.tsx .codex-run/p0-baseline/layout.tsx
Copy-Item web/app/globals.css .codex-run/p0-baseline/globals.css
Get-FileHash .codex-run/p0-baseline/layout.tsx, .codex-run/p0-baseline/globals.css -Algorithm SHA256
```

Expected: two SHA256 hashes and no source-file changes.

- [ ] **Step 2: Create the temporary partial-staging helper**

Create `.codex-run/stage-p0.ps1` with this exact content. Keep it untracked:

```powershell
param(
  [Parameter(Mandatory = $true)]
  [ValidateSet("fonts", "tokens", "buttons", "surfaces")]
  [string[]]$Part
)

$ErrorActionPreference = "Stop"

function Get-HeadFile([string]$Path) {
  $lines = git show "HEAD:$Path"
  if ($LASTEXITCODE -ne 0) { throw "Cannot read HEAD:$Path" }
  return ([string]::Join("`n", $lines) + "`n")
}

function Get-MarkedBlock([string]$Path, [string]$Name) {
  $source = Get-Content -Raw -Encoding UTF8 $Path
  $startMarker = "/* === $Name`: START === */"
  $endMarker = "/* === $Name`: END === */"
  $start = $source.IndexOf($startMarker)
  $end = $source.IndexOf($endMarker)
  if ($start -lt 0 -or $end -lt $start) { throw "Missing marked block: $Name" }
  $end += $endMarker.Length
  return $source.Substring($start, $end - $start)
}

function Stage-Content([string]$Path, [string]$Content) {
  $blob = $Content | git hash-object -w --stdin
  if ($LASTEXITCODE -ne 0) { throw "Cannot create blob for $Path" }
  git update-index --add --cacheinfo 100644 $blob $Path
  if ($LASTEXITCODE -ne 0) { throw "Cannot stage $Path" }
}

if ($Part -contains "fonts") {
  $layout = Get-HeadFile "web/app/layout.tsx"
  $layout = $layout.Replace(
    'import type { Metadata } from "next";',
    "import type { Metadata } from `"next`";`nimport { DM_Sans, DM_Serif_Display } from `"next/font/google`";"
  )
  $fontDeclarations = @'
const dmSans = DM_Sans({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-dm-sans",
});

const dmSerifDisplay = DM_Serif_Display({
  subsets: ["latin"],
  weight: "400",
  display: "swap",
  variable: "--font-dm-serif-display",
});
'@
  $layout = $layout.Replace("export const metadata: Metadata = {", "$fontDeclarations`n`nexport const metadata: Metadata = {")
  $layout = $layout.Replace(
    '<html lang="zh-CN" className="h-full antialiased" suppressHydrationWarning>',
    '<html lang="zh-CN" className={`h-full antialiased ${dmSans.variable} ${dmSerifDisplay.variable}`} suppressHydrationWarning>'
  )
  Stage-Content "web/app/layout.tsx" $layout
}

$cssParts = @(
  @{ Key = "tokens"; Name = "Warm Fold foundation tokens" },
  @{ Key = "buttons"; Name = "Warm Fold button primitives" },
  @{ Key = "surfaces"; Name = "Warm Fold surface primitives" }
)

foreach ($cssPart in $cssParts) {
  if ($Part -contains $cssPart.Key) {
    $headCss = Get-HeadFile "web/app/globals.css"
    $block = Get-MarkedBlock "web/app/globals.css" $cssPart.Name
    Stage-Content "web/app/globals.css" ($headCss.TrimEnd() + "`n`n" + $block + "`n")
  }
}
```

Run:

```powershell
git status --short -- .codex-run/stage-p0.ps1
```

Expected: the helper is untracked under the existing `.codex-run/` workspace and will never be staged.

- [ ] **Step 3: Install exact development dependencies and add scripts**

Run:

```powershell
cd web
npm install --save-dev vitest@4.1.9 @testing-library/react@16.3.2 @testing-library/jest-dom@6.9.1 jsdom@29.1.1 opentype.js@2.0.0 @fontsource/dm-serif-display@5.2.8
npm pkg set scripts.test="vitest run"
npm pkg set scripts.brand:build="node scripts/build-brand-assets.mjs"
npm pkg set scripts.validate:warm-fold="node scripts/validate-warm-fold.mjs"
```

Expected: only `web/package.json` and `web/package-lock.json` change.

- [ ] **Step 4: Create the Vitest configuration**

Create `web/vitest.config.ts`:

```ts
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL(".", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./test/setup.ts"],
    include: ["**/*.test.{ts,tsx}"],
    css: true,
  },
});
```

Create `web/test/setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";
```

Create `web/test/setup.test.ts`:

```ts
import { describe, expect, it } from "vitest";

describe("Vitest setup", () => {
  it("provides a jsdom document", () => {
    expect(document.createElement("button")).toBeInstanceOf(HTMLButtonElement);
  });
});
```

- [ ] **Step 5: Run the harness test**

Run:

```powershell
npm test -- test/setup.test.ts
```

Expected: 1 test passes.

- [ ] **Step 6: Commit the test harness**

Run:

```powershell
git add web/package.json web/package-lock.json web/vitest.config.ts web/test/setup.ts web/test/setup.test.ts
git diff --cached --check
git commit -m "test: add Warm Fold component test harness"
```

## Task 2: Add Font Variables And Warm Fold Tokens Without Staging User Changes

**Files:**
- Modify: `web/app/layout.tsx`
- Modify: `web/app/globals.css`
- Create: `web/test/warm-fold-tokens.test.ts`

- [ ] **Step 1: Write the failing token and typography tests**

Create `web/test/warm-fold-tokens.test.ts`:

```ts
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
const layout = readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");

const requiredTokens = {
  "--wf-canvas": ["#F6F0E7", "#1E1A17"],
  "--wf-surface": ["#FFFAF3", "#28221E"],
  "--wf-surface-muted": ["#EDE2D6", "#352D27"],
  "--wf-text": ["#2D2925", "#F4EADF"],
  "--wf-text-secondary": ["#665D55", "#CBBCAF"],
  "--wf-text-tertiary": ["#877A6E", "#A19184"],
  "--wf-brand-coral": ["#B65C3A", "#E47B59"],
  "--wf-accent": ["#A34A2F", "#E47B59"],
  "--wf-danger": ["#B43A31", "#FF8A7A"],
} as const;

function luminance(hex: string) {
  const channels = hex.slice(1).match(/../g)!.map((value) => parseInt(value, 16) / 255);
  const [r, g, b] = channels.map((value) =>
    value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4,
  );
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string) {
  const first = luminance(a);
  const second = luminance(b);
  return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
}

function selectorBlock(selector: string) {
  const start = css.indexOf(selector);
  expect(start).toBeGreaterThanOrEqual(0);
  const open = css.indexOf("{", start);
  let depth = 0;
  for (let index = open; index < css.length; index += 1) {
    if (css[index] === "{") depth += 1;
    if (css[index] === "}" && --depth === 0) return css.slice(start, index + 1);
  }
  throw new Error(`Unclosed selector: ${selector}`);
}

describe("Warm Fold foundation", () => {
  it("loads both DM font variables without replacing the body font", () => {
    expect(layout).toContain('DM_Sans');
    expect(layout).toContain('DM_Serif_Display');
    expect(layout).toContain('--font-dm-sans');
    expect(layout).toContain('--font-dm-serif-display');
    expect(css).toContain('font-family: -apple-system');
  });

  it("declares every required light and dark token value", () => {
    for (const [token, values] of Object.entries(requiredTokens)) {
      for (const value of values) expect(css).toContain(`${token}: ${value}`);
    }
  });

  it("keeps legacy classes independent from Warm Fold", () => {
    const selectors = [".apple-card {", ".apple-button {", ".tag-chip {"];
    const legacy = selectors.map(selectorBlock).join("\n");
    expect(legacy).not.toContain("--wf-");
    expect(createHash("sha256").update(legacy).digest("hex")).toHaveLength(64);
  });

  it("meets AA contrast for critical light-theme pairs", () => {
    expect(contrast("#2D2925", "#F6F0E7")).toBeGreaterThanOrEqual(4.5);
    expect(contrast("#665D55", "#FFFAF3")).toBeGreaterThanOrEqual(4.5);
    expect(contrast("#A34A2F", "#F6F0E7")).toBeGreaterThanOrEqual(4.5);
    expect(contrast("#FFFAF3", "#A34A2F")).toBeGreaterThanOrEqual(4.5);
  });

  it("meets AA contrast for critical dark-theme pairs", () => {
    expect(contrast("#F4EADF", "#1E1A17")).toBeGreaterThanOrEqual(4.5);
    expect(contrast("#CBBCAF", "#28221E")).toBeGreaterThanOrEqual(4.5);
    expect(contrast("#E47B59", "#28221E")).toBeGreaterThanOrEqual(4.5);
    expect(contrast("#2B1710", "#E47B59")).toBeGreaterThanOrEqual(4.5);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
cd web
npm test -- test/warm-fold-tokens.test.ts
```

Expected: failures for missing DM imports and missing `--wf-*` declarations.

- [ ] **Step 3: Add only font variables to the current layout**

Add this import to `web/app/layout.tsx` without changing the existing `Script`, providers, or structure:

```ts
import { DM_Sans, DM_Serif_Display } from "next/font/google";
```

Add these constants before `metadata`:

```ts
const dmSans = DM_Sans({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-dm-sans",
});

const dmSerifDisplay = DM_Serif_Display({
  subsets: ["latin"],
  weight: "400",
  display: "swap",
  variable: "--font-dm-serif-display",
});
```

Change only the existing `html` class expression:

```tsx
<html
  lang="zh-CN"
  className={`h-full antialiased ${dmSans.variable} ${dmSerifDisplay.variable}`}
  suppressHydrationWarning
>
```

- [ ] **Step 4: Append the complete token layer**

Append this marked block to `web/app/globals.css`; do not edit any existing selector:

```css
/* === Warm Fold foundation tokens: START === */
:root {
  --wf-canvas: #F6F0E7;
  --wf-surface: #FFFAF3;
  --wf-surface-muted: #EDE2D6;
  --wf-text: #2D2925;
  --wf-text-secondary: #665D55;
  --wf-text-tertiary: #877A6E;
  --wf-brand-coral: #B65C3A;
  --wf-accent: #A34A2F;
  --wf-accent-hover: #98492F;
  --wf-accent-active: #7F3927;
  --wf-on-accent: #FFFAF3;
  --wf-caramel: #8B5A35;
  --wf-border: rgba(45, 41, 37, 0.14);
  --wf-border-strong: rgba(45, 41, 37, 0.28);
  --wf-danger: #B43A31;
  --wf-danger-hover: #9F2E27;
  --wf-danger-active: #81241F;
  --wf-on-danger: #FFFAF3;
  --wf-danger-surface: #F9E2DE;
  --wf-danger-border: #D98073;
  --wf-disabled-bg: #E3D8CC;
  --wf-disabled-fg: #877A6E;
  --wf-disabled-border: rgba(45, 41, 37, 0.10);
  --wf-focus: #A34A2F;
  --wf-shadow-sm: 0 1px 2px rgba(92, 58, 36, 0.08);
  --wf-shadow-md: 0 8px 24px rgba(92, 58, 36, 0.10);
  --wf-shadow-lg: 0 18px 48px rgba(72, 43, 28, 0.14);
  --wf-radius-xs: 8px;
  --wf-radius-sm: 12px;
  --wf-radius-md: 18px;
  --wf-radius-lg: 24px;
  --wf-radius-full: 999px;
  --wf-motion-fast: 160ms;
  --wf-motion-normal: 220ms;
  --wf-motion-enter: 420ms;
  --wf-ease: cubic-bezier(0.22, 1, 0.36, 1);
  --wf-font-display: var(--font-dm-serif-display), Georgia, "Songti SC", serif;
  --wf-font-sans: var(--font-dm-sans), "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", system-ui, sans-serif;
  --wf-font-zh: "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", system-ui, sans-serif;
}

:root[data-theme="dark"] {
  --wf-canvas: #1E1A17;
  --wf-surface: #28221E;
  --wf-surface-muted: #352D27;
  --wf-text: #F4EADF;
  --wf-text-secondary: #CBBCAF;
  --wf-text-tertiary: #A19184;
  --wf-brand-coral: #E47B59;
  --wf-accent: #E47B59;
  --wf-accent-hover: #F08D6B;
  --wf-accent-active: #C96343;
  --wf-on-accent: #2B1710;
  --wf-caramel: #D3A173;
  --wf-border: rgba(244, 234, 223, 0.14);
  --wf-border-strong: rgba(244, 234, 223, 0.28);
  --wf-danger: #FF8A7A;
  --wf-danger-hover: #FFA094;
  --wf-danger-active: #E56E61;
  --wf-on-danger: #2D1210;
  --wf-danger-surface: #422521;
  --wf-danger-border: #A94E45;
  --wf-disabled-bg: #3B332D;
  --wf-disabled-fg: #A19184;
  --wf-disabled-border: rgba(244, 234, 223, 0.10);
  --wf-focus: #E47B59;
  --wf-shadow-sm: 0 1px 2px rgba(10, 7, 5, 0.32);
  --wf-shadow-md: 0 6px 18px rgba(10, 7, 5, 0.38);
  --wf-shadow-lg: 0 14px 36px rgba(10, 7, 5, 0.48);
}

@media (prefers-reduced-motion: reduce) {
  :root {
    --wf-motion-fast: 0ms;
    --wf-motion-normal: 0ms;
    --wf-motion-enter: 0ms;
  }
}
/* === Warm Fold foundation tokens: END === */
```

- [ ] **Step 5: Run the token tests**

Run:

```powershell
npm test -- test/warm-fold-tokens.test.ts
npx tsc --noEmit
```

Expected: all token tests pass and TypeScript exits 0.

- [ ] **Step 6: Stage only the P0 versions of the two dirty files**

Run the exact helper created in Task 1, then stage the test normally:

```powershell
.codex-run/stage-p0.ps1 -Part fonts,tokens
git add web/test/warm-fold-tokens.test.ts
git diff --cached -- web/app/layout.tsx web/app/globals.css web/test/warm-fold-tokens.test.ts
```

Expected: the cached diff contains font variables, the marked Warm Fold token block, and the new test. It must not contain the pre-existing `Script` or NotebookLM legacy-token changes.

- [ ] **Step 7: Commit fonts and tokens**

Run:

```powershell
git diff --cached --check
git commit -m "feat: add Warm Fold fonts and semantic tokens"
```

## Task 3: Generate Formal SVG Assets And Implement BrandMark

**Files:**
- Create: `web/scripts/build-brand-assets.mjs`
- Create: `web/public/brand/brand-mark.svg`
- Create: `web/public/brand/brand-logo.svg`
- Create: `web/public/brand/favicon.svg`
- Create: `web/components/brand/brandPaths.ts`
- Create: `web/components/brand/BrandMark.tsx`
- Create: `web/components/brand/__tests__/BrandMark.test.tsx`

- [ ] **Step 1: Write the failing BrandMark test**

Create `web/components/brand/__tests__/BrandMark.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BrandMark } from "../BrandMark";

describe("BrandMark", () => {
  it("is decorative without a label", () => {
    const { container } = render(<BrandMark className="brand" />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(svg).toHaveClass("brand");
  });

  it("exposes an accessible name when labeled", () => {
    render(<BrandMark variant="full" size="sm" label="NoteGen home" />);
    expect(screen.getByRole("img", { name: "NoteGen home" })).toBeInTheDocument();
  });

  it("uses currentColor for ink and the brand token for the pointer", () => {
    const { container } = render(<BrandMark label="NoteGen" />);
    expect(container.querySelector('[data-part="ink"]')).toHaveAttribute("fill", "currentColor");
    expect(container.querySelector('[data-part="pointer"]')).toHaveAttribute(
      "fill",
      "var(--wf-brand-coral, #B65C3A)",
    );
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
npm test -- components/brand/__tests__/BrandMark.test.tsx
```

Expected: module resolution fails because `BrandMark.tsx` does not exist.

- [ ] **Step 3: Create the deterministic asset generator**

Create `web/scripts/build-brand-assets.mjs`:

```js
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import opentype from "opentype.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const outDir = path.join(root, "public", "brand");
const componentDir = path.join(root, "components", "brand");
const fontFile = path.join(
  root,
  "node_modules",
  "@fontsource",
  "dm-serif-display",
  "files",
  "dm-serif-display-latin-400-normal.woff",
);

fs.mkdirSync(outDir, { recursive: true });
fs.mkdirSync(componentDir, { recursive: true });

const inkPaths = [
  "M8 6L25 14V40L8 58Z",
  "M39 26L56 18V48L39 58Z",
];
const foldPaths = ["M8 6L25 14L20 20Z", "M39 26L56 18L47 31Z"];
const pointerBand = "M23 19L42 36V46L23 29Z";
const pointerTriangle = "M43 44L51 49L43 54Z";

const font = opentype.loadSync(fontFile);
const wordmark = font.getPath("NoteGen", 74, 47, 46);
const wordmarkPath = wordmark.toPathData(3);
const wordmarkBounds = wordmark.getBoundingBox();
const logoWidth = Math.ceil(wordmarkBounds.x2 + 8);

const markPaths = `
  <path fill="#2D2925" d="${inkPaths.join(" ")}"/>
  <path fill="#8B5A35" d="${foldPaths.join(" ")}"/>
  <path fill="#B65C3A" d="${pointerBand}"/>
  <path fill="#B65C3A" d="${pointerTriangle}"/>`;

const svg = (viewBox, body, attrs = "") =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox}" ${attrs}>${body}\n</svg>\n`;

fs.writeFileSync(path.join(outDir, "brand-mark.svg"), svg("0 0 64 64", markPaths, 'data-min-size="16"'));
fs.writeFileSync(
  path.join(outDir, "brand-logo.svg"),
  svg(
    `0 0 ${logoWidth} 64`,
    `${markPaths}\n  <path fill="#2D2925" d="${wordmarkPath}"/>`,
    'data-min-width="120"',
  ),
);
fs.writeFileSync(
  path.join(outDir, "favicon.svg"),
  svg(
    "0 0 64 64",
    `\n  <path fill="#2D2925" d="${inkPaths.join(" ")}"/>\n  <path fill="#B65C3A" d="${pointerBand} ${pointerTriangle}"/>`,
    'data-min-size="16"',
  ),
);

const ts = `// Generated by scripts/build-brand-assets.mjs.\n` +
  `export const INK_PATHS = ${JSON.stringify(inkPaths)} as const;\n` +
  `export const FOLD_PATHS = ${JSON.stringify(foldPaths)} as const;\n` +
  `export const POINTER_BAND = ${JSON.stringify(pointerBand)};\n` +
  `export const POINTER_TRIANGLE = ${JSON.stringify(pointerTriangle)};\n` +
  `export const WORDMARK_PATH = ${JSON.stringify(wordmarkPath)};\n` +
  `export const LOGO_WIDTH = ${logoWidth};\n` +
  `export const LOGO_VIEWBOX = ${JSON.stringify(`0 0 ${logoWidth} 64`)};\n`;
fs.writeFileSync(path.join(componentDir, "brandPaths.ts"), ts);
```

Run:

```powershell
npm run brand:build
```

Expected: three SVG files and `brandPaths.ts` are generated.

- [ ] **Step 4: Implement BrandMark**

Create `web/components/brand/BrandMark.tsx`:

```tsx
import { useId } from "react";
import clsx from "clsx";
import {
  FOLD_PATHS,
  INK_PATHS,
  LOGO_VIEWBOX,
  LOGO_WIDTH,
  POINTER_BAND,
  POINTER_TRIANGLE,
  WORDMARK_PATH,
} from "./brandPaths";

export type BrandMarkProps = {
  variant?: "full" | "mark";
  size?: "sm" | "md" | "lg";
  label?: string;
  className?: string;
};

const markSize = { sm: 16, md: 24, lg: 32 } as const;
const logoWidth = { sm: 120, md: 160, lg: 220 } as const;

export function BrandMark({
  variant = "mark",
  size = "md",
  label,
  className,
}: BrandMarkProps) {
  const titleId = useId();
  const width = variant === "full" ? logoWidth[size] : markSize[size];
  const height = variant === "full" ? Math.round((width * 64) / LOGO_WIDTH) : width;

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox={variant === "full" ? LOGO_VIEWBOX : "0 0 64 64"}
      width={width}
      height={height}
      className={clsx("wf-brand-mark", className)}
      role={label ? "img" : undefined}
      aria-labelledby={label ? titleId : undefined}
      aria-hidden={label ? undefined : true}
    >
      {label && <title id={titleId}>{label}</title>}
      <g data-part="ink" fill="currentColor">
        {INK_PATHS.map((path) => <path key={path} d={path} />)}
      </g>
      <g fill="var(--wf-caramel, #8B5A35)">
        {FOLD_PATHS.map((path) => <path key={path} d={path} />)}
      </g>
      <g data-part="pointer" fill="var(--wf-brand-coral, #B65C3A)">
        <path d={POINTER_BAND} />
        <path d={POINTER_TRIANGLE} />
      </g>
      {variant === "full" && <path fill="currentColor" d={WORDMARK_PATH} />}
    </svg>
  );
}
```

- [ ] **Step 5: Run BrandMark tests**

Run:

```powershell
npm test -- components/brand/__tests__/BrandMark.test.tsx
npx tsc --noEmit
```

Expected: 3 tests pass and TypeScript exits 0.

- [ ] **Step 6: Commit the brand system**

Run:

```powershell
git add web/scripts/build-brand-assets.mjs web/public/brand web/components/brand
git diff --cached --check
git commit -m "feat: add Warm Fold brand assets"
```

## Task 4: Implement Button And IconButton With TDD

**Files:**
- Create: `web/components/ui/Button.tsx`
- Create: `web/components/ui/IconButton.tsx`
- Create: `web/components/ui/__tests__/Button.test.tsx`
- Create: `web/components/ui/__tests__/IconButton.test.tsx`
- Modify: `web/app/globals.css`

- [ ] **Step 1: Write failing behavior tests**

Create `web/components/ui/__tests__/Button.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Button } from "../Button";

describe("Button", () => {
  it("defaults to a non-submitting button", () => {
    render(<Button>Save</Button>);
    expect(screen.getByRole("button", { name: "Save" })).toHaveAttribute("type", "button");
  });

  it("allows submit explicitly", () => {
    render(<Button type="submit">Submit</Button>);
    expect(screen.getByRole("button", { name: "Submit" })).toHaveAttribute("type", "submit");
  });

  it("preserves text and blocks interaction while loading", () => {
    const onClick = vi.fn();
    render(<Button loading onClick={onClick}>Generate notes</Button>);
    const button = screen.getByRole("button", { name: "Generate notes" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button.querySelector('[aria-hidden="true"]')).toBeInTheDocument();
    expect(button.querySelector(".wf-button__content")).toHaveTextContent("Generate notes");
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });
});
```

Create `web/components/ui/__tests__/IconButton.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { IconButton } from "../IconButton";

describe("IconButton", () => {
  it("requires and exposes its accessible label", () => {
    render(<IconButton aria-label="Delete note"><span>×</span></IconButton>);
    expect(screen.getByRole("button", { name: "Delete note" })).toHaveAttribute("type", "button");
  });

  it("keeps its label while loading", () => {
    render(<IconButton aria-label="Delete note" loading><span>×</span></IconButton>);
    expect(screen.getByRole("button", { name: "Delete note" })).toHaveAttribute("aria-busy", "true");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
npm test -- components/ui/__tests__/Button.test.tsx components/ui/__tests__/IconButton.test.tsx
```

Expected: both component modules are missing.

- [ ] **Step 3: Implement Button**

Create `web/components/ui/Button.tsx`:

```tsx
import { forwardRef, type ButtonHTMLAttributes } from "react";
import { LoaderCircle } from "lucide-react";
import clsx from "clsx";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, children, disabled, loading = false, size = "md", type = "button", variant = "primary", ...props },
  ref,
) {
  return (
    <button
      {...props}
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      data-loading={loading || undefined}
      data-size={size}
      data-variant={variant}
      className={clsx("wf-button", className)}
    >
      <span className="wf-button__content">{children}</span>
      {loading && <LoaderCircle className="wf-button__spinner" aria-hidden="true" focusable="false" />}
    </button>
  );
});
```

- [ ] **Step 4: Implement IconButton**

Create `web/components/ui/IconButton.tsx`:

```tsx
import { forwardRef, type ButtonHTMLAttributes } from "react";
import { LoaderCircle } from "lucide-react";
import clsx from "clsx";

type NativeIconButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "aria-label">;

export interface IconButtonProps extends NativeIconButtonProps {
  "aria-label": string;
  variant?: "ghost" | "secondary" | "danger";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { className, children, disabled, loading = false, size = "md", type = "button", variant = "ghost", ...props },
  ref,
) {
  return (
    <button
      {...props}
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      data-loading={loading || undefined}
      data-size={size}
      data-variant={variant}
      className={clsx("wf-icon-button", className)}
    >
      <span className="wf-icon-button__content">{children}</span>
      {loading && <LoaderCircle className="wf-icon-button__spinner" aria-hidden="true" focusable="false" />}
    </button>
  );
});
```

- [ ] **Step 5: Append Button and IconButton styles**

Append this complete marked block to `web/app/globals.css`:

```css
/* === Warm Fold button primitives: START === */
.wf-button, .wf-icon-button { position: relative; display: inline-flex; align-items: center; justify-content: center; border: 1px solid transparent; font-family: var(--wf-font-sans); font-weight: 600; cursor: pointer; transition: background var(--wf-motion-fast) var(--wf-ease), border-color var(--wf-motion-fast) var(--wf-ease), color var(--wf-motion-fast) var(--wf-ease), transform var(--wf-motion-fast) var(--wf-ease); }
.wf-button { gap: 0.5rem; border-radius: var(--wf-radius-sm); }
.wf-button[data-size="sm"] { min-height: 36px; padding: 0.5rem 0.75rem; font-size: 0.8125rem; }
.wf-button[data-size="md"] { min-height: 44px; padding: 0.625rem 1rem; font-size: 0.9375rem; }
.wf-button[data-size="lg"] { min-height: 48px; padding: 0.75rem 1.25rem; font-size: 1rem; }
.wf-button[data-variant="primary"] { background: var(--wf-accent); color: var(--wf-on-accent); }
.wf-button[data-variant="primary"]:hover:not(:disabled) { background: var(--wf-accent-hover); }
.wf-button[data-variant="primary"]:active:not(:disabled) { background: var(--wf-accent-active); }
.wf-button[data-variant="secondary"], .wf-icon-button[data-variant="secondary"] { background: var(--wf-surface); border-color: var(--wf-border); color: var(--wf-text); }
.wf-button[data-variant="ghost"], .wf-icon-button[data-variant="ghost"] { background: transparent; color: var(--wf-text-secondary); }
.wf-button[data-variant="secondary"]:hover:not(:disabled), .wf-icon-button[data-variant="secondary"]:hover:not(:disabled) { background: var(--wf-surface-muted); border-color: var(--wf-border-strong); }
.wf-button[data-variant="ghost"]:hover:not(:disabled), .wf-icon-button[data-variant="ghost"]:hover:not(:disabled) { background: var(--wf-surface-muted); color: var(--wf-text); }
.wf-button[data-variant="danger"], .wf-icon-button[data-variant="danger"] { background: var(--wf-danger); color: var(--wf-on-danger); }
.wf-button[data-variant="danger"]:hover:not(:disabled), .wf-icon-button[data-variant="danger"]:hover:not(:disabled) { background: var(--wf-danger-hover); }
.wf-button:focus-visible, .wf-icon-button:focus-visible { outline: 2px solid var(--wf-focus); outline-offset: 3px; }
.wf-button:disabled, .wf-icon-button:disabled { background: var(--wf-disabled-bg); border-color: var(--wf-disabled-border); color: var(--wf-disabled-fg); cursor: not-allowed; box-shadow: none; }
.wf-button[data-loading="true"], .wf-icon-button[data-loading="true"] { cursor: progress; }
.wf-button[data-loading="true"] .wf-button__content, .wf-icon-button[data-loading="true"] .wf-icon-button__content { opacity: 0; }
.wf-button__spinner, .wf-icon-button__spinner { position: absolute; width: 1em; height: 1em; animation: wf-spin 800ms linear infinite; }
.wf-icon-button { width: 44px; height: 44px; padding: 0; border-radius: var(--wf-radius-sm); }
.wf-icon-button[data-size="lg"] { width: 48px; height: 48px; }
@keyframes wf-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .wf-button__spinner, .wf-icon-button__spinner { animation-duration: 1600ms; } }
/* === Warm Fold button primitives: END === */
```

- [ ] **Step 6: Run tests and commit only the P0 CSS block**

Run:

```powershell
npm test -- components/ui/__tests__/Button.test.tsx components/ui/__tests__/IconButton.test.tsx
npx tsc --noEmit
```

Stage the new files normally. Stage `globals.css` through the helper so the existing user changes remain unstaged.

```powershell
.codex-run/stage-p0.ps1 -Part buttons
git add web/components/ui/Button.tsx web/components/ui/IconButton.tsx web/components/ui/__tests__/Button.test.tsx web/components/ui/__tests__/IconButton.test.tsx
git diff --cached --check
git commit -m "feat: add Warm Fold button primitives"
```

## Task 5: Implement Card, Input, And Chip With TDD

**Files:**
- Create: `web/components/ui/Card.tsx`
- Create: `web/components/ui/Input.tsx`
- Create: `web/components/ui/Chip.tsx`
- Create: `web/components/ui/__tests__/surface-primitives.test.tsx`
- Create: `web/test/ui-types.tsx`
- Modify: `web/app/globals.css`

- [ ] **Step 1: Write failing tests**

Create `web/components/ui/__tests__/surface-primitives.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Card } from "../Card";
import { Chip } from "../Chip";
import { Input } from "../Input";

describe("surface primitives", () => {
  it("keeps Card semantically neutral", () => {
    const { container } = render(<Card variant="outlined">Notes</Card>);
    expect(container.firstChild).toHaveAttribute("data-variant", "outlined");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("keeps Chip presentational", () => {
    render(<Chip variant="accent">Course</Chip>);
    expect(screen.getByText("Course").tagName).toBe("SPAN");
  });

  it("forwards native Input relationships and exposes invalid state", () => {
    render(
      <Input
        id="email"
        name="email"
        size="lg"
        invalid
        aria-describedby="email-help"
        aria-errormessage="email-error"
      />,
    );
    const input = screen.getByRole("textbox");
    expect(input).toHaveAttribute("name", "email");
    expect(input).toHaveAttribute("aria-describedby", "email-help");
    expect(input).toHaveAttribute("aria-errormessage", "email-error");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).not.toHaveAttribute("size");
    expect(input).toHaveAttribute("data-size", "lg");
  });
});
```

Create `web/test/ui-types.tsx`:

```tsx
import { IconButton } from "@/components/ui/IconButton";

<IconButton aria-label="Close">×</IconButton>;
// @ts-expect-error IconButton requires an accessible label.
<IconButton>×</IconButton>;
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
npm test -- components/ui/__tests__/surface-primitives.test.tsx
```

Expected: missing Card, Input, and Chip modules.

- [ ] **Step 3: Implement the three primitives**

Create `web/components/ui/Card.tsx`:

```tsx
import { forwardRef, type HTMLAttributes } from "react";
import clsx from "clsx";
export interface CardProps extends HTMLAttributes<HTMLDivElement> { variant?: "surface" | "muted" | "outlined"; padding?: "none" | "sm" | "md" | "lg"; }
export const Card = forwardRef<HTMLDivElement, CardProps>(function Card({ className, variant = "surface", padding = "md", ...props }, ref) {
  return <div {...props} ref={ref} data-variant={variant} data-padding={padding} className={clsx("wf-card", className)} />;
});
```

Create `web/components/ui/Input.tsx`:

```tsx
import { forwardRef, type InputHTMLAttributes } from "react";
import clsx from "clsx";
export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "size"> { size?: "sm" | "md" | "lg"; invalid?: boolean; }
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input({ className, size = "md", invalid, "aria-invalid": ariaInvalid, ...props }, ref) {
  return <input {...props} ref={ref} data-size={size} aria-invalid={invalid || ariaInvalid || undefined} className={clsx("wf-input", className)} />;
});
```

Create `web/components/ui/Chip.tsx`:

```tsx
import { forwardRef, type HTMLAttributes } from "react";
import clsx from "clsx";
export interface ChipProps extends HTMLAttributes<HTMLSpanElement> { variant?: "neutral" | "accent" | "danger"; size?: "sm" | "md"; }
export const Chip = forwardRef<HTMLSpanElement, ChipProps>(function Chip({ className, variant = "neutral", size = "md", ...props }, ref) {
  return <span {...props} ref={ref} data-variant={variant} data-size={size} className={clsx("wf-chip", className)} />;
});
```

- [ ] **Step 4: Append surface primitive styles**

Append this complete marked block:

```css
/* === Warm Fold surface primitives: START === */
.wf-card { color: var(--wf-text); border-radius: var(--wf-radius-md); font-family: var(--wf-font-sans); }
.wf-card[data-variant="surface"] { background: var(--wf-surface); border: 1px solid var(--wf-border); box-shadow: var(--wf-shadow-sm); }
.wf-card[data-variant="muted"] { background: var(--wf-surface-muted); border: 1px solid transparent; }
.wf-card[data-variant="outlined"] { background: transparent; border: 1px solid var(--wf-border-strong); }
.wf-card[data-padding="sm"] { padding: 0.75rem; } .wf-card[data-padding="md"] { padding: 1rem; } .wf-card[data-padding="lg"] { padding: 1.5rem; }
.wf-input { width: 100%; border: 1px solid var(--wf-border); border-radius: var(--wf-radius-sm); background: var(--wf-surface); color: var(--wf-text); font-family: var(--wf-font-sans); transition: border-color var(--wf-motion-fast) var(--wf-ease), background var(--wf-motion-fast) var(--wf-ease); }
.wf-input::placeholder { color: var(--wf-text-tertiary); }
.wf-input[data-size="sm"] { min-height: 36px; padding: 0.5rem 0.625rem; font-size: 0.8125rem; } .wf-input[data-size="md"] { min-height: 44px; padding: 0.625rem 0.75rem; font-size: 0.9375rem; } .wf-input[data-size="lg"] { min-height: 48px; padding: 0.75rem 0.875rem; font-size: 1rem; }
.wf-input:focus-visible { outline: 2px solid var(--wf-focus); outline-offset: 3px; border-color: var(--wf-accent); }
.wf-input[aria-invalid="true"] { border-color: var(--wf-danger); background: var(--wf-danger-surface); }
.wf-input:disabled { background: var(--wf-disabled-bg); border-color: var(--wf-disabled-border); color: var(--wf-disabled-fg); cursor: not-allowed; }
.wf-chip { display: inline-flex; align-items: center; width: fit-content; border-radius: var(--wf-radius-full); font-family: var(--wf-font-sans); font-weight: 600; }
.wf-chip[data-size="sm"] { min-height: 24px; padding: 0.1875rem 0.5rem; font-size: 0.75rem; } .wf-chip[data-size="md"] { min-height: 28px; padding: 0.25rem 0.625rem; font-size: 0.8125rem; }
.wf-chip[data-variant="neutral"] { background: var(--wf-surface-muted); color: var(--wf-text-secondary); }
.wf-chip[data-variant="accent"] { background: color-mix(in srgb, var(--wf-brand-coral) 14%, var(--wf-surface)); color: var(--wf-accent); }
.wf-chip[data-variant="danger"] { background: var(--wf-danger-surface); color: var(--wf-danger); }
/* === Warm Fold surface primitives: END === */
```

- [ ] **Step 5: Run tests and commit**

Run:

```powershell
npm test -- components/ui/__tests__/surface-primitives.test.tsx
npx tsc --noEmit
```

Stage new files normally and use the helper for the marked surface block.

```powershell
.codex-run/stage-p0.ps1 -Part surfaces
git add web/components/ui/Card.tsx web/components/ui/Input.tsx web/components/ui/Chip.tsx web/components/ui/__tests__/surface-primitives.test.tsx web/test/ui-types.tsx
git diff --cached --check
git commit -m "feat: add Warm Fold surface primitives"
```

## Task 6: Add Exports And Automated Asset Validation

**Files:**
- Create: `web/components/ui/index.ts`
- Create: `web/scripts/validate-warm-fold.mjs`

- [ ] **Step 1: Add the public primitive exports**

Create `web/components/ui/index.ts`:

```ts
export { Button, type ButtonProps } from "./Button";
export { Card, type CardProps } from "./Card";
export { Chip, type ChipProps } from "./Chip";
export { IconButton, type IconButtonProps } from "./IconButton";
export { Input, type InputProps } from "./Input";
```

- [ ] **Step 2: Create the validator**

Create `web/scripts/validate-warm-fold.mjs` with these exact checks:

```js
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const css = fs.readFileSync(path.join(root, "app", "globals.css"), "utf8");
const assets = [
  ["brand-mark.svg", 4096, 8],
  ["brand-logo.svg", 18432, 80],
  ["favicon.svg", 4096, 8],
];

function assert(condition, message) { if (!condition) throw new Error(message); }
function selectorBlock(selector) {
  const start = css.indexOf(selector); assert(start >= 0, `Missing selector ${selector}`);
  const open = css.indexOf("{", start); let depth = 0;
  for (let index = open; index < css.length; index += 1) {
    if (css[index] === "{") depth += 1;
    if (css[index] === "}" && --depth === 0) return css.slice(start, index + 1);
  }
  throw new Error(`Unclosed selector ${selector}`);
}

for (const [name, maxBytes, maxPaths] of assets) {
  const file = path.join(root, "public", "brand", name);
  const source = fs.readFileSync(file, "utf8");
  const document = new JSDOM(source, { contentType: "image/svg+xml" }).window.document;
  assert(document.documentElement.tagName.toLowerCase() === "svg", `${name} is not SVG`);
  assert(document.documentElement.hasAttribute("viewBox"), `${name} lacks viewBox`);
  assert(!source.includes("<image"), `${name} embeds raster content`);
  assert(!source.includes("<metadata"), `${name} contains metadata`);
  assert(!source.includes('display="none"'), `${name} contains hidden layers`);
  assert(Buffer.byteLength(source) <= maxBytes, `${name} exceeds ${maxBytes} bytes`);
  assert((source.match(/<path\b/g) || []).length <= maxPaths, `${name} has too many paths`);
  assert(!/\d+\.\d{4,}/.test(source), `${name} exceeds three decimal places`);
}

const logo = fs.readFileSync(path.join(root, "public", "brand", "brand-logo.svg"), "utf8");
assert(logo.includes('data-min-width="120"'), "brand-logo.svg lacks minimum width metadata");
const legacy = [".apple-card {", ".apple-button {", ".tag-chip {"]
  .map(selectorBlock).join("\n");
assert(!legacy.includes("--wf-"), "Legacy classes reference Warm Fold tokens");
assert(css.includes("--wf-accent: #A34A2F"), "Accessible light accent is missing");
assert(css.includes("--wf-brand-coral: #B65C3A"), "Brand coral is missing");
console.log(`Warm Fold validation passed (${createHash("sha256").update(legacy).digest("hex").slice(0, 12)})`);
```

- [ ] **Step 3: Run the complete automated checks**

Run:

```powershell
npm run brand:build
npm run validate:warm-fold
npm test
npx tsc --noEmit
npm run lint
```

Expected: validator exits 0, all tests pass, TypeScript exits 0, and ESLint reports no errors.

- [ ] **Step 4: Commit exports and validation**

Run:

```powershell
git add web/components/ui/index.ts web/scripts/validate-warm-fold.mjs
git diff --cached --check
git commit -m "test: validate Warm Fold foundation"
```

## Task 7: Isolated Visual QA, Full Build, And Migration Audit

**Files:**
- Temporary only: `web/app/__p0-preview/page.tsx` (delete before commit)
- Verify all P0 allowlisted files

- [ ] **Step 1: Create a temporary isolated preview**

Create `web/app/__p0-preview/page.tsx` with light/dark sections containing:

```tsx
import { BrandMark } from "@/components/brand/BrandMark";
import { Button, Card, Chip, IconButton, Input } from "@/components/ui";

export default function P0Preview() {
  return (
    <main style={{ padding: 32, background: "var(--wf-canvas)", color: "var(--wf-text)", fontFamily: "var(--wf-font-sans)" }}>
      <BrandMark variant="full" size="lg" label="NoteGen" />
      <div style={{ display: "flex", alignItems: "center", gap: 16, margin: "24px 0" }}>
        <BrandMark size="sm" label="NoteGen 16px" />
        <BrandMark size="md" label="NoteGen 24px" />
        <BrandMark size="lg" label="NoteGen 32px" />
      </div>
      <Card style={{ display: "grid", gap: 16, maxWidth: 640 }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
          <Button>Primary</Button><Button variant="secondary">Secondary</Button><Button variant="ghost">Ghost</Button><Button variant="danger">Danger</Button><Button loading>Loading</Button><Button disabled>Disabled</Button>
        </div>
        <Input aria-label="Default input" placeholder="Placeholder" />
        <Input aria-label="Invalid input" invalid defaultValue="Invalid" />
        <div style={{ display: "flex", gap: 8 }}><Chip>Neutral</Chip><Chip variant="accent">Accent</Chip><Chip variant="danger">Danger</Chip></div>
        <IconButton aria-label="Example icon">N</IconButton>
      </Card>
    </main>
  );
}
```

- [ ] **Step 2: Run and inspect the preview**

Run:

```powershell
npm run dev
```

Open `http://localhost:3000/__p0-preview` in the in-app browser. Inspect at 375px, 768px, and 1440px. Toggle `data-theme` between light and dark and enable reduced motion. Confirm:

- no clipped Logo paths;
- the mark is legible at 16px, 24px, and 32px;
- the 120px horizontal lockup remains legible;
- every variant, focus, loading, disabled, invalid, and danger state is distinct;
- no horizontal overflow occurs.

- [ ] **Step 3: Delete the temporary preview**

Delete `web/app/__p0-preview/page.tsx` and remove the empty directory. Verify:

```powershell
git status --short -- web/app/__p0-preview
```

Expected: no output.

- [ ] **Step 4: Compare dirty-file baselines**

Run:

```powershell
git diff --no-index -- .codex-run/p0-baseline/layout.tsx web/app/layout.tsx
git diff --no-index -- .codex-run/p0-baseline/globals.css web/app/globals.css
```

Expected: layout differences are limited to DM font import, declarations, and variable classes. CSS differences are limited to the three marked Warm Fold blocks. All earlier user changes remain present.

- [ ] **Step 5: Run final verification from a clean index state**

Run:

```powershell
cd web
npm run brand:build
npm run validate:warm-fold
npm test
npx tsc --noEmit
npm run lint
npm run build
cd ..
git diff --check
git diff --cached --name-only
```

Expected: all commands exit 0 and the staging area is empty.

- [ ] **Step 6: Audit the implementation path allowlist**

Run:

```powershell
git log --name-only --format= HEAD~5..HEAD
git status --short
```

Expected: P0 commits contain only the allowed paths. Existing unrelated working-tree changes remain uncommitted and untouched.

- [ ] **Step 7: Record the final P0 implementation commit if verification required fixes**

If verification required changes, stage only their explicit P0 paths and commit:

```powershell
git diff --cached --check
git commit -m "fix: complete Warm Fold foundation verification"
```

If verification required no fixes, do not create an empty commit.
