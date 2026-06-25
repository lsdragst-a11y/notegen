"use client";
import { useCallback, useSyncExternalStore } from "react";

const STORAGE_PREFIX = "notegen-chapter-done:";
const EMPTY_DONE: number[] = [];

type CacheEntry = {
  raw: string | null;
  value: number[];
};

const snapshotCache = new Map<string, CacheEntry>();
const listeners = new Set<() => void>();

function storageKey(noteId: string) {
  return `${STORAGE_PREFIX}${noteId}`;
}

function parseDone(raw: string | null) {
  if (!raw) return EMPTY_DONE;
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter(n => Number.isInteger(n)) : EMPTY_DONE;
  } catch {
    return EMPTY_DONE;
  }
}

function readDone(key: string) {
  if (typeof window === "undefined") return EMPTY_DONE;
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(key);
  } catch {
    return EMPTY_DONE;
  }

  const cached = snapshotCache.get(key);
  if (cached?.raw === raw) return cached.value;

  const value = parseDone(raw);
  snapshotCache.set(key, { raw, value });
  return value;
}

function emitProgressChange() {
  for (const listener of listeners) listener();
}

function subscribeProgress(listener: () => void) {
  listeners.add(listener);

  function onStorage(event: StorageEvent) {
    if (!event.key?.startsWith(STORAGE_PREFIX)) return;
    emitProgressChange();
  }

  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

function writeDone(key: string, next: number[]) {
  try {
    window.localStorage.setItem(key, JSON.stringify(next));
  } catch {
    // Ignore private browsing or storage quota failures.
  }
  snapshotCache.delete(key);
  emitProgressChange();
}

/**
 * 章节学习进度（“已学完”勾选），localStorage 按笔记隔离。
 * 单页内只在 page 层调一次，向下传 done/toggle，避免多实例状态漂移。
 */
export function useChapterProgress(noteId: string) {
  const key = storageKey(noteId);
  const done = useSyncExternalStore(
    subscribeProgress,
    () => readDone(key),
    () => EMPTY_DONE,
  );

  const toggle = useCallback((idx: number) => {
    const current = readDone(key);
    const next = current.includes(idx) ? current.filter(i => i !== idx) : [...current, idx];
    writeDone(key, next);
  }, [key]);

  return { done, toggle };
}
