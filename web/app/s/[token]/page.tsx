"use client";
import { useEffect, useState, use } from "react";
import NoteWorkspace, { WorkspaceError, WorkspaceSkeleton } from "@/components/NoteWorkspace";
import { fetchSharedNote } from "@/lib/notes";
import type { NoteBundle } from "@/lib/notes";
import { fetchSharedMeta } from "@/lib/api";

interface PageProps {
  params: Promise<{ token: string }>;
}

/**
 * 分享只读页：/s/{token}，免登录。token 即授权——后端 /api/shared/{token}/file
 * 托管笔记文件，撤销分享后链接立即 404。工作台以 shared 模式渲染
 * （隐藏分享/问答/书签入口，其余浏览体验与正常页一致）。
 */
export default function SharedNotePage({ params }: PageProps) {
  const { token } = use(params);
  const [noteId, setNoteId] = useState<string | null>(null);
  const [bundle, setBundle] = useState<NoteBundle | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const meta = await fetchSharedMeta(token);   // token → note_id（无效 404）
        const b = await fetchSharedNote(token, meta.id);
        if (!cancelled) { setNoteId(meta.id); setBundle(b); }
      } catch {
        if (!cancelled) setError("分享链接无效或已被撤销");
      }
    })();
    return () => { cancelled = true; };
  }, [token]);

  if (error) return <WorkspaceError error={error} backHref="/" />;
  if (!bundle || !noteId) return <WorkspaceSkeleton backHref="/" />;
  return <NoteWorkspace noteId={noteId} bundle={bundle} backHref="/" shared />;
}
