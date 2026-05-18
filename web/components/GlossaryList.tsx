"use client";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Book } from "lucide-react";
import type { GlossaryEntry } from "@/lib/notes";
import { formatTime } from "@/lib/notes";

interface Props {
  glossary: GlossaryEntry[];
  onSeek: (sec: number) => void;
}

export default function GlossaryList({ glossary, onSeek }: Props) {
  const [hovered, setHovered] = useState<string | null>(null);
  return (
    <div className="apple-card p-4">
      <div className="flex flex-wrap gap-2">
        {glossary.map(g => (
          <div
            key={g.term}
            className="relative"
            onMouseEnter={() => setHovered(g.term)}
            onMouseLeave={() => setHovered(null)}
          >
            <button
              onClick={() => onSeek(g.firstStart)}
              className="tag-chip hover:bg-[var(--accent)] hover:text-white transition-colors
                         inline-flex items-center gap-1"
            >
              <Book size={11} />
              {g.term}
              <span className="text-[10px] text-[var(--fg-tertiary)]">·{g.df}</span>
            </button>
            <AnimatePresence>
              {hovered === g.term && g.snippet && (
                <motion.div
                  initial={{ opacity: 0, y: 4, scale: 0.96 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 4, scale: 0.96 }}
                  transition={{ type: "spring", stiffness: 400, damping: 26 }}
                  className="absolute top-full left-0 mt-2 z-30 glass rounded-xl p-3
                             w-72 text-xs text-[var(--fg-secondary)] shadow-[var(--shadow-lg)]"
                >
                  <div className="text-[var(--fg)] font-medium mb-1">{g.term}</div>
                  <div className="leading-relaxed mb-2">{g.snippet}</div>
                  <button
                    onClick={() => onSeek(g.firstStart)}
                    className="text-[var(--accent)] hover:underline tabular-nums"
                  >
                    跳转到 {formatTime(g.firstStart)} →
                  </button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        ))}
      </div>
    </div>
  );
}
