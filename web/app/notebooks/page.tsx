"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import {
  BookOpen, Clapperboard, Clock, Code2, FlaskConical,
  GraduationCap, Layers, Loader2, MessagesSquare, Plus, Smartphone,
  Trash2, Wrench, X,
} from "lucide-react";
import NavBar from "@/components/NavBar";
import RequireAuth from "@/components/RequireAuth";
import CreateNotePanel from "@/components/CreateNotePanel";
import { fetchCatalog, formatDuration } from "@/lib/notes";
import { deleteNote, fetchMyNotes } from "@/lib/api";
import type { CatalogItem, NoteView } from "@/lib/types";

/**
 * 笔记本库（登录后主页，NotebookLM 应用首页的对应物）。
 * 营销 landing 在 / ；个人笔记、书签等登录后才可见（RequireAuth 包裹）。
 */

type Filter = "all" | "mine" | "public";

interface CardItem {
  id: string;
  title: string;
  domain: string;
  duration_sec: number;
  chunks: number;
  chapters: number;
  uploader: string;
  mine: boolean;
}

/** domain 文案 → 图标 + 中间调色（中间调在明暗两套底色上都可读） */
const DOMAIN_STYLE: Record<string, { icon: typeof BookOpen; color: string }> = {
  "编程教学": { icon: Code2, color: "#4285f4" },
  "考研专业课": { icon: GraduationCap, color: "#9a6bff" },
  "工具教程": { icon: Wrench, color: "#12b886" },
  "科普": { icon: FlaskConical, color: "#12b886" },
  "Vlog": { icon: Clapperboard, color: "#f59f00" },
  "时评": { icon: MessagesSquare, color: "#e64980" },
  "数码评测": { icon: Smartphone, color: "#22b8cf" },
};

function domainStyle(domain: string) {
  return DOMAIN_STYLE[domain] ?? { icon: BookOpen, color: "#4285f4" };
}

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "mine", label: "我的" },
  { key: "public", label: "公开示例" },
];

