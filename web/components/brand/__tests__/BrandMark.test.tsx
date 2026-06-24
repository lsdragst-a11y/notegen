import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BrandMark } from "../BrandMark";

describe("BrandMark", () => {
  it("is decorative without a label", () => {
    const { container } = render(<BrandMark className="brand" />);
    const svg = container.querySelector("svg");

    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(svg).toHaveClass("brand");
  });

  it("exposes an accessible name when labeled", () => {
    render(<BrandMark variant="full" size="sm" label="NoteGen home" />);

    expect(screen.getByRole("img", { name: "NoteGen home" })).toBeInTheDocument();
  });

  it("uses currentColor for ink and the brand token for the pointer", () => {
    const { container } = render(<BrandMark label="NoteGen" />);

    expect(container.querySelector('[data-part="ink"]')).toHaveAttribute("fill", "currentColor");
    expect(container.querySelector('[data-part="pointer"]')).toHaveAttribute(
      "fill",
      "var(--wf-brand-coral, #B65C3A)",
    );
  });
});
