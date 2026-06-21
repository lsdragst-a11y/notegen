import { redirect } from "next/navigation";

/** 旧笔记库已合并进 /notebooks，保留路由做跳转。 */
export default function LibraryPage() {
  redirect("/notebooks");
}
