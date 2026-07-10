import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  AccountCompanion,
  AccountPaperMascot,
  AuthEvidenceCard,
  AuthNoteSheetPreview,
  AuthTimelineBeam,
  AuthVideoStrip,
  AuthWorkbenchPreview,
} from "../AccountCompanion";

afterEach(() => cleanup());

describe("AccountCompanion", () => {
  it("exports focused auth workbench components", () => {
    expect(AuthWorkbenchPreview).toBeTypeOf("function");
    expect(AuthVideoStrip).toBeTypeOf("function");
    expect(AuthTimelineBeam).toBeTypeOf("function");
    expect(AuthNoteSheetPreview).toBeTypeOf("function");
    expect(AuthEvidenceCard).toBeTypeOf("function");
    expect(AccountPaperMascot).toBeTypeOf("function");
  });

  it("renders a product workbench preview instead of a central paper mascot", () => {
    render(<AccountCompanion state="idle" variant="login" />);

    const preview = screen.getByTestId("auth-workbench-preview");
    expect(preview).toHaveAttribute("data-state", "idle");
    expect(screen.getByTestId("auth-video-strip")).toBeInTheDocument();
    expect(screen.getByTestId("auth-timeline-beam")).toBeInTheDocument();
    expect(screen.getByTestId("auth-note-sheet-preview")).toBeInTheDocument();
    expect(screen.getByTestId("auth-evidence-card")).toBeInTheDocument();
    expect(screen.getByTestId("account-paper-mascot")).toHaveAttribute("data-role", "supporting-mascot");

    expect(within(preview).getAllByText("03:11").length).toBeGreaterThan(0);
    expect(within(preview).getAllByText("08:42").length).toBeGreaterThan(0);
    expect(within(preview).getAllByText("12:18").length).toBeGreaterThan(0);
    expect(within(preview).getByText("视频片段")).toBeInTheDocument();
    expect(within(preview).getByText("生成笔记")).toBeInTheDocument();
    expect(within(preview).getByText("问答证据")).toBeInTheDocument();
  });

  it("maps password reveal to the reveal state", () => {
    render(<AccountCompanion state="passwordReveal" variant="login" />);

    expect(screen.getByTestId("account-companion")).toHaveAttribute("data-state", "passwordReveal");
    expect(screen.getByTestId("auth-note-sheet-preview")).toHaveAttribute("data-sensitive-cover", "revealed");
    expect(screen.getAllByText("书签已移开，密码可见").length).toBeGreaterThan(0);
    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2 })).toBeInTheDocument();
  });

  it("turns account focus and password focus into product feedback", () => {
    const { rerender } = render(<AccountCompanion state="emailFocus" variant="login" />);

    expect(screen.getByTestId("auth-owner-chip")).toHaveAttribute("data-active", "true");
    expect(screen.getByTestId("auth-timecode-03-11")).toHaveAttribute("data-active", "true");

    rerender(<AccountCompanion state="passwordFocus" variant="login" />);

    expect(screen.getByTestId("auth-owner-chip")).toHaveAttribute("data-active", "false");
    expect(screen.getByTestId("auth-note-sheet-preview")).toHaveAttribute("data-sensitive-cover", "locked");
    expect(screen.getAllByText("书签遮住了敏感内容").length).toBeGreaterThan(0);
  });

  it("marks error and success states distinctly", () => {
    const { rerender } = render(<AccountCompanion state="error" variant="register" />);

    expect(screen.getByTestId("account-companion")).toHaveAttribute("data-state", "error");
    expect(screen.getByTestId("auth-timeline-beam")).toHaveAttribute("data-retry", "true");
    expect(screen.getAllByText("retry 00:08").length).toBeGreaterThan(0);

    rerender(<AccountCompanion state="success" variant="register" />);

    expect(screen.getByTestId("account-companion")).toHaveAttribute("data-state", "success");
    expect(screen.getByTestId("auth-note-sheet-preview")).toHaveAttribute("data-folding", "true");
    expect(screen.getAllByText("笔记已折入 notebook").length).toBeGreaterThan(0);
  });
});
