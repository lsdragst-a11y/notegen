"use client";
import { useCallback, useEffect, useState } from "react";

/**
 * 章节学习进度（「已学完」勾选），localStorage 按笔记隔离。
 * 单页内只在 page 层调一次，向下传 done/toggle，避免多实例状态漂移。
 */
export function useChapterProgress(noteId: string) {
  const key = `notegen-chapter-done:${noteId}`;
  const [done, setDone] = useState<number[]>([]);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(key);
      setDone(raw ? (JSON.parse(raw) as number[]).filter(n => Number.isInteger(n)) : []);
    } catch {
      setDone([]);
    }
  }, [key]);

  const toggle = useCallback((idx: number) => {
    setDone(prev => {
      const next = prev.includes(idx) ? prev.filter(i => i !== idx) : [...prev, idx];
      try { localStorage.setItem(key, JSON.stringify(next)); } catch { /* 隐私模式静默 */ }
      return next;
    });
  }, [key]);

  return { done, toggle };
}
