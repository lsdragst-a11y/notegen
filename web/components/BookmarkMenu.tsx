"use client";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Bookmark as BookmarkIcon, Check, Plus, Trash2 } from "lucide-react";
import {
  type BookmarkBase,
  useBookmark,
  useCategories,
  toggleBookmarkCategory,
  saveBookmark,
  removeBookmark,
  addCategory,
} from "@/lib/bookmarks";
import { useLang } from "./LangContext";

interface Props {
  bm: BookmarkBase;
  size?: number;
  /** 触发按钮额外类名（颜色/背景由调用处给，融入各自底色）。 */
  className?: string;
}

/**
 * 收藏按钮 + 分类选择浮层。点一下打开浮层：勾选/取消已有分类（标签式，可多选）、
 * 内联新建分类、仅收藏不分类、移除书签。stopPropagation 不触发卡片点击/跳转——「加书签不移动视频」。
 * 浮层用 portal 挂到 body（卡片 overflow-hidden 会裁切），fixed 定位贴着触发按钮；
 * 点外部 / Esc / 滚动关闭。
 */
export default function BookmarkMenu({ bm, size = 14, className = "" }: Props) {
  const { lang } = useLang();
  const saved = useBookmark(bm.key);
  const cats = useCategories();
  const on = !!saved;
  const activeIds = saved?.categoryIds || [];

  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const [newName, setNewName] = useState("");
  const btnRef = useRef<HTMLButtonElement>(null);
  const popRef = useRef<HTMLDivElement>(null);

  const place = () => {
    const b = btnRef.current?.getBoundingClientRect();
    if (!b) return;
    const W = 248;
    let left = b.left;
    if (left + W > window.innerWidth - 8) left = window.innerWidth - 8 - W;
    if (left < 8) left = 8;
    setPos({ top: b.bottom + 6, left });
  };

  useLayoutEffect(() => {
    if (open) place();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onDocDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (popRef.current?.contains(t) || btnRef.current?.contains(t)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    const onScroll = () => setOpen(false);
    document.addEventListener("mousedown", onDocDown);
    window.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onScroll);
    return () => {
      document.removeEventListener("mousedown", onDocDown);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onScroll);
    };
  }, [open]);

  const label = on
    ? (lang === "en" ? "Edit bookmark" : "编辑书签")
    : (lang === "en" ? "Add bookmark" : "加入书签");

  const createAndTag = () => {
    const c = addCategory(newName);
    if (c) { toggleBookmarkCategory(bm, c.id); setNewName(""); }
  };

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        onClick={e => { e.stopPropagation(); setOpen(o => !o); }}
        title={label}
        aria-label={label}
        aria-pressed={on}
        aria-expanded={open}
        className={`transition-colors ${on ? "text-[var(--accent)]" : ""} ${className}`}
      >
        <BookmarkIcon size={size} fill={on ? "currentColor" : "none"} />
      </button>

      {open && pos && typeof document !== "undefined" && createPortal(
        <div
          ref={popRef}
          onClick={e => e.stopPropagation()}
          style={{ position: "fixed", top: pos.top, left: pos.left, width: 248 }}
          className="z-[60] flex flex-col rounded-xl border border-[var(--border)]
                     bg-[var(--bg)] p-1.5 shadow-[var(--shadow-md)]"
        >
          <div className="px-2 py-1.5 text-[11px] font-medium uppercase tracking-wide text-[var(--fg-tertiary)]">
            {lang === "en" ? "Categories" : "分类"}
          </div>

          <div className="max-h-52 overflow-y-auto">
            {cats.length === 0 ? (
              <p className="px-2 py-1.5 text-xs text-[var(--fg-tertiary)]">
                {lang === "en" ? "No categories yet — create one below." : "还没有分类，下面新建一个。"}
              </p>
            ) : (
              cats.map(c => {
                const checked = activeIds.includes(c.id);
                return (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => toggleBookmarkCategory(bm, c.id)}
                    className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm
                               text-[var(--fg)] transition-colors hover:bg-[var(--bg-muted)]"
                  >
                    <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded
                                     border transition-colors"
                          style={{
                            borderColor: checked ? c.color : "var(--border)",
                            background: checked ? c.color : "transparent",
                          }}>
                      {checked && <Check size={11} className="text-white" />}
                    </span>
                    <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: c.color }} />
                    <span className="min-w-0 flex-1 truncate">{c.name}</span>
                  </button>
                );
              })
            )}
          </div>

          {/* 新建分类 */}
          <form
            onSubmit={e => { e.preventDefault(); createAndTag(); }}
            className="mt-1 flex items-center gap-1 border-t border-[var(--border)] px-1 pt-1.5"
          >
            <input
              value={newName}
              onChange={e => setNewName(e.target.value)}
              placeholder={lang === "en" ? "New category…" : "新建分类…"}
              className="min-w-0 flex-1 rounded-md bg-[var(--bg-muted)] px-2 py-1.5 text-sm
                         text-[var(--fg)] outline-none placeholder:text-[var(--fg-tertiary)]
                         focus:ring-1 focus:ring-[var(--accent)]"
            />
            <button
              type="submit"
              disabled={!newName.trim()}
              title={lang === "en" ? "Create" : "新建"}
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md
                         bg-[var(--accent)] text-white transition-opacity hover:opacity-90
                         disabled:opacity-40"
            >
              <Plus size={14} />
            </button>
          </form>

          {/* 仅收藏 / 移除 */}
          <div className="mt-1 border-t border-[var(--border)] pt-1">
            {on ? (
              <button
                type="button"
                onClick={() => { removeBookmark(bm.key); setOpen(false); }}
                className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm
                           text-[var(--danger,#ff453a)] transition-colors hover:bg-[var(--bg-muted)]"
              >
                <Trash2 size={14} />
                {lang === "en" ? "Remove bookmark" : "移除书签"}
              </button>
            ) : (
              <button
                type="button"
                onClick={() => saveBookmark(bm)}
                className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm
                           text-[var(--fg-secondary)] transition-colors hover:bg-[var(--bg-muted)]"
              >
                <BookmarkIcon size={14} />
                {lang === "en" ? "Save without category" : "仅收藏（不分类）"}
              </button>
            )}
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
