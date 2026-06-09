"use client";
import { useEffect, useState } from "react";
import { API_BASE } from "./api";

/**
 * User bookmarks are now backend-synced. localStorage remains as an offline /
 * anonymous fallback and as an optimistic cache for instant UI updates.
 */
export interface Bookmark {
  key: string;
  noteId: string;
  noteTitle: string;
  kind: "chunk" | "chapter";
  idx: number;
  title: string;
  title_en?: string;
  time: number;
  keyframeRel?: string;
  categoryIds: string[];
  addedAt: number;
}

export type BookmarkBase = Omit<Bookmark, "categoryIds" | "addedAt">;

export interface Category {
  id: string;
  name: string;
  color: string;
  createdAt: number;
}

interface BookmarkState {
  bookmarks: Bookmark[];
  categories: Category[];
}

const BM_KEY = "notegen.bookmarks";
const CAT_KEY = "notegen.bookmarkCategories";
export const BOOKMARKS_EVENT = "notegen:bookmarks-changed";

const PALETTE = ["#0a84ff", "#bf5af2", "#30d158", "#ff9f0a", "#ff375f", "#5e5ce6", "#64d2ff", "#ffd60a"];
let remoteInflight: Promise<void> | null = null;
let lastRemoteSync = 0;

export function bookmarkKey(noteId: string, kind: Bookmark["kind"], idx: number): string {
  return `${noteId}:${kind}:${idx}`;
}

function normalizeBookmark(b: Bookmark): Bookmark {
  return {
    ...b,
    categoryIds: Array.isArray(b.categoryIds) ? b.categoryIds : [],
    addedAt: Number(b.addedAt || Date.now()),
  };
}

function read(): Bookmark[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(BM_KEY);
    const arr = raw ? JSON.parse(raw) : [];
    return Array.isArray(arr) ? (arr as Bookmark[]).map(normalizeBookmark) : [];
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
  if (typeof window !== "undefined") window.dispatchEvent(new Event(BOOKMARKS_EVENT));
}

function writeBookmarks(list: Bookmark[], shouldEmit = true): void {
  try {
    localStorage.setItem(BM_KEY, JSON.stringify(list.map(normalizeBookmark)));
    if (shouldEmit) emit();
  } catch {}
}

function writeCats(cats: Category[], shouldEmit = true): void {
  try {
    localStorage.setItem(CAT_KEY, JSON.stringify(cats));
    if (shouldEmit) emit();
  } catch {}
}

function applyState(state: BookmarkState): void {
  writeCats(state.categories || [], false);
  writeBookmarks((state.bookmarks || []).map(normalizeBookmark), false);
  emit();
}

async function fetchRemoteState(): Promise<BookmarkState | null> {
  const r = await fetch(`${API_BASE}/api/bookmarks`, {
    credentials: "include",
    cache: "no-store",
  });
  if (!r.ok) return null;
  return r.json();
}

async function putRemoteBookmark(bookmark: Bookmark): Promise<BookmarkState | null> {
  const r = await fetch(`${API_BASE}/api/bookmarks`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(bookmark),
  });
  if (!r.ok) return null;
  return r.json();
}

async function deleteRemoteBookmark(key: string): Promise<BookmarkState | null> {
  const r = await fetch(`${API_BASE}/api/bookmarks/${encodeURIComponent(key)}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!r.ok) return null;
  return r.json();
}

async function putRemoteCategory(cat: Category): Promise<BookmarkState | null> {
  const r = await fetch(`${API_BASE}/api/bookmark-categories`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cat),
  });
  if (!r.ok) return null;
  return r.json();
}

async function renameRemoteCategory(id: string, name: string): Promise<BookmarkState | null> {
  const r = await fetch(`${API_BASE}/api/bookmark-categories/${encodeURIComponent(id)}`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!r.ok) return null;
  return r.json();
}

async function deleteRemoteCategory(id: string): Promise<BookmarkState | null> {
  const r = await fetch(`${API_BASE}/api/bookmark-categories/${encodeURIComponent(id)}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!r.ok) return null;
  return r.json();
}

