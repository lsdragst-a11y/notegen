import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const reducedMotionState = vi.hoisted(() => ({
  value: false,
}));

vi.mock("framer-motion", async (importOriginal) => {
  const actual = await importOriginal<typeof import("framer-motion")>();
  return {
    ...actual,
    useReducedMotion: () => reducedMotionState.value,
  };
});

import { FoldingHeroStage } from "../FoldingHeroStage";

afterEach(() => {
  cleanup();
  reducedMotionState.value = false;
});

describe("FoldingHeroStage", () => {
  it("switches the active note when hovering a film frame", async () => {
    reducedMotionState.value = false;
    render(<FoldingHeroStage />);

    const frame = screen.getByTestId("fold-frame-08:42");
    fireEvent.mouseEnter(frame);

    await waitFor(() => {
      expect(frame).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByTestId("fold-note-08:42")).toHaveAttribute("data-active", "true");
    });
  });

  it("shows a stable final state for reduced motion users", async () => {
    reducedMotionState.value = true;
    render(<FoldingHeroStage />);

    await waitFor(() => {
      expect(screen.getByLabelText("可交互的视频折叠成笔记演示")).toHaveAttribute("data-mode", "reducedMotion");
      expect(screen.getByTestId("fold-note-12:18")).toHaveAttribute("data-active", "true");
    });
  });
});
