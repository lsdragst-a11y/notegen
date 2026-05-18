"use client";
import { motion, AnimatePresence } from "framer-motion";
import { formatTime } from "@/lib/notes";

interface Props {
  chapterTitle: string;
  chapterIdx: number;
  totalChapters: number;
  currentTime: number;
  chapterStart: number;
  chapterEnd: number;
}

/**
 * Dynamic Island 风格章节 chip — 浮在视频上方，章节切换时 spring 滑动。
 */
export default function ChapterChip({
  chapterTitle, chapterIdx, totalChapters, currentTime, chapterStart, chapterEnd,
}: Props) {
  const progress = chapterEnd > chapterStart
    ? Math.min(1, Math.max(0, (currentTime - chapterStart) / (chapterEnd - chapterStart)))
    : 0;
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={chapterIdx}
        initial={{ opacity: 0, y: -8, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 4, scale: 0.96 }}
        transition={{ type: "spring", stiffness: 400, damping: 30 }}
        className="glass rounded-full px-4 py-2 inline-flex items-center gap-3
                   text-sm text-[var(--fg)] shadow-[var(--shadow-md)]"
      >
        <span className="text-[var(--fg-tertiary)] tabular-nums">
          {chapterIdx + 1}/{totalChapters}
        </span>
        <span className="font-medium truncate max-w-[26ch]">{chapterTitle}</span>
        <span className="text-[var(--fg-tertiary)] tabular-nums">
          {formatTime(currentTime - chapterStart)} / {formatTime(chapterEnd - chapterStart)}
        </span>
        <div className="w-12 h-1 rounded-full bg-[var(--bg-muted)] overflow-hidden">
          <div className="h-full bg-[var(--accent)] transition-[width] duration-150"
               style={{ width: `${progress * 100}%` }} />
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
