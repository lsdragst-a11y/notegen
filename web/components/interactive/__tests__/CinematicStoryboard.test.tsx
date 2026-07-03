import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("framer-motion", async (importOriginal) => {
  const actual = await importOriginal<typeof import("framer-motion")>();
  return {
    ...actual,
    useReducedMotion: () => false,
  };
});

import { CinematicStoryboard } from "../CinematicStoryboard";

afterEach(() => {
  cleanup();
});

describe("CinematicStoryboard", () => {
  it("marks only one perceptible film frame as active", () => {
    const { container } = render(<CinematicStoryboard />);

    expect(container.querySelectorAll(".wf-story-film-frame--active")).toHaveLength(1);
  });
});
