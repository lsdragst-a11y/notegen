# NoteGen Warm Fold P0 Foundation Design

Date: 2026-06-19
Status: Approved for implementation planning

## 1. Goal

P0 establishes the shared Warm Fold brand and interface foundation without migrating existing business pages.

The foundation includes:

- the approved NoteGen logo system;
- DM Serif Display and DM Sans font variables with Chinese system fallbacks;
- light and dark Warm Fold semantic tokens;
- reusable visual primitives for buttons, cards, inputs, chips, and icon buttons;
- tests and validation that protect accessibility, asset quality, and the legacy compatibility layer.

P0 does not redesign or migrate the homepage, authentication pages, notebook library, note workspace, or any other business page.

## 2. Design Direction

The approved direction is **Warm Fold**.

Its visual language combines:

- warm paper surfaces;
- warm ink text and structure;
- a terracotta-coral playback pointer;
- restrained caramel accents;
- folded-note geometry;
- editorial typography;
- quiet motion that supports comprehension.

Warm Fold replaces the current NotebookLM-inspired blue system for new work. The existing system remains available only as a deprecated compatibility layer until P1-P4 migrate business pages.

## 3. Scope And Migration Boundary

### 3.1 Included in P0

- Add font variables in `web/app/layout.tsx` with `next/font`.
- Add new `--wf-*` semantic tokens in `web/app/globals.css`.
- Add approved SVG assets under `web/public/brand/`.
- Add `BrandMark` under `web/components/brand/`.
- Add visual primitives under `web/components/ui/`.
- Add focused component tests, asset validation, contrast checks, and test configuration.

### 3.2 Excluded from P0

P0 must not change component usage or page structure in:

- `web/app/page.tsx`;
- `web/app/login/page.tsx`;
- `web/app/register/page.tsx`;
- `web/app/notebooks/page.tsx`;
- `web/app/notes/[id]/page.tsx`;
- authentication, notebook, workspace, upload, routing, or note-creation flows;
- any other business page or business component.

P1-P4 own page-by-page migration from legacy styles to Warm Fold primitives.

### 3.3 Compatibility rule

P0 is additive.

- Existing variables such as `--bg`, `--accent`, and `--border` retain their current values.
- Existing `.apple-card`, `.apple-button`, and related legacy classes retain their current rules.
- Legacy variables and classes must not reference `--wf-*` variables.
- New Warm Fold components must use `--wf-*` variables only.
- Legacy names are documented as deprecated but are not removed in P0.

This prevents existing pages from changing appearance as a side effect of installing the new foundation.

## 4. File Architecture

### 4.1 Files modified

- `web/app/layout.tsx`
  - Load DM Serif Display and DM Sans through `next/font`.
  - Attach only their CSS variable class names.
  - Do not replace the existing global body font and do not restructure the layout.

- `web/app/globals.css`
  - Add Warm Fold light and dark semantic token groups.
  - Add shared primitive styles or token-backed component selectors where needed.
  - Leave legacy token values and `.apple-*` rules unchanged.

- `web/package.json`
  - Add the test scripts and focused test dependencies approved in this specification.

- `web/package-lock.json`
  - Record only dependency changes resulting from P0 test tooling.

### 4.2 Files created

- `web/public/brand/brand-mark.svg`
- `web/public/brand/brand-logo.svg`
- `web/public/brand/favicon.svg`
- `web/components/brand/BrandMark.tsx`
- `web/components/ui/Button.tsx`
- `web/components/ui/Card.tsx`
- `web/components/ui/Input.tsx`
- `web/components/ui/Chip.tsx`
- `web/components/ui/IconButton.tsx`
- `web/components/ui/index.ts`
- `web/components/brand/__tests__/BrandMark.test.tsx`
- `web/components/ui/__tests__/Button.test.tsx`
- `web/components/ui/__tests__/Card.test.tsx`
- `web/components/ui/__tests__/Input.test.tsx`
- `web/components/ui/__tests__/Chip.test.tsx`
- `web/components/ui/__tests__/IconButton.test.tsx`
- `web/test/setup.ts`
- `web/vitest.config.ts`
- `web/scripts/validate-warm-fold.mjs`

The implementation plan may consolidate closely related tests when that reduces duplication without weakening coverage.

## 5. Typography

### 5.1 Font roles

- `DM Serif Display`: NoteGen wordmark, brand display headings, and later marketing headings.
- `DM Sans`: English UI, Latin text, numbers, and controls in Warm Fold components.
- Chinese system fallback: Chinese UI and content.

### 5.2 Loading strategy

