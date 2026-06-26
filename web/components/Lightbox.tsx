"use client";
import { useEffect } from "react";
import Image from "next/image";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronLeft, ChevronRight, X, Play } from "lucide-react";
import { formatTime } from "@/lib/notes";

export interface LightboxItem {
  src: string;
  time: number;
  headline: string;
}

interface Props {
  items: LightboxItem[];
  index: number | null;
  onClose: () => void;
  onIndexChange: (i: number) => void;
  onSeek: (sec: number) => void;
}

/**
 * 苹果 Photos 风格关键帧大图查看。
 * - 黑底全屏 + 大图 + 左右箭头 + 键盘 ←/→/Esc
 * - "跳转到 mm:ss" 按钮：seek 视频后关闭
 * - 缩略图带：当前帧高亮
 */
export default function Lightbox({
  items, index, onClose, onIndexChange, onSeek,
}: Props) {
  useEffect(() => {
    if (index === null) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      } else if (e.key === "ArrowLeft" && index > 0) {
        e.preventDefault();
        onIndexChange(index - 1);
      } else if (e.key === "ArrowRight" && index < items.length - 1) {
        e.preventDefault();
        onIndexChange(index + 1);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [index, items.length, onClose, onIndexChange]);

  const cur = index !== null ? items[index] : null;
  const canPrev = index !== null && index > 0;
  const canNext = index !== null && index < items.length - 1;

  return (
    <AnimatePresence>
      {cur && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          data-overlay
          className="fixed inset-0 z-50 flex flex-col"
          style={{ background: "rgba(0,0,0,0.92)", backdropFilter: "blur(12px)" }}
          onClick={onClose}
        >
          {/* 顶栏 */}
          <div className="flex items-center gap-3 px-5 py-4 text-white shrink-0"
               onClick={e => e.stopPropagation()}>
            <span className="text-xs tabular-nums opacity-70">
              {(index ?? 0) + 1} / {items.length}
            </span>
            <span className="text-sm font-medium truncate">{cur.headline}</span>
            <button
              onClick={() => { onSeek(cur.time); onClose(); }}
              className="ml-auto inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full
                         bg-white/15 hover:bg-white/25 text-xs backdrop-blur transition-colors"
            >
              <Play size={12} />
              跳转到 {formatTime(cur.time)}
            </button>
            <button
              onClick={onClose}
              className="w-9 h-9 rounded-full bg-white/10 hover:bg-white/20
                         inline-flex items-center justify-center"
              title="关闭 (Esc)"
            >
              <X size={16} />
            </button>
          </div>

          {/* 大图区 + 左右箭头 */}
          <div className="flex-1 relative flex items-center justify-center px-12 py-4 min-h-0">
            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                key={cur.src}
                initial={{ opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.98 }}
                transition={{ duration: 0.18 }}
                className="relative h-full w-full max-w-6xl overflow-hidden rounded-xl
                           shadow-[0_30px_80px_rgba(0,0,0,0.6)]"
                onClick={e => e.stopPropagation()}
              >
                <Image
                  src={cur.src}
                  alt={cur.headline}
                  fill
                  sizes="100vw"
                  className="object-contain"
                />
              </motion.div>
            </AnimatePresence>

            {canPrev && (
              <button
                onClick={e => { e.stopPropagation(); onIndexChange(index! - 1); }}
                className="absolute left-3 top-1/2 -translate-y-1/2 w-12 h-12 rounded-full
                           bg-white/10 hover:bg-white/20 text-white
                           inline-flex items-center justify-center backdrop-blur-md"
                title="上一张 (←)"
              >
                <ChevronLeft size={22} />
              </button>
            )}
            {canNext && (
              <button
                onClick={e => { e.stopPropagation(); onIndexChange(index! + 1); }}
                className="absolute right-3 top-1/2 -translate-y-1/2 w-12 h-12 rounded-full
                           bg-white/10 hover:bg-white/20 text-white
                           inline-flex items-center justify-center backdrop-blur-md"
                title="下一张 (→)"
              >
                <ChevronRight size={22} />
              </button>
            )}
          </div>

          {/* 缩略图带 */}
          <div
            className="shrink-0 overflow-x-auto px-5 py-3 flex gap-2 items-center justify-start"
            onClick={e => e.stopPropagation()}
          >
            {items.map((it, i) => (
              <button
                key={i}
                onClick={() => onIndexChange(i)}
                className={`shrink-0 w-20 h-12 rounded-lg overflow-hidden transition-all
                            ${i === index
                              ? "ring-2 ring-white scale-[1.06]"
                              : "opacity-55 hover:opacity-90"}`}
              >
                <span className="relative block h-full w-full">
                  <Image src={it.src} alt="" fill sizes="80px" className="object-cover" />
                </span>
              </button>
            ))}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
