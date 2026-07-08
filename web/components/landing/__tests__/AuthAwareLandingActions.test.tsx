import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/AuthContext", () => ({
  useAuth: () => ({ user: null }),
}));

import { AuthAwareHeroActions } from "../AuthAwareLandingActions";

afterEach(() => {
  cleanup();
});

describe("AuthAwareHeroActions", () => {
  it("routes the demo link to a featured public example, not the generic catalog", () => {
    const { container } = render(<AuthAwareHeroActions />);
    const demoLink = container.querySelector<HTMLAnchorElement>(".wf-upload-demo-link");

    expect(demoLink).not.toBeNull();
    expect(demoLink).toHaveAttribute(
      "href",
      "/notebooks?filter=public&demo=EH5jx5qPabU_p0",
    );
  });
});
