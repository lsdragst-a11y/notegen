import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AuthBrandStage } from "../AuthBrandStage";

afterEach(() => cleanup());

describe("AuthBrandStage", () => {
  it("covers the note character eyes while typing a hidden password", () => {
    render(<AuthBrandStage focus="password" passwordVisible={false} status="idle" variant="login" />);

    expect(screen.getAllByText("角色遮住眼睛").length).toBeGreaterThan(0);
    expect(screen.getByTestId("auth-character")).toHaveAttribute("data-eye-state", "covered");
  });

  it("lets the character peek when password is visible", () => {
    render(<AuthBrandStage focus="password" passwordVisible status="idle" variant="login" />);

    expect(screen.getAllByText("角色从指缝里偷看").length).toBeGreaterThan(0);
    expect(screen.getByTestId("auth-character")).toHaveAttribute("data-eye-state", "peek");
  });

  it("marks validation feedback and success feedback distinctly", () => {
    const { rerender } = render(<AuthBrandStage focus="email" passwordVisible={false} status="error" variant="register" />);

    expect(screen.getByTestId("auth-character")).toHaveAttribute("data-status", "error");

    rerender(<AuthBrandStage focus="email" passwordVisible={false} status="success" variant="register" />);

    expect(screen.getAllByText("角色轻碰书签庆祝").length).toBeGreaterThan(0);
    expect(screen.getByTestId("auth-character")).toHaveAttribute("data-status", "success");
  });
});
