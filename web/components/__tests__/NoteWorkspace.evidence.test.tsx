import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ComponentProps, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { NoteBundle } from "@/lib/notes";
import NoteWorkspace from "@/components/NoteWorkspace";

const videoHarness = vi.hoisted(() => ({
  seek: vi.fn(),
  toggle: vi.fn(),
}));

vi.mock("@/components/NavBar", () => ({
  default: ({ children }: { children?: ReactNode }) => <nav>{children}</nav>,
}));

vi.mock("@/components/AuthContext", () => ({
  useAuth: () => ({ user: null, loading: false, offline: false }),
}));

vi.mock("@/components/VideoPlayer", async () => {
  const React = await import("react");

  return {
    default: React.forwardRef(function MockVideoPlayer(
      _props: Record<string, unknown>,
      ref: React.ForwardedRef<{
        seek: (sec: number) => void;
        getCurrentTime: () => number;
        toggle: () => void;
      }>,
    ) {
      React.useImperativeHandle(ref, () => ({
        seek: videoHarness.seek,
        getCurrentTime: () => 0,
        toggle: videoHarness.toggle,
      }));

      return <div data-testid="video-player" />;
    }),
  };
});

vi.mock("@/components/NotesContent", () => ({
  default: () => <section data-testid="notes-content" />,
}));

vi.mock("@/components/ChatPanel", () => ({
  default: ({ onSeek }: Pick<ComponentProps<"button">, never> & { onSeek: (sec: number, sourceElement?: HTMLElement | null) => void }) => (
    <button type="button" onClick={(event) => onSeek(142, event.currentTarget)}>
      Q&A evidence 02:22
    </button>
  ),
}));

vi.mock("@/components/Spotlight", () => ({
  default: () => null,
}));

vi.mock("@/components/MiniPlayer", () => ({
  default: () => null,
}));

vi.mock("@/components/interactive/CitationJumpLayer", () => ({
  CitationJumpLayer: () => null,
  useCitationJump: () => ({ jump: null, triggerJump: vi.fn() }),
}));

const bundle: NoteBundle = {
  id: "demo-note",
  videoUrl: "/videos/demo-note.mp4",
  keyframeBase: "/notes/demo-note/keyframes/",
  viaBackend: false,
  meta: {
    id: "demo-note",
    title: "Demo evidence workspace",
    category: "teaching",
  },
  overview: null,
  summary: [
    {
      start: 0,
      end: 80,
      text: "Intro chunk",
      headline: "Intro",
    },
    {
      start: 142,
      end: 170,
      text: "Evidence chunk",
      headline: "Evidence",
    },
  ],
  chapters: [
    {
      title: "Intro",
      title_zh: "开场章节",
      start: 0,
      end: 100,
      indices: [0],
    },
    {
      title: "Evidence",
      title_zh: "证据章节",
      start: 120,
      end: 220,
      indices: [1],
    },
  ],
};

afterEach(() => {
  cleanup();
  videoHarness.seek.mockClear();
  videoHarness.toggle.mockClear();
});

describe("NoteWorkspace evidence jumps", () => {
  it("links Q&A timestamp clicks to video seek, chapter highlight, body hint, and video hint", () => {
    Element.prototype.scrollIntoView = vi.fn();
    vi.stubGlobal("IntersectionObserver", class {
      observe = vi.fn();
      unobserve = vi.fn();
      disconnect = vi.fn();
      takeRecords = () => [];
    });

    const { container } = render(<NoteWorkspace noteId="demo-note" bundle={bundle} backHref="/notebooks" />);

    fireEvent.click(screen.getByRole("button", { name: "Q&A evidence 02:22" }));

    expect(videoHarness.seek).toHaveBeenCalledWith(142);
    expect(screen.getAllByRole("button", { name: /证据章节/ }).some((button) => (
      button.getAttribute("aria-current") === "true"
    ))).toBe(true);
    expect(screen.getByText("证据片段 02:22")).toBeInTheDocument();
    expect(screen.getByTestId("workspace-body-evidence-status")).toHaveTextContent("02:22");
    expect(container.querySelector('[data-evidence-active="true"]')).toBeInTheDocument();
  });
});