`web/app/layout.tsx` uses `next/font` to expose two variables:

```txt
--font-dm-serif-display
--font-dm-sans
```

The variables are attached without changing the existing `html`, `body`, provider, or page structure. P0 must not replace the current global `font-family` declaration.

### 5.3 Warm Fold font tokens

```css
--wf-font-display: var(--font-dm-serif-display), Georgia, "Songti SC", serif;
--wf-font-sans: var(--font-dm-sans), "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", system-ui, sans-serif;
--wf-font-zh: "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", system-ui, sans-serif;
```

The Chinese fallback must remain explicit. DM Serif Display and DM Sans are not treated as Chinese fonts.

## 6. Warm Fold Semantic Tokens

All new tokens use the `--wf-*` prefix.

### 6.1 Light theme: Warm Paper

| Token | Value | Use |
| --- | --- | --- |
| `--wf-canvas` | `#F6F0E7` | Page background |
| `--wf-surface` | `#FFFAF3` | Primary elevated surface |
| `--wf-surface-muted` | `#EDE2D6` | Secondary surface |
| `--wf-text` | `#2D2925` | Primary text |
| `--wf-text-secondary` | `#665D55` | Secondary text |
| `--wf-text-tertiary` | `#877A6E` | Metadata, timestamps, placeholders, disabled hints |
| `--wf-brand-coral` | `#B65C3A` | Logo pointer and non-text brand decoration |
| `--wf-accent` | `#A34A2F` | Links, controls, focus, and small interactive text |
| `--wf-accent-hover` | `#98492F` | Hover state |
| `--wf-accent-active` | `#7F3927` | Active state |
| `--wf-on-accent` | `#FFFAF3` | Content on accent surfaces |
| `--wf-caramel` | `#8B5A35` | Restrained secondary brand accent |
| `--wf-danger` | `#B43A31` | Destructive and error state |
| `--wf-on-danger` | `#FFFAF3` | Content on danger surfaces |

`--wf-brand-coral` is not used as normal small body text or as the default link color. `--wf-accent` supplies the darker accessible interaction color.

`--wf-text-tertiary` is not allowed for body copy, button text, form labels, or critical interaction guidance.

### 6.2 Dark theme: Warm Ink

| Token | Value | Use |
| --- | --- | --- |
| `--wf-canvas` | `#1E1A17` | Page background |
| `--wf-surface` | `#28221E` | Primary elevated surface |
| `--wf-surface-muted` | `#352D27` | Secondary surface |
| `--wf-text` | `#F4EADF` | Primary text |
| `--wf-text-secondary` | `#CBBCAF` | Secondary text |
| `--wf-text-tertiary` | `#A19184` | Metadata, timestamps, placeholders, disabled hints |
| `--wf-brand-coral` | `#E47B59` | Logo pointer and brand decoration |
| `--wf-accent` | `#E47B59` | Links, controls, and focus |
| `--wf-accent-hover` | `#F08D6B` | Hover state |
| `--wf-accent-active` | `#C96343` | Active state |
| `--wf-on-accent` | `#2B1710` | Content on accent surfaces |
| `--wf-caramel` | `#D3A173` | Restrained secondary brand accent |
| `--wf-danger` | `#FF8A7A` | Destructive and error state |
| `--wf-on-danger` | `#2D1210` | Content on danger surfaces |

The dark theme uses warm ink rather than neutral black and must not introduce blue as its main interaction color.

### 6.3 Borders, radii, and shadows

Radii:

```txt
xs: 8px
sm: 12px
md: 18px
lg: 24px
full: 999px
```

Borders:

- Light: warm ink at approximately 14% opacity.
- Dark: warm paper at approximately 14% opacity.
- Strong and danger border tokens are separate from the default border.

Shadows:

- `sm`: small paper lift for controls and menus.
- `md`: card hover or floating panel.
- `lg`: modal or major overlay only.
- Shadows use warm-brown undertones, not neutral black.
- Dark theme uses tighter, lower-spread shadows.

### 6.4 Motion

```txt
fast: 160ms
normal: 220ms
enter: 420ms
easing: cubic-bezier(0.22, 1, 0.36, 1)
```

`prefers-reduced-motion: reduce` removes translation, scale, and automatic motion. Immediate color and visibility changes remain available.

### 6.5 Focus, disabled, and danger

- Focus uses a visible 2px accent outline with a 3px offset.
- Focus is applied with `:focus-visible`, not ordinary focus.
- Disabled uses dedicated foreground, background, and border tokens plus native disabled semantics.
- Disabled and loading must not be communicated with opacity or color alone.
- Danger has separate foreground, surface, border, hover, and active semantics.
- The danger palette remains visually distinct from brand coral.

