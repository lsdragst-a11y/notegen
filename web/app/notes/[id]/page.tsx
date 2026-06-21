"use client";
import { useEffect, useState, use } from "react";
import NoteWorkspace, { WorkspaceError, WorkspaceSkeleton } from "@/components/NoteWorkspace";
import { fetchNote } from "@/lib/notes";
import type { NoteBundle } from "@/lib/notes";
import { useAuth } from "@/components/AuthContext";

interface PageProps {
  params: Promise<{ id: string }>;
}

/** 薄壳：取数 + 加载/错误态。工作台本体在 components/NoteWorkspace（与 /s/[token] 共用）。 */
export default function NoteDetailPage({ params }: PageProps) {
  const { id } = use(params);
  const { user } = useAuth();
  const backHref = user ? "/notebooks" : "/";   // 登录回笔记库，游客回 landing
  const [bundle, setBundle] = useState<NoteBundle | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // 取消标志：id 快速切换时丢弃过期响应，避免旧笔记覆盖新笔记
    let cancelled = false;
    fetchNote(id)
      .then(b => { if (!cancelled) setBundle(b); })
      .catch(e => { if (!cancelled) setError(String(e)); });
    return () => { cancelled = true; };
  }, [id]);

  if (error) return <WorkspaceError error={error} backHref={backHref} />;
  if (!bundle) return <WorkspaceSkeleton backHref={backHref} />;
  return <NoteWorkspace noteId={id} bundle={bundle} backHref={backHref} />;
}
