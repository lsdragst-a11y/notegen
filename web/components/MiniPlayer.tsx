"use client";
import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Maximize2 } from "lucide-react";
import { formatTime } from "@/lib/notes";

interface Props {
  visible: boolean;
  src: string;
  currentTime: number;
  isPlaying: boolean;
  chapterLabel?: string;
  onClose: () => void;
  onExpand: () => void;
}

/**
 * 主视频滚出视口时弹出的右下角浮窗。镜像主视频画面 + 时间/播放状态同步；
 * mini 自身 muted（避免双音轨），音频仍来自主视频。close 临时隐藏直到下次滚回；
 * expand 滚回主视频。
 */
export default function MiniPlayer({
  visible, src, currentTime, isPlaying, chapterLabel, onClose, onExpand,
}: Props) {
  const ref = useRef<HTMLVideoElement>(null);

  // 时间漂移容差 0.5s 才矫正，避免每帧 setter 抖动
  useEffect(() => {
    const v = ref.current;
    if (!v) return;
    if (Math.abs(v.currentTime - currentTime) > 0.5) {
      try { v.currentTime = currentTime; } catch {}
    }
  }, [currentTime]);

  // 播放状态同步主视频
  useEffect(() => {
    const v = ref.current;
    if (!v) return;
    if (isPlaying) {
      v.play().catch(() => {});  // autoplay 被拒就静默
    } else {
      v.pause();
    }
  }, [isPlaying]);

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, y: 40, scale: 0.9 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 40, scale: 0.9 }}
          transition={{ type: "spring", stiffness: 320, damping: 28 }}
          className="fixed bottom-5 right-5 z-40 w-[320px] rounded-2xl overflow-hidden
                     glass shadow-[var(--shadow-lg)] group"
          style={{ aspectRatio: "16 / 9" }}
        >
          <video
            ref={ref}
            src={src}
            muted
            playsInline
            preload="metadata"
            className="w-full h-full object-cover"
          />
          {/* 顶部渐变 + 控制 */}
          <div className="absolute top-0 left-0 right-0 p-2 flex items-center gap-1
                          bg-gradient-to-b from-black/55 to-transparent
                          opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              onClick={onExpand}
              className="ml-auto w-7 h-7 rounded-full bg-black/40 hover:bg-black/60
                         text-white inline-flex items-center justify-center"
              title="回到主视频"
            >
              <Maximize2 size={13} />
            </button>
            <button
              onClick={onClose}
              className="w-7 h-7 rounded-full bg-black/40 hover:bg-black/60
                         text-white inline-flex items-center justify-center"
              title="关闭"
            >
              <X size={14} />
            </button>
          </div>
          {/* 底部当前章节 + 时间 */}
          <div className="absolute bottom-0 left-0 right-0 px-3 py-2
                          bg-gradient-to-t from-black/65 to-transparent
                          text-white text-xs flex items-center gap-2">
            <span className="tabular-nums shrink-0 opacity-90">{formatTime(currentTime)}</span>
            {chapterLabel && (
              <>
                <span className="opacity-50">·</span>
                <span className="truncate opacity-90">{chapterLabel}</span>
              </>
            )}
            {!isPlaying && (
              <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded-full
                               bg-white/20 shrink-0">已暂停</span>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