## 7. Logo System

### 7.1 Approved direction

The primary mark uses the approved second visual direction:

- a strong angular capital N silhouette;
- two folded-note planes in warm ink;
- a terracotta-coral diagonal playback pointer;
- one restrained paper-fold detail;
- no pure black, blue, gradient, shadow, 3D effect, or rounded-square container.

The horizontal lockup uses the approved mark with wordmark proportions based on the third visual direction. The first direction contributes only a restrained folded-paper detail.

### 7.2 Vectorization rules

- Formal assets are vectorized from the approved visual target; the generated raster is reference material only.
- Use filled shapes for the core silhouette so small sizes do not depend on thin strokes.
- Warm-ink geometry can inherit `currentColor` in `BrandMark`.
- The playback pointer always uses the fixed Warm Fold brand-coral token.
- Avoid overlapping paths that produce seams at fractional pixels.
- Remove hidden layers, editor metadata, masks that can be flattened, and unnecessary decimal precision.
- SVG assets must not contain embedded raster images.

### 7.3 Assets

`brand-mark.svg`:

- The full approved mark.
- Recommended minimum size: 16px.
- A safe area equal to one-sixth of mark width on all sides.

`brand-logo.svg`:

- Approved mark plus the `NoteGen` wordmark.
- Wordmark follows the calm serif layout of the third direction.
- DM Serif Display lettering is converted to paths.
- Path complexity and numeric precision are reduced without visible deformation.
- Recommended minimum width: 120px.

`favicon.svg`:

- A dedicated small-size construction, not a direct scale of the full mark.
- At 16px, remove minor fold lines and the playback circle; retain the N silhouette and one coral triangle.
- At 24px and 32px, one primary fold detail may return if it remains crisp.

### 7.4 BrandMark component

```ts
type BrandMarkProps = {
  variant?: "full" | "mark";
  size?: "sm" | "md" | "lg";
  label?: string;
  className?: string;
};
```

- `variant="mark"` renders the icon.
- `variant="full"` renders the horizontal lockup.
- Warm-ink geometry follows `currentColor`.
- The coral pointer uses the fixed brand token and does not inherit `currentColor`.
- Decorative use sets `aria-hidden="true"`.
- Meaningful use exposes the provided label through an accessible SVG title or equivalent name.
- Layout and routing remain the caller's responsibility.

## 8. Visual Primitive Contracts

All primitives:

- accept `className`;
- forward refs;
- accept appropriate native element attributes;
- use only `--wf-*` tokens;
- contain no login, upload, note creation, routing, or other business logic;
- use native semantics instead of clickable neutral containers;
- support keyboard and focus-visible behavior;
- respect reduced motion.

### 8.1 Button

```ts
type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg";
```

- Extends native button attributes.
- Defaults to `type="button"`.
- Allows callers to set `type="submit"` explicitly.
- Supports leading and trailing icons through children composition.
- `loading` sets disabled interaction and `aria-busy="true"`.
- Loading preserves the existing accessible text.
- The spinner is `aria-hidden="true"`.
- Loading preserves the component's rendered width.
- Disabled and loading use native semantics, explicit cursor and interaction behavior, and dedicated visual tokens.

### 8.2 Card

```ts
type CardVariant = "surface" | "muted" | "outlined";
type CardPadding = "none" | "sm" | "md" | "lg";
```

- Renders a neutral container.
- Does not include an `interactive` prop.
- Does not add button, link, or keyboard behavior.
- Business layers use real `button` or `a` elements when a card is actionable.

### 8.3 Input

```ts
type InputVisualSize = "sm" | "md" | "lg";
```

- Extends `Omit<React.InputHTMLAttributes<HTMLInputElement>, "size">`.
- Uses the component `size` prop only for visual dimensions.
- `invalid` maps to `aria-invalid` and danger styling.
- Passes through `id`, `name`, `aria-describedby`, `aria-errormessage`, `required`, `readOnly`, `disabled`, and other valid native attributes.
- Does not own the label, helper text, or error text.
- Upstream form structure remains responsible for those relationships.

### 8.4 Chip

```ts
type ChipVariant = "neutral" | "accent" | "danger";
type ChipSize = "sm" | "md";
```

- Renders a display-only `span` by default.
- Does not manufacture selection or click semantics.
- Interactive filters use a business-owned button with the appropriate visual styling.

### 8.5 IconButton

```ts
type IconButtonVariant = "ghost" | "secondary" | "danger";
type IconButtonSize = "sm" | "md" | "lg";
```

