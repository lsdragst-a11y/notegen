import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ChapterRail from "@/components/ChapterRail";
import type { Chapter } from "@/lib/types";

const chapters: Chapter[] = [
  {
    title: "Agent planning",
    title_zh: "智能体规划",
    start: 12,
    end: 90,
    indices: [0],
    children: [
      {
        title: "Evidence loop",
        title_zh: "证据闭环",
        start: 48,
        end: 72,
        indices: [0],
      },
    ],
  },
];

describe("ChapterRail", () => {
  it("passes the clicked timeline control as evidence jump source", () => {
    Element.prototype.scrollIntoView = vi.fn();
    const onSeek = vi.fn();
    render(
      <ChapterRail
        chapters={chapters}
        currentIdx={0}
        currentTime={20}
        onSeek={onSeek}
      />,
    );

    const chapterButton = screen.getByRole("button", { name: /智能体规划/ });
    fireEvent.click(chapterButton);

    expect(onSeek).toHaveBeenCalledWith(12, chapterButton);
  });
});
