"use client";
import { motion } from "framer-motion";
import type { Chapter } from "@/lib/types";
import { formatTime } from "@/lib/notes";
import { useLang, pickByLang } from "./LangContext";

interface Props {
  chapters: Chapter[];
  currentIdx: number;
  currentTime: number;
  onSeek: (sec: number) => void;
}

const CHAPTER_COLORS = ["#0a84ff", "#bf5af2", "#30d158", "#ff9f0a", "#ff375f", "#5e5ce6"];

/**
 * 视频下方章节快速导航。横向滚动，所有章节列出来，当前章节带 accent
 * border + 底部进度条。点击 seek 视频。
 */
export default function ChapterNav({ chapters, currentIdx, currentTime, onSeek }: Props) {
  const { lang } = useLang();
  return (
    <div className="flex gap-2 overflow-x-auto pb-2 -mb-2 -mx-1 px-1">
      {chapters.map((ch, i) => {
        const active = i === currentIdx;
        const color = CHAPTER_COLORS[i % CHAPTER_COLORS.length];
        const progress = active
          ? Math.min(1, Math.max(0, (currentTime - ch.start) / Math.max(1, ch.end - ch.start)))
          : 0;
        return (
          <motion.button
            key={i}
            onClick={() => onSeek(ch.start)}
            whileTap={{ scale: 0.97 }}
            whileHover={{ y: -1 }}
            className={`relative shrink-0 flex items-center gap-2 pl-2 pr-3 py-2 rounded-2xl text-xs
                        border transition-colors overflow-hidden
                        ${active
                          ? "border-[var(--accent)] bg-[var(--bg-elevated)] text-[var(--fg)] shadow-[var(--shadow-sm)]"
                          : "border-[var(--border)] bg-[var(--bg-elevated)] text-[var(--fg-secondary)] hover:text-[var(--fg)]"}`}
          >
            {active && (
              <div
                className="absolute bottom-0 left-0 h-0.5 bg-[var(--accent)] transition-[width] duration-150"
                style={{ width: `${progress * 100}%` }}
              />
            )}
            <span
              className="w-5 h-5 rounded-full flex items-center justify-center text-[10px]
                         font-semibold text-white tabular-nums shrink-0"
              style={{ background: color }}
            >
              {i + 1}
            </span>
            <span className="font-medium truncate max-w-[20ch]">{pickByLang(ch, "title", lang)}</span>
            <span className="tabular-nums opacity-60 text-[10px] shrink-0">
              {formatTime(ch.start)}
            </span>
          </motion.button>
        );
      })}
    </div>
  );
}
