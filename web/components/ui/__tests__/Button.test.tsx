import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Button } from "../Button";

describe("Button", () => {
  it("defaults to a non-submit button", () => {
    render(<Button>Start</Button>);

    expect(screen.getByRole("button", { name: "Start" })).toHaveAttribute("type", "button");
  });

  it("allows submit type when explicitly requested", () => {
    render(<Button type="submit">Save</Button>);

    expect(screen.getByRole("button", { name: "Save" })).toHaveAttribute("type", "submit");
  });

  it("keeps text semantics while loading", () => {
    render(<Button loading>Saving</Button>);
    const button = screen.getByRole("button", { name: "Saving" });

    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button.querySelector(".wf-button__spinner")).toHaveAttribute("aria-hidden", "true");
  });
});