function NotebooksInner() {
  const [pub, setPub] = useState<CatalogItem[] | null>(null);
  const [mine, setMine] = useState<NoteView[] | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [createOpen, setCreateOpen] = useState(false);
  const [delId, setDelId] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetchCatalog()
      .then(d => { if (alive) setPub(d); })
      .catch(() => { if (alive) setPub([]); });
    fetchMyNotes()
      .then(d => { if (alive) setMine(d); })
      .catch(() => { if (alive) setMine([]); });
    return () => { alive = false; };
  }, []);

  // Esc 关闭新建面板
  useEffect(() => {
    if (!createOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setCreateOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [createOpen]);

  const loading = pub === null || mine === null;

  const items: CardItem[] = useMemo(() => {
    const mineCards: CardItem[] = (mine ?? []).map(n => ({
      id: n.id, title: n.title, domain: n.domain, duration_sec: n.duration_sec,
      chunks: n.chunks, chapters: n.chapters, uploader: n.uploader, mine: true,
    }));
    const mineIds = new Set(mineCards.map(c => c.id));
    const pubCards: CardItem[] = (pub ?? [])
      .filter(p => !mineIds.has(p.id))
      .map(p => ({
        id: p.id, title: p.title, domain: p.domain, duration_sec: p.duration_sec,
        chunks: p.chunks, chapters: p.chapters, uploader: p.uploader, mine: false,
      }));
    if (filter === "mine") return mineCards;
    if (filter === "public") return pubCards;
    return [...mineCards, ...pubCards];
  }, [pub, mine, filter]);

  async function remove(id: string) {
    if (!confirm("删除这篇笔记？产物文件会一并清除，不可恢复。")) return;
    setDelId(id);
    try {
      await deleteNote(id);
      setMine(m => (m ?? []).filter(x => x.id !== id));
    } catch (e) {
      alert(`删除失败：${String(e)}`);
    } finally {
      setDelId(null);
    }
  }

  return (
    <main className="min-h-screen bg-[var(--bg)]">
      <NavBar />

      <section className="mx-auto max-w-6xl px-5 pb-24 pt-8 sm:px-6">
        {/* 标题行 + filter chips */}
        <div className="mb-5 flex flex-wrap items-center gap-3">
          <h1 className="mr-1 text-xl font-medium text-[var(--fg)]">我的笔记本</h1>
          <div className="flex items-center gap-1.5">
            {FILTERS.map(f => {
              const active = filter === f.key;
              return (
                <button
                  key={f.key}
                  onClick={() => setFilter(f.key)}
                  className={`rounded-full px-3 py-1 text-xs font-medium transition-colors
                              ${active
                                ? "bg-[color-mix(in_srgb,var(--accent)_14%,transparent)] text-[var(--accent)]"
                                : "text-[var(--fg-secondary)] hover:bg-[var(--bg-muted)] hover:text-[var(--fg)]"}`}
                >
                  {f.label}
                </button>
              );
            })}
          </div>
          <span className="ml-auto text-xs text-[var(--fg-tertiary)]">
            {loading ? "" : `${items.length} 个笔记本`}
          </span>
        </div>

        {/* 卡片 grid */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {/* 新建卡 */}
          <button
            type="button"
            onClick={() => setCreateOpen(true)}
            className="flex min-h-44 flex-col items-center justify-center gap-2 rounded-2xl
                       border-2 border-dashed border-[var(--border)] text-[var(--fg-secondary)]
                       transition-colors hover:border-[var(--accent)] hover:text-[var(--accent)]"
          >
            <span className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-[var(--bg-muted)]">
              <Plus size={18} />
            </span>
            <span className="text-sm font-medium">新建笔记本</span>
            <span className="text-xs text-[var(--fg-tertiary)]">链接 / 本地视频</span>
          </button>

          {loading
            ? Array.from({ length: 7 }).map((_, i) => (
                <div key={i} className="min-h-44 animate-pulse rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] p-4">
                  <div className="h-9 w-9 rounded-full bg-[var(--bg-muted)]" />
                  <div className="mt-4 h-4 w-3/4 rounded bg-[var(--bg-muted)]" />
                  <div className="mt-2 h-4 w-1/2 rounded bg-[var(--bg-muted)]" />
                  <div className="mt-6 h-3 w-2/3 rounded bg-[var(--bg-muted)]" />
                </div>
              ))
            : items.map(item => {
                const { icon: Icon, color } = domainStyle(item.domain);
                return (
                  <motion.article
                    key={item.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ type: "spring", stiffness: 220, damping: 26 }}
                    className="apple-card group relative min-h-44"
                  >
                    {item.mine && (
                      <button
                        type="button"
                        onClick={() => remove(item.id)}
                        disabled={delId === item.id}
                        title="删除笔记"
                        className="absolute right-3 top-3 z-10 inline-flex h-7 w-7 items-center justify-center
                                   rounded-full bg-[var(--bg-muted)] text-[var(--fg-tertiary)] opacity-0
                                   transition-all hover:bg-[#d93025] hover:text-white
                                   group-hover:opacity-100 disabled:opacity-60"
                      >
                        {delId === item.id
                          ? <Loader2 size={13} className="animate-spin" />
                          : <Trash2 size={13} />}
                      </button>
                    )}
                    <Link href={`/notes/${item.id}`} className="flex h-full flex-col p-4">
                      <span
                        className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-[var(--bg-muted)]"
                        style={{ color }}
                      >
                        <Icon size={17} />
                      </span>
                      <h3 className="mt-3 line-clamp-2 flex-1 text-[15px] font-medium leading-snug text-[var(--fg)]">
                        {item.title}
                      </h3>
                      <div className="mt-3 flex items-center gap-2.5 text-xs text-[var(--fg-tertiary)]">
                        <span className="inline-flex items-center gap-1 tabular-nums">
                          <Clock size={11} /> {formatDuration(item.duration_sec)}
                        </span>
                        <span className="inline-flex items-center gap-1">
                          <Layers size={11} /> {item.chapters} 章
                        </span>
                        <span className="ml-auto flex items-center gap-1.5">
                          <span className="rounded-full bg-[var(--bg-muted)] px-2 py-0.5 text-[11px] text-[var(--fg-secondary)]">
                            {item.domain}
                          </span>
                          {item.mine && (
                            <span className="rounded-full bg-[color-mix(in_srgb,var(--accent)_14%,transparent)] px-2 py-0.5 text-[11px] text-[var(--accent)]">
                              我的
                            </span>
                          )}
                        </span>
                      </div>
                    </Link>
                  </motion.article>
                );
              })}
        </div>

        {!loading && items.length === 0 && (
          <div className="mt-10 text-center text-sm text-[var(--fg-secondary)]">
            {filter === "mine"
              ? "还没有私有笔记。点「新建笔记本」提交一个视频试试。"
              : "暂时没有可显示的笔记。"}
          </div>
        )}
      </section>

      {/* 新建笔记本弹层 */}
      <AnimatePresence>
        {createOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto
                       bg-black/40 px-4 py-16 backdrop-blur-sm"
            onClick={() => setCreateOpen(false)}
            role="dialog"
            aria-modal="true"
            aria-label="新建笔记本"
          >
            <motion.div
              initial={{ opacity: 0, y: 16, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 16, scale: 0.98 }}
              transition={{ type: "spring", stiffness: 300, damping: 30 }}
              className="w-full max-w-xl"
              onClick={e => e.stopPropagation()}
            >
              <div className="mb-2 flex items-center justify-between px-1">
                <span className="text-sm font-medium text-white drop-shadow">新建笔记本</span>
                <button
                  type="button"
                  onClick={() => setCreateOpen(false)}
                  className="inline-flex h-7 w-7 items-center justify-center rounded-full
                             bg-white/20 text-white transition-colors hover:bg-white/30"
                  aria-label="关闭"
                >
                  <X size={14} />
                </button>
              </div>
              <CreateNotePanel next="/notebooks" />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </main>
  );
}

export default function NotebooksPage() {
  return <RequireAuth><NotebooksInner /></RequireAuth>;
}
