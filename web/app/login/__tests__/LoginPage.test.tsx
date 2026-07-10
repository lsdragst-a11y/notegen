import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import LoginPage from "../page";

const push = vi.hoisted(() => vi.fn());
const login = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams("next=/notebooks"),
}));

vi.mock("@/components/AuthContext", () => ({
  useAuth: () => ({ login }),
}));

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("LoginPage", () => {
  it("keeps the success state visible before redirecting", async () => {
    vi.useFakeTimers();
    login.mockResolvedValueOnce(undefined);

    render(<LoginPage />);

    fireEvent.change(document.querySelector("#login-email") as HTMLInputElement, {
      target: { value: "user@example.com" },
    });
    fireEvent.change(document.querySelector("#login-password") as HTMLInputElement, {
      target: { value: "correct-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: /登录/ }));

    await act(async () => {
      await Promise.resolve();
    });

    expect(login).toHaveBeenCalledWith("user@example.com", "correct-password");
    expect(push).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(599);
    });
    expect(push).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(push).toHaveBeenCalledWith("/notebooks");
  });
});
