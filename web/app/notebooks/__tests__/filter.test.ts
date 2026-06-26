import { describe, expect, it } from "vitest";

import { getVisibleNotebookFilters, parseNotebookFilter } from "../filter";

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
});
