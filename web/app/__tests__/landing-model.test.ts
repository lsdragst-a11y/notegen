import { describe, expect, it } from "vitest";

import { CINEMATIC_BEATS } from "../landing-model";

describe("landing cinematic model", () => {
  it("tells the product story from import to grounded replay", () => {
    expect(CINEMATIC_BEATS.map((beat) => beat.id)).toEqual([
      "import",
      "timeline",
      "notes",
      "ask",
    ]);
  });

  it("keeps every beat tied to a visible time cue", () => {
    expect(CINEMATIC_BEATS.every((beat) => beat.timecode && beat.title && beat.copy)).toBe(true);
  });
});
