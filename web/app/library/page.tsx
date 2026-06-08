"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { BookMarked, Layers, Hash, Clock, ArrowRight, Trash2, Loader2 } from "lucide-react";
import NavBar from "@/components/NavBar";
import FluidBG from "@/components/FluidBG";
import RequireAuth from "@/components/RequireAuth";
import { fetchMyNotes, deleteNote } from "@/lib/api";
import { formatDuration } from "@/lib/notes";
import type { NoteView } from "@/lib/types";

function LibraryInner() {
  const [notes, setNotes] = useState<NoteView[]>([]);
  const [loading, setLoading] = useState(true);
  const [delId, setDelId] = useState<string | null>(null);

  useEffect(() => {
    fetchMyNotes().then(setNotes).catch(console.error).finally(() => setLoading(false));
  }, []);

  async function remove(id: string) {
    setDelId(id);
    try {
      await deleteNote(id);
      setNotes(n => n.filter(x => x.id !== id));
    } catch (e) {
      alert(`删除失败：${String(e)}`);
    } finally {
      setDelId(null);
    }
  }

  return (
    <main className="relative min-h-screen">
      <FluidBG />
      <NavBar />
      <section className="relative z-10 max-w-6xl mx-auto px-6 pt-20 pb-32">
        <h1 className="text-xl font-semibold mb-5 flex items-center gap-2">
          <BookMarked size={18} className="text-[var(--accent)]" /> 我的笔记
        </h1>
        {loading ? (
          <div className="text-sm text-[var(--fg-tertiary)]">加载中…</div>
        ) : notes.length === 0 ? (
          <div className="apple-card p-8 text-center">
            <p className="text-sm text-[var(--fg-secondary)]">还没有私有笔记。</p>
            <Link href="/" className="apple-button inline-flex mt-4">去生成一个</Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {notes.map(item => (
              <article key={item.id} className="apple-card group p-5 h-full flex flex-col relative">
                <button
                  type="button"
                  onClick={() => remove(item.id)}
                  disabled={delId === item.id}
                  title="删除笔记"
                  className="absolute top-3 right-3 w-7 h-7 rounded-full bg-[var(--bg-muted)]
                             text-[var(--fg-tertiary)] hover:bg-[#ff3b30] hover:text-white
                             inline-flex items-center justify-center opacity-0 group-hover:opacity-100
                             transition-all z-10 disabled:opacity-60"
                >
                  {delId === item.id ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
                </button>
                <Link href={`/notes/${item.id}`} className="flex flex-col h-full">
                  <div className="flex items-start justify-between gap-3">
                    <span className="tag-chip">{item.domain}</span>
                    <span className="inline-flex items-center gap-1 text-xs text-[var(--fg-tertiary)] tabular-nums">
                      <Clock size={11} /> {formatDuration(item.duration_sec)}
                    </span>
                  </div>
                  <h3 className="mt-3 text-base font-semibold leading-snug line-clamp-2 flex-1">{item.title}</h3>
                  {item.uploader && <p className="mt-1 text-xs text-[var(--fg-tertiary)]">{item.uploader}</p>}
                  <div className="mt-4 pt-4 border-t border-[var(--border)] flex items-center gap-3 text-xs text-[var(--fg-secondary)]">
                    <span className="inline-flex items-center gap-1"><Layers size={11} /> {item.chapters} 章</span>
                    <span className="inline-flex items-center gap-1"><Hash size={11} /> {item.chunks} 段</span>
                    <span className="ml-auto inline-flex items-center gap-1 text-[var(--accent)] font-medium group-hover:gap-1.5 transition-all">
                      打开 <ArrowRight size={12} />
                    </span>
                  </div>
                </Link>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

export default function LibraryPage() {
  return <RequireAuth><LibraryInner /></RequireAuth>;
}
