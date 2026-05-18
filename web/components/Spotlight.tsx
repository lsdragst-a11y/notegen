"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, BookOpen, Hash, FileText, CornerDownLeft } from "lucide-react";
import type { Chapter, Chunk, DisplayLang } from "@/lib/types";
import type { GlossaryEntry } from "@/lib/notes";
import { formatTime } from "@/lib/notes";
import { useLang, pickByLang } from "./LangContext";

type Kind = "chapter" | "chunk" | "term";

interface Item {
  kind: Kind;
  label: string;
  detail?: string;
  time: number;
  key: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onSeek: (sec: number) => void;
  chapters: Chapter[];
  summary: Chunk[];
  glossary: GlossaryEntry[];
}

const KIND_META: Record<Kind, { label: string; icon: React.ComponentType<{ size?: number }> }> = {
  chapter: { label: "章节", icon: BookOpen },
  chunk: { label: "知识点", icon: Hash },
  term: { label: "术语", icon: FileText },
};

function buildItems(
  chapters: Chapter[], summary: Chunk[], glossary: GlossaryEntry[],
  lang: DisplayLang = "zh",
): Item[] {
  const out: Item[] = [];
  const chPrefix = lang === "en" ? "Ch" : "第";
  const chSuffix = lang === "en" ? "" : "章 · ";
  chapters.forEach((ch, i) => {
    out.push({
      kind: "chapter",
      label: `${chPrefix} ${i + 1} ${chSuffix}${pickByLang(ch, "title", lang)}`,
      detail: pickByLang(ch, "abstract", lang),
      time: ch.start,
      key: `ch-${i}`,
    });
    (ch.children || []).forEach((sub, si) => {
      out.push({
        kind: "chapter",
        label: `${i + 1}.${si + 1} · ${pickByLang(sub, "title", lang)}`,
        detail: pickByLang(sub, "abstract", lang),
        time: sub.start,
        key: `ch-${i}-${si}`,
      });
    });
  });
  summary.forEach((c, i) => {
    out.push({
      kind: "chunk",
      label: pickByLang(c, "headline", lang) || c.text.slice(0, 30),
      detail: (c.keywords || []).slice(0, 5).join(" · "),
      time: c.start,
      key: `cu-${i}`,
    });
  });
  glossary.forEach(g => {
    out.push({
      kind: "term",
      label: g.term,
      detail: g.snippet || `出现 ${g.df} 次`,
      time: g.firstStart,
      key: `tm-${g.term}`,
    });
  });
  return out;
}

function scoreItem(it: Item, query: string): number {
  const l = it.label.toLowerCase();
  const d = (it.detail || "").toLowerCase();
  if (l === query) return 100;
  if (l.startsWith(query)) return 70;
  if (l.includes(query)) return 50;
  if (d.includes(query)) return 20;
  return 0;
}

function Panel({
  onClose, onSeek, chapters, summary, glossary,
}: Omit<Props, "open">) {
  const [q, setQ] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const { lang } = useLang();
  const items = useMemo(
    () => buildItems(chapters, summary, glossary, lang),
    [chapters, summary, glossary, lang]
  );

  const filtered = useMemo(() => {
    const query = q.trim().toLowerCase();
    if (!query) return items.slice(0, 40);
    return items
      .map(it => [it, scoreItem(it, query)] as const)
      .filter(([, s]) => s > 0)
      .sort((a, b) => b[1] - a[1])
      .map(([it]) => it)
      .slice(0, 50);
  }, [items, q]);

  // mount 时 focus 输入框
  useEffect(() => {
    const t = setTimeout(() => inputRef.current?.focus(), 30);
    return () => clearTimeout(t);
  }, []);

  // 键盘导航
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setCursor(c => Math.min(filtered.length - 1, c + 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setCursor(c => Math.max(0, c - 1));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const sel = filtered[cursor];
        if (sel) {
          onSeek(sel.time);
          onClose();
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [filtered, cursor, onClose, onSeek]);

  // 滚动选中项进入视野
  useEffect(() => {
    if (!listRef.current) return;
    const el = listRef.current.querySelector<HTMLElement>(`[data-cursor="${cursor}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  const safeCursor = Math.min(cursor, Math.max(0, filtered.length - 1));

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.15 }}
      className="fixed inset-0 z-50 flex items-start justify-center pt-[14vh] px-4"
      onClick={onClose}
      style={{ background: "rgba(0,0,0,0.42)", backdropFilter: "blur(8px)" }}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: -8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: -8 }}
        transition={{ type: "spring", stiffness: 360, damping: 28 }}
        className="glass w-full max-w-xl rounded-2xl overflow-hidden shadow-[var(--shadow-lg)]
                   flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[var(--border)]">
          <Search size={16} className="text-[var(--fg-tertiary)] shrink-0" />
          <input
            ref={inputRef}
            value={q}
            onChange={e => { setQ(e.target.value); setCursor(0); }}
            placeholder="搜索章节 / 知识点 / 术语…"
            className="flex-1 bg-transparent outline-none text-sm placeholder:text-[var(--fg-tertiary)]"
          />
          <kbd className="text-[10px] text-[var(--fg-tertiary)] px-1.5 py-0.5 rounded
                          border border-[var(--border)]">Esc</kbd>
        </div>
        <div ref={listRef} className="max-h-[55vh] overflow-y-auto py-1">
          {filtered.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-[var(--fg-tertiary)]">
              没有匹配
            </div>
          ) : filtered.map((it, i) => {
            const meta = KIND_META[it.kind];
            const Icon = meta.icon;
            const active = i === safeCursor;
            return (
              <button
                key={it.key}
                data-cursor={i}
                onMouseEnter={() => setCursor(i)}
                onClick={() => { onSeek(it.time); onClose(); }}
                className={`w-full text-left px-3 py-2 flex items-center gap-3
                            ${active ? "bg-[var(--bg-muted)]" : ""}`}
              >
                <span className={`w-7 h-7 rounded-lg inline-flex items-center justify-center shrink-0
                                   ${active ? "bg-[var(--accent)] text-white"
                                            : "bg-[var(--bg-muted)] text-[var(--fg-secondary)]"}`}>
                  <Icon size={14} />
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate text-[var(--fg)]">{it.label}</div>
                  {it.detail && (
                    <div className="text-xs text-[var(--fg-tertiary)] truncate">{it.detail}</div>
                  )}
                </div>
                <span className="text-[10px] text-[var(--fg-tertiary)] mr-1 shrink-0">
                  {meta.label}
                </span>
                <span className="tabular-nums text-xs text-[var(--fg-tertiary)] shrink-0">
                  {formatTime(it.time)}
                </span>
                {active && <CornerDownLeft size={12} className="text-[var(--accent)] shrink-0" />}
              </button>
            );
          })}
        </div>
        <div className="px-4 py-2 border-t border-[var(--border)] flex items-center justify-between
                        text-[10px] text-[var(--fg-tertiary)]">
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-1">
              <kbd className="px-1 rounded border border-[var(--border)]">↑</kbd>
              <kbd className="px-1 rounded border border-[var(--border)]">↓</kbd>
              导航
            </span>
            <span className="inline-flex items-center gap-1">
              <kbd className="px-1 rounded border border-[var(--border)]">Enter</kbd>
              跳转
            </span>
          </div>
          <span>{filtered.length} 项</span>
        </div>
      </motion.div>
    </motion.div>
  );
}

export default function Spotlight(props: Props) {
  return (
    <AnimatePresence>
      {props.open && <Panel {...props} />}
    </AnimatePresence>
  );
}
