import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const sourcePath = join(process.cwd(), "components", "NoteWorkspace.tsx");

describe("NoteWorkspace layout contracts", () => {
  it("keeps the chat panel in normal document flow on mobile", () => {
    const source = readFileSync(sourcePath, "utf8");

    expect(source).not.toContain('className="sticky bottom-3 mt-6"');
    expect(source).toContain('className="mt-6 lg:sticky lg:bottom-3"');
  });

  it("traps and restores focus for the mobile chapter drawer", () => {
    const source = readFileSync(sourcePath, "utf8");

    expect(source).toContain("railTriggerRef");
    expect(source).toContain("railDialogRef");
    expect(source).toContain("railCloseButtonRef");
    expect(source).toContain("getRailFocusableElements");
    expect(source).toContain("document.activeElement");
  });
});
