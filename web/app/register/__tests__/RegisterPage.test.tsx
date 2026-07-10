import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RegisterPage from "../page";

const authState = vi.hoisted(() => ({
  refresh: vi.fn(),
}));

const apiRegister = vi.hoisted(() => vi.fn());

vi.mock("@/components/AuthContext", () => ({
  useAuth: () => authState,
}));

vi.mock("@/lib/auth", () => ({
  apiRegister,
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("RegisterPage", () => {
  it("marks only the password field invalid for short passwords", async () => {
    render(<RegisterPage />);

    fireEvent.change(document.querySelector("#register-email") as HTMLInputElement, {
      target: { value: "user@example.com" },
    });
    fireEvent.change(document.querySelector("#register-password") as HTMLInputElement, {
      target: { value: "short" },
    });
    fireEvent.click(screen.getByRole("button", { name: /注册/ }));

    await waitFor(() => {
      expect(document.querySelector("#register-password")).toHaveAttribute("aria-invalid", "true");
      expect(document.querySelector("#register-email")).not.toHaveAttribute("aria-invalid", "true");
    });
    expect(apiRegister).not.toHaveBeenCalled();
  });
});
