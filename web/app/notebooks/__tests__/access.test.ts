import { describe, expect, it } from "vitest";

import {
  canCreateNotebook,
  getNotebookHeroCopy,
  shouldAllowPublicCatalog,
  shouldShowProgressPanel,
} from "../filter";

describe("notebook access helpers", () => {
  it("allows the public catalog without a signed-in user", () => {
    expect(shouldAllowPublicCatalog("public")).toBe(true);
    expect(shouldAllowPublicCatalog("mine")).toBe(false);
  });

  it("hides notebook creation for guests", () => {
    expect(canCreateNotebook(null)).toBe(false);
    expect(canCreateNotebook({ id: "u1" })).toBe(true);
  });

  it("uses public-example copy for guest catalog views", () => {
    expect(getNotebookHeroCopy("public", null)).toEqual({
      eyebrow: "Public Examples",
      title: "公开示例",
      description: "先浏览 NoteGen 生成的视频笔记样例；登录后可以创建自己的私有笔记本。",
      cta: "登录后创建",
    });
  });

  it("does not show personal progress to guest public viewers", () => {
    expect(shouldShowProgressPanel("public", null)).toBe(false);
    expect(shouldShowProgressPanel("public", { id: "u1" })).toBe(true);
    expect(shouldShowProgressPanel("mine", null)).toBe(true);
  });
});
