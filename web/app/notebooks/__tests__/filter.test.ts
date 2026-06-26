import { describe, expect, it } from "vitest";

import { parseNotebookFilter } from "../filter";

describe("parseNotebookFilter", () => {
  it("opens public examples when requested from the landing page", () => {
    expect(parseNotebookFilter("public")).toBe("public");
  });

  it("falls back to personal notes for missing or unknown values", () => {
    expect(parseNotebookFilter(null)).toBe("mine");
    expect(parseNotebookFilter("debug")).toBe("mine");
  });
});
