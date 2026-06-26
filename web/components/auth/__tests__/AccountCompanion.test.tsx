import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AccountCompanion } from "../AccountCompanion";

afterEach(() => cleanup());

describe("AccountCompanion", () => {
  it("maps password reveal to the reveal state", () => {
    render(<AccountCompanion state="passwordReveal" variant="login" />);

    expect(screen.getByTestId("account-companion")).toHaveAttribute("data-state", "passwordReveal");
    expect(screen.getAllByText("纸页角色从书签旁确认密码可见").length).toBeGreaterThan(0);
  });

  it("marks error and success states distinctly", () => {
    const { rerender } = render(<AccountCompanion state="error" variant="register" />);

    expect(screen.getByTestId("account-companion")).toHaveAttribute("data-state", "error");

    rerender(<AccountCompanion state="success" variant="register" />);

    expect(screen.getByTestId("account-companion")).toHaveAttribute("data-state", "success");
    expect(screen.getAllByText("纸页角色把书签归档完成").length).toBeGreaterThan(0);
  });
});
