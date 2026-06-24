import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { IconButton } from "../IconButton";

describe("IconButton", () => {
  it("requires and exposes an accessible label", () => {
    render(<IconButton aria-label="Close">x</IconButton>);

    expect(screen.getByRole("button", { name: "Close" })).toHaveAttribute("type", "button");
  });

  it("keeps the label while loading", () => {
    render(
      <IconButton aria-label="Refresh" loading>
        R
      </IconButton>,
    );
    const button = screen.getByRole("button", { name: "Refresh" });

    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button.querySelector(".wf-icon-button__spinner")).toHaveAttribute("aria-hidden", "true");
  });
});
