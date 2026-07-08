import { describe, expect, it } from "vitest";

import {
  DEFAULT_PUBLIC_DEMO_ID,
  FEATURED_PUBLIC_DEMO_IDS,
  getVisibleNotebookFilters,
  parseNotebookFilter,
  parsePublicDemo,
} from "../filter";

describe("parseNotebookFilter", () => {
  it("opens public examples when requested from the landing page", () => {
    expect(parseNotebookFilter("public")).toBe("public");
  });

  it("falls back to personal notes for missing or unknown values", () => {
    expect(parseNotebookFilter(null)).toBe("mine");
    expect(parseNotebookFilter("debug")).toBe("mine");
  });

  it("opens public examples by default for guests", () => {
    expect(parseNotebookFilter(null, null)).toBe("public");
    expect(parseNotebookFilter("mine", null)).toBe("public");
    expect(parseNotebookFilter("all", null)).toBe("public");
  });

  it("only exposes public examples filter to guests", () => {
    expect(getVisibleNotebookFilters(null).map((item) => item.key)).toEqual(["public"]);
    expect(getVisibleNotebookFilters({ id: "u1" }).map((item) => item.key)).toEqual(["mine", "all", "public"]);
  });

  it("parses the featured public demo route from the landing page", () => {
    expect(FEATURED_PUBLIC_DEMO_IDS).toEqual([
      "EH5jx5qPabU_p0",
      "BV1GofdBZEW7_p0",
      "claudecode",
    ]);
    expect(DEFAULT_PUBLIC_DEMO_ID).toBe("EH5jx5qPabU_p0");
    expect(parsePublicDemo("BV1GofdBZEW7_p0")).toBe("BV1GofdBZEW7_p0");
    expect(parsePublicDemo("unknown-note")).toBe(DEFAULT_PUBLIC_DEMO_ID);
    expect(parsePublicDemo(null)).toBe(DEFAULT_PUBLIC_DEMO_ID);
  });
});
