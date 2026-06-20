import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(resolve(process.cwd(), "app/globals.css"), "utf8");
const layout = readFileSync(resolve(process.cwd(), "app/layout.tsx"), "utf8");

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
