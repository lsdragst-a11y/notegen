"use client";
import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import type { DisplayLang } from "@/lib/types";

interface Ctx {
  lang: DisplayLang;
  setLang: (l: DisplayLang) => void;
}

const LangCtx = createContext<Ctx>({ lang: "zh", setLang: () => {} });

const STORAGE_KEY = "notegen.displayLang";

export function LangProvider({ children }: { children: ReactNode }) {
  // SSR-safe 初始值 "zh"，mount 后从 localStorage 读真值
  const [lang, setLangState] = useState<DisplayLang>("zh");
  useEffect(() => {
    try {
      const v = localStorage.getItem(STORAGE_KEY);
      if (v === "zh" || v === "en") setLangState(v);
    } catch {}
  }, []);
  const setLang = (l: DisplayLang) => {
    setLangState(l);
    try { localStorage.setItem(STORAGE_KEY, l); } catch {}
  };
  return <LangCtx.Provider value={{ lang, setLang }}>{children}</LangCtx.Provider>;
}

export function useLang(): Ctx {
  return useContext(LangCtx);
}

/**
 * 通用文本选择：优先 _zh/_en 字段，缺失 fallback 到原字段 base 或空串。
 * 用于 chapter.title / chapter.abstract / chunk.headline。
 */
export function pickByLang(
  obj: object | null | undefined,
  baseKey: string,
  lang: DisplayLang
): string {
  if (!obj) return "";
  const rec = obj as Record<string, unknown>;
  const v = rec[`${baseKey}_${lang}`];
  if (typeof v === "string" && v) return v;
  const base = rec[baseKey];
  return typeof base === "string" ? base : "";
}
