export type NotebookFilter = "mine" | "all" | "public";

export const FEATURED_PUBLIC_DEMO_IDS = [
  "EH5jx5qPabU_p0",
  "BV1GofdBZEW7_p0",
  "claudecode",
] as const;

export type FeaturedPublicDemoId = (typeof FEATURED_PUBLIC_DEMO_IDS)[number];

export const DEFAULT_PUBLIC_DEMO_ID: FeaturedPublicDemoId = FEATURED_PUBLIC_DEMO_IDS[0];

export const NOTEBOOK_FILTERS: { key: NotebookFilter; label: string }[] = [
  { key: "mine", label: "我的笔记" },
  { key: "all", label: "全部" },
  { key: "public", label: "公开示例" },
];

export function parseNotebookFilter(value: string | null, user?: { id: string } | null): NotebookFilter {
  if (user === null) return "public";
  if (value === "all" || value === "public") return value;
  return "mine";
}

export function getVisibleNotebookFilters(user: { id: string } | null) {
  if (!user) return NOTEBOOK_FILTERS.filter((item) => item.key === "public");
  return NOTEBOOK_FILTERS;
}

export function shouldAllowPublicCatalog(filter: NotebookFilter) {
  return filter === "public";
}

export function isFeaturedPublicDemo(value: string) {
  return FEATURED_PUBLIC_DEMO_IDS.includes(value as FeaturedPublicDemoId);
}

export function parsePublicDemo(value: string | null): FeaturedPublicDemoId {
  if (value && isFeaturedPublicDemo(value)) return value as FeaturedPublicDemoId;
  return DEFAULT_PUBLIC_DEMO_ID;
}

export function getPublicDemoRank(value: string) {
  const index = FEATURED_PUBLIC_DEMO_IDS.indexOf(value as FeaturedPublicDemoId);
  return index === -1 ? Number.POSITIVE_INFINITY : index;
}

export function canCreateNotebook(user: { id: string } | null) {
  return Boolean(user);
}

export function getNotebookHeroCopy(filter: NotebookFilter, user: { id: string } | null) {
  if (filter === "public" && !user) {
    return {
      eyebrow: "Public Examples",
      title: "公开示例",
      description: "先浏览 NoteGen 生成的视频笔记样例；登录后可以创建自己的私有笔记本。",
      cta: "登录后创建",
    };
  }

  return {
    eyebrow: "Notebook Library",
    title: "我的笔记",
    description: "优先查看自己的视频笔记、最近生成进度和可复习材料；公开示例保留为参考内容。",
    cta: "新建笔记本",
  };
}

export function shouldShowProgressPanel(filter: NotebookFilter, user: { id: string } | null) {
  return !(filter === "public" && !user);
}
