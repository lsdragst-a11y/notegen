import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import RequireAuth from "../RequireAuth";

const replace = vi.fn();
const authState = {
  user: null,
  loading: false,
  offline: true,
  refresh: vi.fn(),
};

vi.mock("next/navigation", () => ({
  usePathname: () => "/notebooks",
  useRouter: () => ({ replace }),
}));

vi.mock("../AuthContext", () => ({
  useAuth: () => authState,
}));

describe("RequireAuth", () => {
  it("renders children for public routes even when auth status is offline", () => {
    render(
      <RequireAuth allowUnauthenticated>
        <div>Public examples</div>
      </RequireAuth>,
    );

    expect(screen.getByText("Public examples")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });
});
