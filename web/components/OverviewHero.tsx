"use client";
import { motion } from "framer-motion";
import { FileText, Sparkles } from "lucide-react";
import type { Chapter, Overview } from "@/lib/types";
import { formatTime } from "@/lib/notes";
import { useLang, pickByLang } from "./LangContext";

interface Props {
  overview: Overview;
  chapters: Chapter[];
  currentTime: number;
  onSeek: (sec: number) => void;
}

/**
 * 文档级「全文总结」hero：散文概览 + 「你将学到」要点 + 按时长比例的可点击章节条。
 * overview / takeaways 走 lang fallback（缺 _en 回退中文），无 overview 时不渲染。
 */
export default function OverviewHero({ overview, chapters, currentTime, onSeek }: Props) {
  const { lang } = useLang();
  const summary = pickByLang(overview, "summary", lang);
  const takeaways = (() => {
    const t = (overview as unknown as Record<string, unknown>)[`takeaways_${lang}`];
    if (Array.isArray(t) && t.length) return t as string[];
    return overview.takeaways || [];
  })();
  if (!summary && takeaways.length === 0) return null;

  const span = chapters.length
    ? chapters[chapters.length - 1].end - chapters[0].start
    : 0;
  const curIdx = chapters.findIndex(c => currentTime >= c.start && currentTime < c.end);

  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 200, damping: 24, delay: 0.05 }}
      className="apple-card p-6"
    >
      <h2 className="flex items-center gap-2 text-base font-semibold text-[var(--fg)]">
        <FileText size={16} className="text-[var(--accent)]" />
        {lang === "en" ? "Overview" : "全文总结"}
      </h2>
      {summary && (
        <p className="mt-2.5 text-sm leading-relaxed text-[var(--fg-secondary)]">
          {summary}
        </p>
      )}

      {takeaways.length > 0 && (
        <div className="mt-4">
          <div className="flex items-center gap-1.5 text-sm font-medium text-[var(--fg)]">
            <Sparkles size={13} className="text-[var(--accent)]" />
            {lang === "en" ? "What you'll learn" : "你将学到"}
          </div>
          <ul className="mt-2 flex flex-col gap-1.5">
            {takeaways.map((t, i) => (
              <li key={i}
                  className="flex gap-2 text-sm text-[var(--fg-secondary)] leading-snug">
                <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--accent)]" />
                <span>{t}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {chapters.length > 1 && span > 0 && (
        <div className="mt-5">
          <div className="flex items-center justify-between text-xs text-[var(--fg-tertiary)] mb-1.5">
            <span>{lang === "en" ? "Chapters" : "章节构成"} · {formatTime(span)}</span>
            <span>{lang === "en" ? "click to jump" : "点击跳转"}</span>
          </div>
          <div className="flex gap-1 h-9">
            {chapters.map((ch, i) => {
              const pct = ((ch.end - ch.start) / span) * 100;
              const active = i === curIdx;
              return (
                <button
                  key={i}
                  onClick={() => onSeek(ch.start)}
                  title={`${i + 1}. ${pickByLang(ch, "title", lang)} · ${formatTime(ch.start)}`}
                  style={{ flexGrow: pct, flexBasis: 0, minWidth: 22 }}
                  className={`rounded-md transition-all flex items-center justify-center
                              text-[11px] font-medium tabular-nums
                              ${active
                                ? "bg-[var(--accent)] text-white shadow-[var(--shadow-sm)]"
                                : "bg-[var(--bg-muted)] text-[var(--fg-tertiary)] "
                                  + "hover:text-[var(--fg)] hover:ring-1 hover:ring-[var(--accent)]"}`}
                >
                  {i + 1}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </motion.section>
  );
}
