"use client";
import { motion } from "framer-motion";
import { CheckCircle2, ChevronDown, Circle } from "lucide-react";
import type { Chapter, Chunk, Mark } from "@/lib/types";
import { formatTime } from "@/lib/notes";
import { useLang, pickByLang } from "./LangContext";
import ChapterQuiz from "./ChapterQuiz";
import BookmarkMenu from "./BookmarkMenu";
import { bookmarkKey } from "@/lib/bookmarks";

interface Props {
  chapters: Chapter[];
  summary: Chunk[];
  noteId: string;
  noteTitle: string;
  marksByChunk: Mark[][];
  showMarks: boolean;
  headerLabel: string;
  headerIcon: string;
  onSeek: (sec: number) => void;
  /** 章节学习进度（可选） */
  done?: number[];
  onToggleDone?: (idx: number) => void;
  readOnly?: boolean;
}

/** 章节详情区（含小节、知识点 chip、章节自测）。从 NotesContent 拆出，纯展示。 */
export default function ChapterSection({
  chapters, summary, noteId, noteTitle, marksByChunk, showMarks,
  headerLabel, headerIcon, onSeek, done, onToggleDone, readOnly = false,
}: Props) {
  const { lang } = useLang();
  return (
    <section className="flex flex-col gap-5">
      <h2 className="text-lg font-semibold text-[var(--fg)]">
        {headerIcon} {headerLabel}
      </h2>
      {chapters.map((ch, ci) => {
        const hasChildren = !!(ch.children && ch.children.length > 0);
        return (
          <motion.div
            key={ci}
            id={`chapter-${ci + 1}`}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: Math.min(ci * 0.06, 0.4), type: "spring", stiffness: 180, damping: 22 }}
            className="apple-card p-5"
          >
            <div className="flex items-start justify-between gap-3 mb-2">
              <h3 className="text-base font-semibold leading-tight">
                <span className="text-[var(--fg-tertiary)] mr-2 tabular-nums">{ci + 1}</span>
                {pickByLang(ch, "title", lang)}
              </h3>
              <div className="flex shrink-0 items-center gap-2">
                {!readOnly && onToggleDone && (
                  <button
                    type="button"
                    onClick={() => onToggleDone(ci)}
                    aria-pressed={done?.includes(ci) ?? false}
                    title={done?.includes(ci)
                      ? (lang === "en" ? "Mark as not done" : "取消已学完")
                      : (lang === "en" ? "Mark as done" : "标记已学完")}
                    className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] transition-colors
                                ${done?.includes(ci)
                                  ? "bg-[rgba(29,158,117,0.12)] text-[#1d9e75]"
                                  : "text-[var(--fg-tertiary)] hover:bg-[var(--bg-muted)] hover:text-[var(--fg-secondary)]"}`}
                  >
                    {done?.includes(ci) ? <CheckCircle2 size={12} /> : <Circle size={12} />}
                    {lang === "en" ? "Done" : "已学完"}
                  </button>
                )}
                {!readOnly && (
                  <BookmarkMenu
                    size={15}
                    bm={{
                      key: bookmarkKey(noteId, "chapter", ci),
                      noteId, noteTitle, kind: "chapter", idx: ci,
                      title: ch.title_zh || ch.title,
                      title_en: ch.title_en,
                      time: ch.start,
                    }}
                    className="text-[var(--fg-tertiary)] hover:text-[var(--accent)]"
                  />
                )}
                <button
                  onClick={() => onSeek(ch.start)}
                  className="text-xs tabular-nums text-[var(--accent)] hover:underline"
                >
                  {formatTime(ch.start)}
                </button>
              </div>
            </div>
            {(() => { const ab = pickByLang(ch, "abstract", lang); return ab ? (
              <p className="text-sm text-[var(--fg-secondary)] leading-relaxed mb-2">
                {ab}
              </p>
            ) : null; })()}
            {hasChildren ? (
              <div className="mt-3 flex flex-col gap-2 border-l-2 border-[var(--border)] pl-3">
                {ch.children!.map((sub, si) => (
                  <div key={si} className="rounded-xl bg-[var(--bg-muted)] p-3">
                    <div className="flex items-start justify-between gap-2 mb-1">
                      <h4 className="text-sm font-medium leading-tight text-[var(--fg)]">
                        <span className="text-[var(--fg-tertiary)] mr-1.5 tabular-nums">
                          {ci + 1}.{si + 1}
                        </span>
                        {pickByLang(sub, "title", lang)}
                      </h4>
                      <button
                        onClick={() => onSeek(sub.start)}
                        className="shrink-0 text-[10px] tabular-nums text-[var(--accent)] hover:underline"
                      >
                        {formatTime(sub.start)}
                      </button>
                    </div>
                    {(() => { const sab = pickByLang(sub, "abstract", lang); return sab ? (
                      <p className="text-xs text-[var(--fg-secondary)] leading-relaxed mb-1.5">
                        {sab}
                      </p>
                    ) : null; })()}
                    <div className="flex flex-wrap gap-1.5">
                      {sub.indices.map(idx => {
                        const c = summary[idx];
                        if (!c) return null;
                        const marks = showMarks ? marksByChunk[idx] : [];
                        return (
                          <button
                            key={idx}
                            onClick={() => onSeek(c.start)}
                            className="tag-chip hover:bg-[var(--accent)] hover:text-[var(--on-accent)] transition-colors"
                          >
                            {marks.includes("emphasis") && "⭐"}
                            {marks.includes("hard") && "🎯"}
                            {(c.headline || `段 ${idx + 1}`).slice(0, 20)}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {ch.indices.map(idx => {
                  const c = summary[idx];
                  if (!c) return null;
                  const marks = showMarks ? marksByChunk[idx] : [];
                  return (
                    <button
                      key={idx}
                      onClick={() => onSeek(c.start)}
                      className="tag-chip hover:bg-[var(--accent)] hover:text-[var(--on-accent)] transition-colors"
                    >
                      {marks.includes("emphasis") && "⭐"}
                      {marks.includes("hard") && "🎯"}
                      {(c.headline || `段 ${idx + 1}`).slice(0, 20)}
                    </button>
                  );
                })}
              </div>
            )}
            {ch.quiz?.questions?.length ? (
              <details className="group mt-3">
                <summary className="flex cursor-pointer list-none items-center gap-2
                                    text-sm font-semibold text-[var(--fg)]">
                  <ChevronDown
                    size={14}
                    className="transition-transform group-open:rotate-0 -rotate-90"
                  />
                  {lang === "en" ? "🎓 Chapter Quiz" : "🎓 本章自测"}
                  <span className="text-xs font-normal text-[var(--fg-tertiary)]">
                    {ch.quiz.questions.length} {lang === "en" ? "questions" : "题"}
                  </span>
                </summary>
                <ChapterQuiz quiz={ch.quiz} />
              </details>
            ) : null}
          </motion.div>
        );
      })}
    </section>
  );
}
