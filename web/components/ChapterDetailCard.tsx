"use client";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronLeft, ChevronRight, Radio } from "lucide-react";
import type { Chapter, Chunk, DisplayLang } from "@/lib/types";
import { useLang, pickByLang } from "./LangContext";
import { formatTime, filterStopwords } from "@/lib/notes";

interface Props {
  chapters: Chapter[];
  currentIdx: number;
  currentTime: number;
  summary: Chunk[];
  onSeek: (sec: number, sourceElement?: HTMLElement | null) => void;
}

const CHAPTER_COLORS = ["#0a84ff", "#bf5af2", "#30d158", "#ff9f0a", "#ff375f", "#5e5ce6"];

function chapterKeywords(
  chapter: Chapter,
  summary: Chunk[],
  lang: DisplayLang,
  topK = 6,
): string[] {
  const df: Record<string, number> = {};
  const display: Record<string, string> = {};
  for (const idx of chapter.indices || []) {
    const c = summary[idx];
    if (!c) continue;
    const rec = c as unknown as Record<string, unknown>;
    const langKws = rec[`keywords_${lang}`];
    const raw = (Array.isArray(langKws) && langKws.length ? langKws : c.keywords) as
      | string[]
      | undefined;
    if (!raw) continue;
    const seen = new Set<string>();
    for (const kw of filterStopwords(raw)) {
      const key = kw.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      df[key] = (df[key] || 0) + 1;
      if (!(key in display)) display[key] = kw;
    }
  }
  return Object.keys(df)
    .sort((a, b) => df[b] - df[a])
    .slice(0, topK)
    .map(k => display[k]);
}

/**
 * 视频下方 sticky 列的章节详情卡。lg+ 显示，填补 sticky 留白；
 * 跟随 currentTime/currentIdx 实时更新章节标题、摘要、进度、术语 chips、prev/next。
 * 屏幕缩小到 <lg 时整卡隐藏（此时布局已经堆叠，无 sticky 留白可填）。
 */
