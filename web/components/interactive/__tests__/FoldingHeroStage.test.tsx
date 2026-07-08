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

  it("exposes only the native range as the accessible progress slider", () => {
    reducedMotionState.value = false;
    render(<FoldingHeroStage />);

    const sliders = screen.getAllByRole("slider");
    expect(sliders).toHaveLength(1);
    expect(sliders[0]).toHaveAttribute("id", "fold-progress");
    expect(sliders[0].tagName).toBe("INPUT");

    const playhead = document.querySelector(".wf-playhead-beam");
    expect(playhead).not.toBeNull();
    expect(playhead).not.toHaveAttribute("role");
    expect(playhead).not.toHaveAttribute("tabindex");
    expect(playhead).toHaveAttribute("aria-hidden", "true");
  });

  it("lets keyboard users scrub the single native range", async () => {
    reducedMotionState.value = false;
    render(<FoldingHeroStage />);

    const slider = screen.getByRole("slider", { name: "调整视频折叠进度" });
    const startingValue = Number((slider as HTMLInputElement).value);

    fireEvent.keyDown(slider, { key: "ArrowLeft" });

    await waitFor(() => {
      expect(slider).toHaveValue(String(Math.max(0, startingValue - 4)));
    });

    fireEvent.keyDown(slider, { key: "Home" });

    await waitFor(() => {
      expect(slider).toHaveValue("0");
    });

    fireEvent.keyDown(slider, { key: "End" });

    await waitFor(() => {
      expect(slider).toHaveValue("100");
    });
  });

  it("lets pointer dragging on the visual playhead update the same native range", async () => {
    reducedMotionState.value = false;
    render(<FoldingHeroStage />);

    const stage = document.querySelector(".wf-hero-fold-stage") as HTMLElement;
    const playhead = document.querySelector(".wf-playhead-beam") as HTMLElement;
    const slider = screen.getByRole("slider", { name: "调整视频折叠进度" });

    stage.getBoundingClientRect = () => ({
      bottom: 120,
      height: 120,
      left: 0,
      right: 100,
      top: 0,
      width: 100,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    });
    playhead.setPointerCapture = vi.fn();

    fireEvent.pointerDown(playhead, { clientX: 76, clientY: 40, pointerId: 1 });

    await waitFor(() => {
      expect(slider).toHaveValue("76");
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
