"use client";
import { motion } from "framer-motion";
import { useEffect, useRef } from "react";
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
  const activeRef = useRef<HTMLButtonElement>(null);
  // active chip 自动滚入视口居中，避免最后一章 chip 时长被容器右边沿切掉
  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest", inline: "center", behavior: "smooth" });
  }, [currentIdx]);
  return (
    // pb-2 给 active chip shadow 留呼吸空间；不再用 -mb-2 抵消，否则下方
    // ChapterDetailCard 跟 chip 行视觉粘连（截图重叠问题）
    <nav aria-label={lang === "en" ? "Chapters" : "章节"}
         className="flex gap-2 overflow-x-auto pb-2 -mx-1 px-1">
      {chapters.map((ch, i) => {
        const active = i === currentIdx;
        const color = CHAPTER_COLORS[i % CHAPTER_COLORS.length];
        const progress = active
          ? Math.min(1, Math.max(0, (currentTime - ch.start) / Math.max(1, ch.end - ch.start)))
          : 0;
        return (
          <motion.button
            key={i}
            ref={active ? activeRef : undefined}
            onClick={() => onSeek(ch.start)}
            aria-current={active ? "location" : undefined}
            whileTap={{ scale: 0.97 }}
            whileHover={{ y: -1 }}
            className={`relative shrink-0 flex min-h-11 items-center gap-2 pl-2 pr-3 py-2 rounded-2xl text-xs
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
    </nav>
  );
}
