import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ChapterNav from "../ChapterNav";
import ChapterRail from "../ChapterRail";
import type { Chapter } from "@/lib/types";

vi.mock("framer-motion", () => ({
  motion: {
    button: ({
      children,
      whileHover: _whileHover,
      whileTap: _whileTap,
      ...props
    }: React.ButtonHTMLAttributes<HTMLButtonElement> & {
      whileHover?: unknown;
      whileTap?: unknown;
    }) => {
      void _whileHover;
      void _whileTap;
      return <button {...props}>{children}</button>;
    },
  },
}));

const chapters: Chapter[] = [
  {
    title: "Intro",
    start: 0,
    end: 60,
    indices: [],
    children: [
      { title: "Opening", start: 0, end: 20, indices: [] },
      { title: "Setup", start: 20, end: 60, indices: [] },
    ],
  },
  { title: "Deep dive", start: 60, end: 120, indices: [] },
];

describe("chapter navigation accessibility", () => {
  afterEach(() => {
    cleanup();
  });

  it("marks the active vertical chapter and child as the current location", () => {
    window.HTMLElement.prototype.scrollIntoView = vi.fn();

    render(
      <ChapterRail
        chapters={chapters}
        currentIdx={0}
        currentTime={25}
        onSeek={() => {}}
      />
    );

    expect(screen.getByRole("button", { name: /00:00Intro/ })).toHaveAttribute(
      "aria-current",
      "location"
    );
    expect(screen.getByRole("button", { name: /00:20Setup/ })).toHaveAttribute(
      "aria-current",
      "location"
    );
    expect(screen.getByRole("button", { name: /01:00Deep dive/ })).not.toHaveAttribute(
      "aria-current"
    );
  });

  it("marks the active horizontal chapter as the current location", () => {
    window.HTMLElement.prototype.scrollIntoView = vi.fn();

    render(
      <ChapterNav
        chapters={chapters}
        currentIdx={1}
        currentTime={80}
        onSeek={() => {}}
      />
    );

    const nav = screen.getByRole("navigation", { name: "章节" });
    expect(within(nav).getByRole("button", { name: /Deep dive/ })).toHaveAttribute(
      "aria-current",
      "location"
    );
    expect(within(nav).getByRole("button", { name: /Intro/ })).not.toHaveAttribute(
      "aria-current"
    );
  });
});
