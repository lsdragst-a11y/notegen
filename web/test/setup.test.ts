import { describe, expect, it } from "vitest";

describe("Vitest setup", () => {
  it("provides a jsdom document", () => {
    expect(document.createElement("button")).toBeInstanceOf(HTMLButtonElement);
  });
});
