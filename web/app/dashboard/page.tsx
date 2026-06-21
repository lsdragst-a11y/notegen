import { redirect } from "next/navigation";

/** 旧工作台已合并进 /notebooks 笔记本库，保留路由做跳转。 */
export default function DashboardPage() {
  redirect("/notebooks");
}