- Extends native button attributes while requiring `"aria-label": string` at the type level.
- Defaults to `type="button"`.
- Allows explicit `type="submit"`.
- Supports loading, disabled, and focus-visible states.
- Loading preserves the accessible label and marks only the spinner as hidden.
- The interactive target is at least 44px by 44px even when the visible icon is smaller.

## 9. Accessibility And Interaction Rules

- All text and interactive color combinations must meet WCAG AA for their intended size.
- `--wf-text-tertiary` is restricted to non-critical information.
- Focus indicators remain visible in light and dark themes.
- Hover never carries unique information.
- Loading and disabled states have semantic attributes, visual state changes, and blocked interaction.
- Icon-only controls always have an accessible name.
- Brand assets expose a name only when meaningful and remain hidden when decorative.
- Motion never blocks input, navigation, or content reading.

## 10. Verification Strategy

### 10.1 Component tests

Add Vitest, React Testing Library, jest-dom matchers, and jsdom.

Tests cover:

- `Button` and `IconButton` default `type="button"`;
- explicit submit type support;
- loading `aria-busy`, disabled behavior, preserved accessible text, hidden spinner, and stable layout wrapper;
- disabled native semantics and blocked clicks;
- required IconButton accessible label typing;
- Input native attribute forwarding and visual-size/native-size separation;
- Input invalid semantics;
- Card and Chip neutral semantics;
- BrandMark variants, sizes, class names, decorative state, and accessible names.

### 10.2 Asset validation

`web/scripts/validate-warm-fold.mjs` checks:

- every SVG parses;
- every SVG has a `viewBox`;
- no SVG embeds raster images;
- no editor metadata or hidden layers remain;
- `brand-mark.svg` and `favicon.svg` remain at or below 4 KB with no more than 8 paths each;
- `brand-logo.svg` remains at or below 18 KB with no more than 80 paths after wordmark outlining;
- path coordinates use no more than three decimal places;
- the horizontal logo meets its minimum-width metadata contract.

### 10.3 Contrast validation

Automated checks cover at least:

- primary and secondary text on canvas and surface;
- interactive accent on canvas and surface;
- on-accent text on accent backgrounds;
- danger text and on-danger content;
- focus indicator contrast in both themes.

Tertiary text is tested only for its approved metadata and placeholder roles.

### 10.4 Visual validation

Use an isolated, non-production preview to inspect:

- brand mark at 16px, 24px, and 32px;
- horizontal lockup at its minimum recommended width;
- light and dark themes;
- button, input, chip, card, and icon button variants;
- focus, loading, disabled, invalid, and danger states;
- reduced-motion behavior.

The preview is not added to application routing.

### 10.5 Build verification

Run:

```txt
npm run lint
npx tsc --noEmit
npm run test
npm run build
npm run validate:warm-fold
```

### 10.6 Migration guard

Before commit, verify the implementation diff against an allowlist. No business page or business component may be modified.

The implementation must also compare the legacy token and `.apple-*` blocks against their pre-P0 baseline to ensure they retain their original values and do not reference `--wf-*`.

## 11. Acceptance Criteria

P0 is complete when:

1. The approved Logo direction is represented by optimized vector assets.
2. The mark is legible at 16px, 24px, and 32px.
3. The horizontal lockup remains legible at 120px or wider.
4. BrandMark supports `full`, `mark`, sizes, `label`, and `className`.
5. Warm-ink geometry inherits current color while the coral pointer uses the fixed brand token.
6. DM Serif Display and DM Sans variables are loaded without replacing existing page typography.
7. Warm Paper and Warm Ink token sets cover color, typography, radii, borders, shadows, motion, focus, disabled, and danger.
8. The light interactive accent is `#A34A2F` and the brand coral remains `#B65C3A`.
9. Tertiary text is restricted to non-critical roles.
10. Button, Card, Input, Chip, and IconButton satisfy their approved APIs and semantics.
11. The existing legacy tokens and `.apple-*` classes remain unchanged and independent of `--wf-*`.
12. No business page or business flow is migrated in P0.
13. Component, asset, contrast, type, lint, and build verification passes.

## 12. Implementation Sequence

After this design is reviewed:

1. Write a task-level implementation plan.
2. Vectorize and validate the approved Logo assets.
3. Add font variables without changing global typography.
4. Add light and dark `--wf-*` semantic tokens without modifying the legacy layer.
5. Implement BrandMark and the five visual primitives.
6. Add tests and validation tooling.
7. Run the complete verification and migration guard.
8. Commit only the P0 allowlisted files.
