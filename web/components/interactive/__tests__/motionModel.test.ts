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
