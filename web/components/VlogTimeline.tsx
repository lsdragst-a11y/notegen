"use client";
import { motion } from "framer-motion";
import { Expand } from "lucide-react";
import type { Chunk } from "@/lib/types";
import { formatTime } from "@/lib/notes";
import { useLang, pickByLang } from "./LangContext";

interface Props {
  keyframeBase: string;
  summary: Chunk[];
  currentTime: number;
  onSeek: (sec: number) => void;
  onOpenLightbox?: (chunkIdx: number) => void;
  /** UI 文案 — vlog 用"片段"，talk 用"观点" */
  variant: "vlog" | "talk";
}

/** 给非教学类视频用的"时间轴亮点"卡片，竖向时间线 + 关键帧 + 时间戳 + headline。
 *  不显示 ⭐ 重难点 / 关键词标签 / "知识点"语义包装。 */
export default function VlogTimeline({
  keyframeBase, summary, currentTime, onSeek, onOpenLightbox, variant,
}: Props) {
  const { lang } = useLang();
  const currentIdx = summary.findIndex(
    c => currentTime >= c.start && currentTime < c.end
  );

  const headerLabel = variant === "vlog"
    ? (lang === "en" ? "📍 Timeline" : "📍 片段时间线")
    : (lang === "en" ? "💬 Highlights" : "💬 观点片段");
  const emptyHeadlineLabel = variant === "vlog"
    ? (lang === "en" ? "Clip" : "片段")
    : (lang === "en" ? "Point" : "观点");

  return (
    <section>
      <h2 className="text-lg font-semibold mb-3 text-[var(--fg)]">{headerLabel}</h2>
      <div className="relative pl-6">
        {/* 左侧竖线 */}
        <div className="absolute left-2 top-2 bottom-2 w-px bg-[var(--border)]" />
        <div className="flex flex-col gap-3">
          {summary.map((c, i) => {
            const isActive = i === currentIdx;
            const kfRel = c.keyframe?.rel;
            const headline = pickByLang(c, "headline", lang) || `${emptyHeadlineLabel} ${i + 1}`;
            const summary_t = pickByLang(c, "summary", lang);
            const text_t = pickByLang(c, "text", lang);
            const preview = summary_t || text_t.slice(0, 100);
            return (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.04, type: "spring", stiffness: 200, damping: 24 }}
                className="relative"
              >
                {/* 时间线节点圆点 */}
                <div className={`absolute -left-[18px] top-3 w-2 h-2 rounded-full
                                 ${isActive ? "bg-[var(--accent)] ring-4 ring-[var(--accent)]/25"
                                            : "bg-[var(--fg-tertiary)]/40"}`} />
                <motion.div
                  role="button"
                  tabIndex={0}
                  onClick={() => onSeek(c.start)}
                  onKeyDown={e => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSeek(c.start);
                    }
                  }}
                  whileHover={{ y: -1 }}
                  className={`apple-card p-3 cursor-pointer flex gap-3
                              ${isActive ? "ring-2 ring-[var(--accent)]" : ""}`}
                >
                  {kfRel && (
                    <button
                      type="button"
                      onClick={e => {
                        e.stopPropagation();
                        onOpenLightbox?.(i);
                      }}
                      className="shrink-0 w-28 h-16 rounded-lg overflow-hidden
                                 bg-[var(--bg-muted)] relative group/kf"
                      title={lang === "en" ? "Open" : "查看大图"}
                    >
                      <img src={`${keyframeBase}${kfRel}`}
                           alt="" className="w-full h-full object-cover dark:brightness-90
                                              transition-transform group-hover/kf:scale-[1.06]" />
                      <span className="absolute inset-0 bg-black/35 opacity-0
                                       group-hover/kf:opacity-100 transition-opacity
                                       flex items-center justify-center text-white">
                        <Expand size={14} />
                      </span>
                    </button>
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="text-xs text-[var(--fg-tertiary)] tabular-nums mb-1">
                      {formatTime(c.start)}
                    </div>
                    <div className="text-sm font-medium leading-snug line-clamp-2">
                      {headline}
                    </div>
                    {preview && (
                      <div className="mt-1.5 text-xs text-[var(--fg-secondary)]
                                      leading-relaxed line-clamp-2">
                        {preview}
                      </div>
                    )}
                  </div>
                </motion.div>
              </motion.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
