"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import {
  Bookmark as BookmarkIcon, Play, X, Layers, BookOpen, Settings2, Trash2, Plus,
} from "lucide-react";
import NavBar from "@/components/NavBar";
import BookmarkMenu from "@/components/BookmarkMenu";
import { useLang } from "@/components/LangContext";
import {
  useBookmarksList, useCategories, removeBookmark,
  renameCategory, removeCategory, addCategory,
  type Bookmark, type Category, type BookmarkBase,
} from "@/lib/bookmarks";
import { formatTime } from "@/lib/notes";

const ALL = "__all__";
const UNCAT = "__uncat__";

export default function BookmarksPage() {
  const { lang } = useLang();
  const list = useBookmarksList();
  const cats = useCategories();
  const [filter, setFilter] = useState<string>(ALL);
  const [manage, setManage] = useState(false);
  const [newCat, setNewCat] = useState("");

  const catById = useMemo(() => {
    const m = new Map<string, Category>();
    cats.forEach(c => m.set(c.id, c));
    return m;
  }, [cats]);

  const catCounts = useMemo(() => {
    const m: Record<string, number> = {};
    for (const b of list) for (const id of b.categoryIds || []) m[id] = (m[id] || 0) + 1;
    return m;
  }, [list]);

  const uncatCount = useMemo(
    () => list.filter(b => !(b.categoryIds?.length)).length,
    [list],
  );

  const filtered = useMemo(() => {
    if (filter === ALL) return list;
    if (filter === UNCAT) return list.filter(b => !(b.categoryIds?.length));
    return list.filter(b => b.categoryIds?.includes(filter));
  }, [list, filter]);

  // 按笔记分组；组内按时间升序，组间按最近收藏时间降序
  const groups = useMemo(() => {
    const m = new Map<string, { noteId: string; noteTitle: string; items: Bookmark[] }>();
    for (const b of filtered) {
      const g = m.get(b.noteId) || { noteId: b.noteId, noteTitle: b.noteTitle, items: [] };
      g.items.push(b);
      m.set(b.noteId, g);
    }
    const arr = Array.from(m.values());
    arr.forEach(g => g.items.sort((a, b) => a.time - b.time));
    arr.sort((a, b) => Math.max(...b.items.map(i => i.addedAt)) - Math.max(...a.items.map(i => i.addedAt)));
    return arr;
  }, [filtered]);

  const titleOf = (b: Bookmark) => (lang === "en" && b.title_en ? b.title_en : b.title);
  const baseOf = (b: Bookmark): BookmarkBase => ({
    key: b.key, noteId: b.noteId, noteTitle: b.noteTitle, kind: b.kind,
    idx: b.idx, title: b.title, title_en: b.title_en, time: b.time, keyframeRel: b.keyframeRel,
  });

  const Chip = ({ id, label, count, color }: { id: string; label: string; count: number; color?: string }) => {
    const active = filter === id;
    return (
      <button
        onClick={() => setFilter(id)}
        className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors
          ${active
            ? "border-transparent bg-[var(--accent)] text-white"
            : "border-[var(--border)] text-[var(--fg-secondary)] hover:bg-[var(--bg-muted)]"}`}
      >
        {color && <span className="h-2 w-2 rounded-full" style={{ background: color }} />}
        {label}
        <span className={active ? "text-white/80" : "text-[var(--fg-tertiary)]"}>{count}</span>
      </button>
    );
  };

  return (
    <main className="min-h-screen pb-24">
      <NavBar>
        <div className="flex items-center gap-2 min-w-0">
          <BookmarkIcon size={14} className="text-[var(--accent)] shrink-0" />
          <span className="text-sm font-medium truncate">
            {lang === "en" ? "My Bookmarks" : "我的书签"}
          </span>
        </div>
      </NavBar>

      <div className="max-w-3xl mx-auto px-6 mt-8">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              {lang === "en" ? "My Bookmarks" : "我的书签"}
            </h1>
            <p className="mt-1.5 text-sm text-[var(--fg-secondary)]">
              {lang === "en"
                ? `${list.length} saved · synced to this browser`
                : `共 ${list.length} 条 · 保存在本浏览器`}
            </p>
          </div>
          {cats.length > 0 && (
            <button
              onClick={() => setManage(m => !m)}
              className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs
                font-medium transition-colors
                ${manage
                  ? "border-transparent bg-[var(--bg-muted)] text-[var(--fg)]"
                  : "border-[var(--border)] text-[var(--fg-secondary)] hover:bg-[var(--bg-muted)]"}`}
            >
              <Settings2 size={13} />
              {lang === "en" ? "Manage categories" : "管理分类"}
            </button>
          )}
        </div>

        {/* 分类筛选条 */}
        <div className="mt-5 flex flex-wrap gap-2">
          <Chip id={ALL} label={lang === "en" ? "All" : "全部"} count={list.length} />
          {cats.map(c => (
            <Chip key={c.id} id={c.id} label={c.name} count={catCounts[c.id] || 0} color={c.color} />
          ))}
          {uncatCount > 0 && (
            <Chip id={UNCAT} label={lang === "en" ? "Uncategorized" : "未分类"} count={uncatCount} />
          )}
        </div>

        {/* 分类管理面板 */}
        {manage && (
          <div className="apple-card mt-4 flex flex-col gap-1.5 p-3">
            {cats.map(c => (
              <div key={c.id} className="flex items-center gap-2">
                <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: c.color }} />
                <input
                  defaultValue={c.name}
                  onBlur={e => { const v = e.target.value.trim(); if (v && v !== c.name) renameCategory(c.id, v); }}
                  className="min-w-0 flex-1 rounded-md bg-[var(--bg-muted)] px-2 py-1.5 text-sm
                             text-[var(--fg)] outline-none focus:ring-1 focus:ring-[var(--accent)]"
                />
                <span className="shrink-0 text-xs tabular-nums text-[var(--fg-tertiary)]">
                  {catCounts[c.id] || 0}
                </span>
                <button
                  onClick={() => { if (filter === c.id) setFilter(ALL); removeCategory(c.id); }}
                  title={lang === "en" ? "Delete category" : "删除分类"}
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md
                             text-[var(--fg-tertiary)] transition-colors hover:bg-[var(--bg-muted)]
                             hover:text-[#ff453a]"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
            <form
              onSubmit={e => { e.preventDefault(); if (addCategory(newCat)) setNewCat(""); }}
              className="mt-1 flex items-center gap-1.5 border-t border-[var(--border)] pt-2"
            >
              <input
                value={newCat}
                onChange={e => setNewCat(e.target.value)}
                placeholder={lang === "en" ? "New category…" : "新建分类…"}
                className="min-w-0 flex-1 rounded-md bg-[var(--bg-muted)] px-2 py-1.5 text-sm
                           text-[var(--fg)] outline-none placeholder:text-[var(--fg-tertiary)]
                           focus:ring-1 focus:ring-[var(--accent)]"
              />
              <button
                type="submit"
                disabled={!newCat.trim()}
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md
                           bg-[var(--accent)] text-white transition-opacity hover:opacity-90 disabled:opacity-40"
              >
                <Plus size={14} />
              </button>
            </form>
            <p className="px-0.5 text-[11px] text-[var(--fg-tertiary)]">
              {lang === "en"
                ? "Deleting a category keeps its bookmarks (they become uncategorized)."
                : "删除分类不会删除其中的书签（书签会变为未分类）。"}
            </p>
          </div>
        )}

        {groups.length === 0 ? (
          <div className="apple-card mt-8 flex flex-col items-center gap-3 p-12 text-center">
            <BookmarkIcon size={32} className="text-[var(--fg-tertiary)]" />
            <p className="text-sm text-[var(--fg-secondary)]">
              {list.length === 0
                ? (lang === "en"
                    ? "No bookmarks yet. Tap the bookmark icon on any key point or chapter to save it here."
                    : "还没有书签。在任意知识点或章节上点书签图标，就会收藏到这里。")
                : (lang === "en"
                    ? "No bookmarks in this category."
                    : "这个分类下还没有书签。")}
            </p>
            {list.length === 0 && (
              <Link href="/" className="apple-button mt-2 inline-flex">
                {lang === "en" ? "Browse notes" : "去浏览笔记"}
              </Link>
            )}
          </div>
        ) : (
          <div className="mt-8 flex flex-col gap-8">
            {groups.map(g => (
              <section key={g.noteId}>
                <Link href={`/notes/${g.noteId}`}
                      className="group inline-flex items-center gap-1.5 text-sm font-semibold
                                 text-[var(--fg)] hover:text-[var(--accent)] transition-colors">
                  {g.noteTitle}
                  <span className="text-xs font-normal text-[var(--fg-tertiary)]">
                    ({g.items.length})
                  </span>
                </Link>
                <div className="mt-3 flex flex-col gap-2">
                  {g.items.map(b => (
                    <div key={b.key}
                         className="apple-card flex items-center gap-3 p-2.5 pr-3">
                      <Link
                        href={`/notes/${b.noteId}?t=${Math.floor(b.time)}`}
                        className="group flex min-w-0 flex-1 items-center gap-3"
                      >
                        {/* 缩略图 / 章节图标 */}
                        {b.kind === "chunk" && b.keyframeRel ? (
                          <span className="relative h-12 w-20 shrink-0 overflow-hidden rounded-lg
                                           bg-[var(--bg-muted)]">
                            <img src={`/notes/${b.noteId}/keyframes/${b.keyframeRel}`} alt=""
                                 className="h-full w-full object-cover dark:brightness-90
                                            transition-transform group-hover:scale-105" />
                          </span>
                        ) : (
                          <span className="flex h-12 w-20 shrink-0 items-center justify-center
                                           rounded-lg bg-[var(--bg-muted)] text-[var(--fg-tertiary)]">
                            {b.kind === "chapter" ? <Layers size={16} /> : <BookOpen size={16} />}
                          </span>
                        )}
                        <span className="flex min-w-0 flex-1 flex-col">
                          <span className="flex items-center gap-1.5">
                            <span className="rounded px-1.5 py-0.5 text-[10px] font-medium
                                             bg-[var(--bg-muted)] text-[var(--fg-tertiary)]">
                              {b.kind === "chapter"
                                ? (lang === "en" ? "Chapter" : "章节")
                                : (lang === "en" ? "Key point" : "知识点")}
                            </span>
                            <span className="text-xs tabular-nums text-[var(--fg-tertiary)]">
                              {formatTime(b.time)}
                            </span>
                          </span>
                          <span className="mt-0.5 truncate text-sm font-medium text-[var(--fg)]
                                           group-hover:text-[var(--accent)] transition-colors">
                            {titleOf(b)}
                          </span>
                          {/* 分类标签 */}
                          {b.categoryIds?.length > 0 && (
                            <span className="mt-1 flex flex-wrap gap-1">
                              {b.categoryIds.map(id => {
                                const c = catById.get(id);
                                if (!c) return null;
                                return (
                                  <span key={id}
                                        className="rounded px-1.5 py-0.5 text-[10px] font-medium"
                                        style={{ background: `${c.color}22`, color: c.color }}>
                                    {c.name}
                                  </span>
                                );
                              })}
                            </span>
                          )}
                        </span>
                        <Play size={14} className="shrink-0 text-[var(--fg-tertiary)]
                                                   group-hover:text-[var(--accent)] transition-colors" />
                      </Link>
                      <BookmarkMenu
                        size={15}
                        bm={baseOf(b)}
                        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full
                                   text-[var(--fg-tertiary)] hover:bg-[var(--bg-muted)] hover:text-[var(--accent)]"
                      />
                      <button
                        onClick={() => removeBookmark(b.key)}
                        title={lang === "en" ? "Remove" : "移除"}
                        aria-label={lang === "en" ? "Remove bookmark" : "移除书签"}
                        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full
                                   text-[var(--fg-tertiary)] hover:bg-[var(--bg-muted)]
                                   hover:text-[var(--fg)] transition-colors"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
