import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Card } from "../Card";
import { Chip } from "../Chip";
import { Input } from "../Input";

describe("surface primitives", () => {
  it("keeps Card semantically neutral", () => {
    const { container } = render(<Card variant="outlined">Notes</Card>);

    expect(container.firstChild).toHaveAttribute("data-variant", "outlined");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("keeps Chip presentational", () => {
    render(<Chip variant="accent">Course</Chip>);

    expect(screen.getByText("Course").tagName).toBe("SPAN");
  });

  it("forwards native Input relationships and exposes invalid state", () => {
    render(
      <Input
        id="email"
        name="email"
        size="lg"
        invalid
        aria-describedby="email-help"
        aria-errormessage="email-error"
      />,
    );
    const input = screen.getByRole("textbox");

    expect(input).toHaveAttribute("name", "email");
    expect(input).toHaveAttribute("aria-describedby", "email-help");
    expect(input).toHaveAttribute("aria-errormessage", "email-error");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).not.toHaveAttribute("size");
    expect(input).toHaveAttribute("data-size", "lg");
  });
});
