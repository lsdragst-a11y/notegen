import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import NavBar from "../NavBar";

const authState = vi.hoisted(() => ({
  user: null,
  loading: false,
  offline: false,
}));

vi.mock("../AuthContext", () => ({
  useAuth: () => authState,
}));

vi.mock("../LangContext", () => ({
  useLang: () => ({ lang: "zh" }),
}));

vi.mock("@/lib/bookmarks", () => ({
  useBookmarksList: () => [],
}));

vi.mock("../LangToggle", () => ({
  default: () => <button type="button">语言</button>,
}));

vi.mock("../ThemeToggle", () => ({
  default: () => <button type="button">主题</button>,
}));

vi.mock("../UserMenu", () => ({
  default: () => <button type="button">用户</button>,
}));

describe("NavBar", () => {
  it("does not expose internal experiment routes in the public navigation", () => {
    authState.offline = false;
    render(<NavBar />);

    expect(screen.queryByRole("link", { name: /ablation/i })).not.toBeInTheDocument();
  });

  it("can suppress the offline badge on public fallback pages", () => {
    authState.offline = true;
    render(<NavBar suppressOfflineBadge />);

    expect(screen.queryByText("服务离线")).not.toBeInTheDocument();
  });

  it("shows the offline badge by default when auth status is unavailable", () => {
    authState.offline = true;
    render(<NavBar />);

    expect(screen.getByText("服务离线")).toBeInTheDocument();
  });
});
