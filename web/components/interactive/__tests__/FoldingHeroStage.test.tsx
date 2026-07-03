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

  it("switches the active note when clicking a film frame", async () => {
    reducedMotionState.value = false;
    render(<FoldingHeroStage />);

    const frame = screen.getByTestId("fold-frame-08:42");
    fireEvent.click(frame);

    await waitFor(() => {
      expect(frame).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByTestId("fold-note-08:42")).toHaveAttribute("data-active", "true");
    });
  });

  it("lets keyboard users scrub the playhead slider", async () => {
    reducedMotionState.value = false;
    render(<FoldingHeroStage />);

    const playhead = document.querySelector(".wf-playhead-beam");
    expect(playhead).not.toBeNull();
    const startingValue = Number(playhead?.getAttribute("aria-valuenow"));

    fireEvent.keyDown(playhead as Element, { key: "ArrowLeft" });

    await waitFor(() => {
      expect(playhead).toHaveAttribute("aria-valuenow", String(Math.max(0, startingValue - 4)));
    });

    fireEvent.keyDown(playhead as Element, { key: "Home" });

    await waitFor(() => {
      expect(playhead).toHaveAttribute("aria-valuenow", "0");
    });

    fireEvent.keyDown(playhead as Element, { key: "End" });

    await waitFor(() => {
      expect(playhead).toHaveAttribute("aria-valuenow", "100");
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
