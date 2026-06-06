"use client";
import { useEffect, useState } from "react";

/**
 * 全局书签 + 用户自定义分类（标签式，一个书签可属多个分类）。
 * 纯前端、存浏览器 localStorage（静态站无后端）。知识点（chunk）和章节（chapter）都能收藏。
 * 写入后派发 BOOKMARKS_EVENT，让 NavBar 计数 / 卡片按钮 / 书签页实时同步。
 */
export interface Bookmark {
  key: string;                  // `${noteId}:${kind}:${idx}` 唯一
  noteId: string;
  noteTitle: string;
  kind: "chunk" | "chapter";
  idx: number;
  title: string;                // 基准/中文标题
  title_en?: string;
  time: number;                 // 跳转时间（秒）
  keyframeRel?: string;         // chunk 缩略图（书签页展示）
  categoryIds: string[];        // 所属分类（可多个，可空=未分类）
  addedAt: number;
}

/** 收藏时调用方提供的基础字段（不含分类/时间戳，由本模块管理）。 */
export type BookmarkBase = Omit<Bookmark, "categoryIds" | "addedAt">;

export interface Category {
  id: string;
  name: string;
  color: string;
  createdAt: number;
}

const BM_KEY = "notegen.bookmarks";
const CAT_KEY = "notegen.bookmarkCategories";
export const BOOKMARKS_EVENT = "notegen:bookmarks-changed";

const PALETTE = ["#0a84ff", "#bf5af2", "#30d158", "#ff9f0a", "#ff375f", "#5e5ce6", "#64d2ff", "#ffd60a"];

export function bookmarkKey(noteId: string, kind: Bookmark["kind"], idx: number): string {
  return `${noteId}:${kind}:${idx}`;
}

// ---- 低层读写 ----

function read(): Bookmark[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(BM_KEY);
    const arr = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(arr)) return [];
    // 兼容旧数据：补 categoryIds
    return (arr as Bookmark[]).map(b => ({
      ...b,
      categoryIds: Array.isArray(b.categoryIds) ? b.categoryIds : [],
    }));
  } catch {
    return [];
  }
}

function readCats(): Category[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(CAT_KEY);
    const arr = raw ? JSON.parse(raw) : [];
    return Array.isArray(arr) ? (arr as Category[]) : [];
  } catch {
    return [];
  }
}

function emit(): void {
  window.dispatchEvent(new Event(BOOKMARKS_EVENT));
}

function writeBookmarks(list: Bookmark[]): void {
  try {
    localStorage.setItem(BM_KEY, JSON.stringify(list));
    emit();
  } catch {}
}

function writeCats(cats: Category[]): void {
  try {
    localStorage.setItem(CAT_KEY, JSON.stringify(cats));
    emit();
  } catch {}
}

// ---- 书签操作 ----

export function getBookmarks(): Bookmark[] {
  return read();
}

export function getBookmark(key: string): Bookmark | undefined {
  return read().find(b => b.key === key);
}

export function isBookmarked(key: string): boolean {
  return read().some(b => b.key === key);
}

/** 仅收藏（不分类）；已存在则 no-op。 */
export function saveBookmark(base: BookmarkBase): void {
  const list = read();
  if (list.some(b => b.key === base.key)) return;
  list.push({ ...base, categoryIds: [], addedAt: Date.now() });
  writeBookmarks(list);
}

export function removeBookmark(key: string): void {
  writeBookmarks(read().filter(b => b.key !== key));
}

/** 切换书签在某分类的归属；书签不存在则自动创建。 */
export function toggleBookmarkCategory(base: BookmarkBase, catId: string): void {
  const list = read();
  const i = list.findIndex(b => b.key === base.key);
  if (i >= 0) {
    const cur = list[i].categoryIds || [];
    const has = cur.includes(catId);
    list[i] = { ...list[i], categoryIds: has ? cur.filter(c => c !== catId) : [...cur, catId] };
  } else {
    list.push({ ...base, categoryIds: [catId], addedAt: Date.now() });
  }
  writeBookmarks(list);
}

// ---- 分类操作 ----

export function getCategories(): Category[] {
  return readCats();
}

export function addCategory(name: string): Category | null {
  const n = name.trim();
  if (!n) return null;
  const cats = readCats();
  const cat: Category = {
    id: `c_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`,
    name: n,
    color: PALETTE[cats.length % PALETTE.length],
    createdAt: Date.now(),
  };
  cats.push(cat);
  writeCats(cats);
  return cat;
}

export function renameCategory(id: string, name: string): void {
  const n = name.trim();
  if (!n) return;
  writeCats(readCats().map(c => (c.id === id ? { ...c, name: n } : c)));
}

/** 删除分类并从所有书签上摘掉该分类（书签本身保留，变未分类）。 */
export function removeCategory(id: string): void {
  writeCats(readCats().filter(c => c.id !== id));
  const list = read();
  let changed = false;
  const next = list.map(b => {
    if (b.categoryIds?.includes(id)) {
      changed = true;
      return { ...b, categoryIds: b.categoryIds.filter(c => c !== id) };
    }
    return b;
  });
  if (changed) writeBookmarks(next);
}

// ---- 订阅 hooks ----

function useSync<T>(getter: () => T, deps: unknown[] = []): T {
  const [val, setVal] = useState<T>(getter);
  useEffect(() => {
    const sync = () => setVal(getter());
    sync();
    window.addEventListener(BOOKMARKS_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(BOOKMARKS_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return val;
}

export function useBookmarksList(): Bookmark[] {
  return useSync(() => read(), []);
}

export function useBookmark(key: string): Bookmark | undefined {
  return useSync(() => read().find(b => b.key === key), [key]);
}

export function useCategories(): Category[] {
  return useSync(() => readCats(), []);
}