async function pushLocalStateToBackend(): Promise<void> {
  const cats = readCats();
  const bookmarks = read();
  for (const cat of cats) {
    await putRemoteCategory(cat);
  }
  for (const bookmark of bookmarks) {
    await putRemoteBookmark(bookmark);
  }
}

async function refreshFromBackend(force = false): Promise<void> {
  if (typeof window === "undefined") return;
  const now = Date.now();
  if (!force && now - lastRemoteSync < 1200) return;
  if (remoteInflight) return remoteInflight;
  remoteInflight = (async () => {
    try {
      const state = await fetchRemoteState();
      if (!state) return;
      const localHasData = read().length > 0 || readCats().length > 0;
      const remoteEmpty = (state.bookmarks?.length || 0) === 0 && (state.categories?.length || 0) === 0;
      if (remoteEmpty && localHasData) {
        await pushLocalStateToBackend();
        const next = await fetchRemoteState();
        if (next) applyState(next);
      } else {
        applyState(state);
      }
      lastRemoteSync = Date.now();
    } catch {
      // Offline / anonymous fallback keeps localStorage usable.
    } finally {
      remoteInflight = null;
    }
  })();
  return remoteInflight;
}

function syncAfterRemote(p: Promise<BookmarkState | null>): void {
  void p.then(state => {
    if (state) {
      applyState(state);
      lastRemoteSync = Date.now();
    }
  }).catch(() => {});
}

export function getBookmarks(): Bookmark[] {
  return read();
}

export function getBookmark(key: string): Bookmark | undefined {
  return read().find(b => b.key === key);
}

export function isBookmarked(key: string): boolean {
  return read().some(b => b.key === key);
}

export function saveBookmark(base: BookmarkBase): void {
  const list = read();
  if (list.some(b => b.key === base.key)) return;
  const bookmark = { ...base, categoryIds: [], addedAt: Date.now() };
  writeBookmarks([...list, bookmark]);
  syncAfterRemote(putRemoteBookmark(bookmark));
}

export function removeBookmark(key: string): void {
  writeBookmarks(read().filter(b => b.key !== key));
  syncAfterRemote(deleteRemoteBookmark(key));
}

export function toggleBookmarkCategory(base: BookmarkBase, catId: string): void {
  const list = read();
  const i = list.findIndex(b => b.key === base.key);
  let bookmark: Bookmark;
  if (i >= 0) {
    const cur = list[i].categoryIds || [];
    const has = cur.includes(catId);
    bookmark = { ...list[i], categoryIds: has ? cur.filter(c => c !== catId) : [...cur, catId] };
    list[i] = bookmark;
  } else {
    bookmark = { ...base, categoryIds: [catId], addedAt: Date.now() };
    list.push(bookmark);
  }
  writeBookmarks(list);
  syncAfterRemote(putRemoteBookmark(bookmark));
}

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
  writeCats([...cats, cat]);
  syncAfterRemote(putRemoteCategory(cat));
  return cat;
}

export function renameCategory(id: string, name: string): void {
  const n = name.trim();
  if (!n) return;
  writeCats(readCats().map(c => (c.id === id ? { ...c, name: n } : c)));
  syncAfterRemote(renameRemoteCategory(id, n));
}

export function removeCategory(id: string): void {
  writeCats(readCats().filter(c => c.id !== id));
  const list = read();
  const next = list.map(b => (
    b.categoryIds?.includes(id)
      ? { ...b, categoryIds: b.categoryIds.filter(c => c !== id) }
      : b
  ));
  writeBookmarks(next);
  syncAfterRemote(deleteRemoteCategory(id));
}

function useSync<T>(getter: () => T, deps: unknown[] = []): T {
  const [val, setVal] = useState<T>(getter);
  useEffect(() => {
    const sync = () => setVal(getter());
    sync();
    void refreshFromBackend();
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
