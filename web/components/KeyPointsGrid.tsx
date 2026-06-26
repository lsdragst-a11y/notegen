"use client";
import Image from "next/image";
import { motion } from "framer-motion";
import { Sparkles, Target, Clock, Expand, Play } from "lucide-react";
import type { Chunk, Mark } from "@/lib/types";
import { formatTime } from "@/lib/notes";
import { useLang, pickByLang } from "./LangContext";
import BookmarkMenu from "./BookmarkMenu";
import { bookmarkKey } from "@/lib/bookmarks";

interface Props {
  summary: Chunk[];
  keyframeBase: string;
  noteId: string;
  noteTitle: string;
  currentChunkIdx: number;
  marksByChunk: Mark[][];
  showMarks: boolean;
  onSeek: (sec: number) => void;
  onOpenDetail: (chunkIdx: number) => void;
  onOpenLightbox: (chunkIdx: number) => void;
  readOnly?: boolean;
}

/** 知识点速览卡片 grid（teaching/popsci）。从 NotesContent 拆出，纯展示。 */
export default function KeyPointsGrid({
  summary, keyframeBase, noteId, noteTitle, currentChunkIdx,
  marksByChunk, showMarks, onSeek, onOpenDetail, onOpenLightbox, readOnly = false,
}: Props) {
  const { lang } = useLang();
  return (
    <section>
      <h2 className="text-lg font-semibold mb-3 text-[var(--fg)]">
        {lang === "en" ? "💡 Key Points" : "💡 知识点速览"}
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
        {summary.map((c, i) => {
          const marks = showMarks ? marksByChunk[i] : [];
          const isActive = i === currentChunkIdx;
          const kfRel = c.keyframe?.rel;
          const headline = pickByLang(c, "headline", lang) || c.text.slice(0, 30);
          const caption = pickByLang(c, "summary", lang) || pickByLang(c, "text", lang).slice(0, 80);
          const handleCardActivate = () => onOpenDetail(i);
          return (
            <motion.div
              key={i}
              onClick={handleCardActivate}
              onKeyDown={e => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  handleCardActivate();
                }
              }}
              role="button"
              tabIndex={0}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: Math.min(i * 0.04, 0.4), type: "spring", stiffness: 200, damping: 24 }}
              whileHover={{ y: -3 }}
              className={`apple-card overflow-hidden text-left flex flex-col cursor-pointer
                          ${isActive ? "ring-2 ring-[var(--accent)]" : ""}`}
              style={marks.includes("emphasis") ? {
                boxShadow: "0 0 0 1px rgba(255, 186, 46, 0.45), var(--shadow-md)"
              } : undefined}
            >
              {/* 幻灯片大图——卡片主体 */}
              <div className="relative aspect-video bg-[var(--bg-muted)] overflow-hidden group/kf">
                {kfRel ? (
                  <Image
                    src={`${keyframeBase}${kfRel}`}
                    alt=""
                    fill
                    sizes="(max-width: 640px) 100vw, (max-width: 1280px) 50vw, 33vw"
                    className="object-cover transition-transform duration-300 group-hover/kf:scale-[1.04] dark:brightness-90"
                  />
                ) : (
                  <div className="absolute inset-0 flex items-center justify-center
                                  bg-gradient-to-br from-[var(--bg-muted)] to-[var(--bg)]
                                  text-[var(--fg-tertiary)]">
                    <Clock size={20} />
                  </div>
                )}
                {/* hover 操作浮层：跳转 + 查看大图 */}
                <div className="absolute inset-0 flex items-center justify-center gap-2.5
                                bg-black/0 opacity-0 transition-all
                                group-hover/kf:bg-black/35 group-hover/kf:opacity-100">
                  <button
                    type="button"
                    onClick={e => { e.stopPropagation(); onSeek(c.start); }}
                    title={lang === "en" ? "Jump to this point" : "跳转到此处"}
                    aria-label={lang === "en" ? "Jump to this point" : "跳转到此处"}
                    className="flex h-9 w-9 items-center justify-center rounded-full
                               bg-white/90 text-neutral-900 shadow-md transition-transform
                               hover:scale-110 hover:bg-white"
                  >
                    <Play size={15} fill="currentColor" className="translate-x-[1px]" />
                  </button>
                  {kfRel && (
                    <button
                      type="button"
                      onClick={e => { e.stopPropagation(); onOpenLightbox(i); }}
                      title={lang === "en" ? "View slide" : "查看大图"}
                      aria-label={lang === "en" ? "View slide" : "查看大图"}
                      className="flex h-9 w-9 items-center justify-center rounded-full
                                 bg-white/90 text-neutral-900 shadow-md transition-transform
                                 hover:scale-110 hover:bg-white"
                    >
                      <Expand size={15} />
                    </button>
                  )}
                </div>
                {/* 时间角标（左下） */}
                <span className="pointer-events-none absolute bottom-2 left-2 rounded-md
                                 bg-black/55 px-1.5 py-0.5 text-[11px] tabular-nums text-white
                                 backdrop-blur-sm">
                  {formatTime(c.start)}
                </span>
                {/* ⭐🎯 角标（右上） */}
                {(marks.includes("emphasis") || marks.includes("hard")) && (
                  <div className="pointer-events-none absolute right-2 top-2 flex gap-1">
                    {marks.includes("emphasis") && (
                      <span className="flex h-6 w-6 items-center justify-center rounded-full
                                       bg-white/90 shadow-sm"><Sparkles size={13} color="#b8851a" /></span>
                    )}
                    {marks.includes("hard") && (
                      <span className="flex h-6 w-6 items-center justify-center rounded-full
                                       bg-white/90 shadow-sm"><Target size={13} color="#b86a05" /></span>
                    )}
                  </div>
                )}
                {/* 收藏（左上，常显） */}
                {!readOnly && (
                  <BookmarkMenu
                  size={14}
                  bm={{
                    key: bookmarkKey(noteId, "chunk", i),
                    noteId, noteTitle, kind: "chunk", idx: i,
                    title: c.headline_zh || c.headline || c.text.slice(0, 30),
                    title_en: c.headline_en,
                    time: c.start,
                    keyframeRel: kfRel,
                  }}
                    className="absolute left-2 top-2 flex h-7 w-7 items-center justify-center
                               rounded-full bg-white/90 text-[var(--fg-secondary)] shadow-sm
                               hover:text-[var(--accent)]"
                  />
                )}
              </div>
              {/* 标题 + 一句话说明 */}
              <div className="flex flex-1 flex-col p-3.5">
                <div className="text-sm font-semibold leading-snug line-clamp-2 text-[var(--fg)]">
                  {headline}
                </div>
                {caption && (
                  <div className="mt-1.5 text-xs leading-relaxed text-[var(--fg-secondary)] line-clamp-2">
                    {caption}
                  </div>
                )}
              </div>
            </motion.div>
          );
        })}
      </div>
    </section>
  );
}
