import { describe, expect, it } from "vitest";

import catalog from "@/public/notes/catalog.json";

import {
  DEFAULT_PUBLIC_DEMO_ID,
  FEATURED_PUBLIC_DEMO_IDS,
  getFeaturedPublicDemoItems,
  parsePublicDemo,
} from "../filter";

type CatalogRow = { id: string };

describe("featured public demo catalog", () => {
  it("keeps all featured demo ids backed by real public catalog entries", () => {
    const catalogIds = new Set((catalog as CatalogRow[]).map((item) => item.id));

    expect(FEATURED_PUBLIC_DEMO_IDS).toHaveLength(3);
    expect(FEATURED_PUBLIC_DEMO_IDS.every((id) => catalogIds.has(id))).toBe(true);
  });

  it("puts the requested demo first and leaves the card selectable by id", () => {
    const cards = [
      { id: "python", title: "Python" },
      { id: "claudecode", title: "Claude Code" },
      { id: "EH5jx5qPabU_p0", title: "AI Agents" },
      { id: "BV1GofdBZEW7_p0", title: "Vibe Coding" },
    ];

    expect(getFeaturedPublicDemoItems(cards, "BV1GofdBZEW7_p0").map((item) => item.id)).toEqual([
      "BV1GofdBZEW7_p0",
      "EH5jx5qPabU_p0",
      "claudecode",
    ]);
  });

  it("falls back to the default demo when the route asks for an unknown id", () => {
    expect(parsePublicDemo("missing-demo")).toBe(DEFAULT_PUBLIC_DEMO_ID);
  });
});
