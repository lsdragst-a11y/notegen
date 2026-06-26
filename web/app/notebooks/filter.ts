export type NotebookFilter = "mine" | "all" | "public";

export const NOTEBOOK_FILTERS: { key: NotebookFilter; label: string }[] = [
  { key: "mine", label: "我的笔记" },
  { key: "all", label: "全部" },
  { key: "public", label: "公开示例" },
];

export function parseNotebookFilter(value: string | null): NotebookFilter {
  if (value === "all" || value === "public") return value;
  return "mine";
}

export function shouldAllowPublicCatalog(filter: NotebookFilter) {
  return filter === "public";
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