export default function ChapterDetailCard({
  chapters,
  currentIdx,
  currentTime,
  summary,
  onSeek,
}: Props) {
  const { lang } = useLang();
  if (currentIdx < 0 || !chapters[currentIdx]) return null;

  const ch = chapters[currentIdx];
  const color = CHAPTER_COLORS[currentIdx % CHAPTER_COLORS.length];
  const dur = Math.max(1, ch.end - ch.start);
  const elapsed = Math.min(dur, Math.max(0, currentTime - ch.start));
  const progress = elapsed / dur;
  const title = pickByLang(ch, "title", lang);
  const abstract = pickByLang(ch, "abstract", lang);
  const kws = chapterKeywords(ch, summary, lang, 6);

  const hasPrev = currentIdx > 0;
  const hasNext = currentIdx < chapters.length - 1;
  const prevTitle = hasPrev ? pickByLang(chapters[currentIdx - 1], "title", lang) : "";
  const nextTitle = hasNext ? pickByLang(chapters[currentIdx + 1], "title", lang) : "";

  return (
    <div
      className="hidden rounded-[var(--wf-radius-md)] border border-[var(--wf-border)]
                 bg-[var(--wf-surface)] p-5 shadow-[var(--wf-shadow-sm)] lg:block"
    >
      <AnimatePresence mode="wait">
        <motion.div
          key={currentIdx}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
        >
          {/* Header: 章节号 + 当前播放 */}
          <div className="flex items-center gap-3">
            <span
              className="w-9 h-9 rounded-full inline-flex items-center justify-center
                         text-white text-sm font-semibold tabular-nums shrink-0"
              style={{ background: color, boxShadow: `0 0 0 4px ${color}1a` }}
            >
              {currentIdx + 1}
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-[10px] text-[var(--wf-text-tertiary)] uppercase tracking-[0.08em]
                              inline-flex items-center gap-1">
                <Radio size={9} className="animate-pulse" style={{ color }} />
                {lang === "en" ? "Now Playing" : "正在播放"}
              </div>
              <div className="text-[15px] font-semibold leading-snug text-[var(--wf-text)] line-clamp-2">
                {title}
              </div>
            </div>
          </div>

          {/* 摘要 */}
          {abstract && (
            <p className="mt-3.5 text-[12.5px] leading-relaxed text-[var(--wf-text-secondary)] line-clamp-4">
              {abstract}
            </p>
          )}

          {/* 章节内进度 */}
          <div className="mt-4">
            <div className="flex items-center justify-between text-[10.5px]
                            text-[var(--wf-text-tertiary)] tabular-nums mb-1.5">
              <span>{formatTime(elapsed)}</span>
              <span>{Math.round(progress * 100)}%</span>
              <span>{formatTime(dur)}</span>
            </div>
            <div className="h-1 rounded-full bg-[var(--wf-surface-muted)] overflow-hidden">
              <motion.div
                className="h-full"
                style={{ background: color }}
                initial={false}
                animate={{ width: `${progress * 100}%` }}
                transition={{ duration: 0.15, ease: "linear" }}
              />
            </div>
          </div>

          {/* 本章高频术语 */}
          {kws.length > 0 && (
            <div className="mt-3.5 flex flex-wrap gap-1.5">
              {kws.map((k, i) => (
                <span
                  key={`${k}-${i}`}
                  className="rounded-[var(--wf-radius-full)] border border-[var(--wf-border)] bg-[var(--wf-surface-muted)] px-2 py-0.5 text-[11px] font-medium text-[var(--wf-text-secondary)]"
                >
                  {k}
                </span>
              ))}
            </div>
          )}

          {/* prev / next */}
          <div className="mt-4 grid grid-cols-2 gap-2 border-t border-[var(--wf-border)] pt-3.5">
            <motion.button
              onClick={(event) => hasPrev && onSeek(chapters[currentIdx - 1].start, event.currentTarget)}
              disabled={!hasPrev}
              whileTap={hasPrev ? { scale: 0.97 } : undefined}
              className="group inline-flex items-center gap-1.5 px-2.5 py-2 rounded-xl
                         text-[11.5px] text-[var(--wf-text-secondary)] hover:text-[var(--wf-text)]
                         bg-[var(--wf-surface-muted)] hover:bg-[var(--wf-surface)]
                         border border-[var(--wf-border)]
                         transition-colors disabled:opacity-35 disabled:cursor-not-allowed
                         disabled:hover:bg-[var(--wf-surface-muted)] min-w-0"
            >
              <ChevronLeft
                size={13}
                className="shrink-0 transition-transform group-enabled:group-hover:-translate-x-0.5"
              />
              <span className="flex-1 min-w-0 text-left">
                <span className="block text-[9.5px] text-[var(--wf-text-tertiary)] uppercase tracking-wider leading-none">
                  {lang === "en" ? "Prev" : "上一章"}
                </span>
                <span className="block truncate font-medium mt-0.5">
                  {hasPrev ? prevTitle : lang === "en" ? "—" : "—"}
                </span>
              </span>
            </motion.button>

            <motion.button
              onClick={(event) => hasNext && onSeek(chapters[currentIdx + 1].start, event.currentTarget)}
              disabled={!hasNext}
              whileTap={hasNext ? { scale: 0.97 } : undefined}
              className="group inline-flex items-center gap-1.5 px-2.5 py-2 rounded-xl
                         text-[11.5px] text-[var(--wf-text-secondary)] hover:text-[var(--wf-text)]
                         bg-[var(--wf-surface-muted)] hover:bg-[var(--wf-surface)]
                         border border-[var(--wf-border)]
                         transition-colors disabled:opacity-35 disabled:cursor-not-allowed
                         disabled:hover:bg-[var(--wf-surface-muted)] min-w-0"
            >
              <span className="flex-1 min-w-0 text-right">
                <span className="block text-[9.5px] text-[var(--wf-text-tertiary)] uppercase tracking-wider leading-none">
                  {lang === "en" ? "Next" : "下一章"}
                </span>
                <span className="block truncate font-medium mt-0.5">
                  {hasNext ? nextTitle : lang === "en" ? "—" : "—"}
                </span>
              </span>
              <ChevronRight
                size={13}
                className="shrink-0 transition-transform group-enabled:group-hover:translate-x-0.5"
              />
            </motion.button>
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
