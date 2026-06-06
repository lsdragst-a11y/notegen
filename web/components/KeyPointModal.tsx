"use client";
import { useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Play, Sparkles, Target, ChevronDown } from "lucide-react";
import type { Chunk, Mark } from "@/lib/types";
import { formatTime } from "@/lib/notes";
import { useLang, pickByLang } from "./LangContext";
import BookmarkMenu from "./BookmarkMenu";
import { bookmarkKey } from "@/lib/bookmarks";

interface Props {
  chunk: Chunk | null;
  chunkIdx: number;
  noteId: string;
  keyframeBase: string;
  noteTitle: string;
  marks: Mark[];
  onClose: () => void;
  onSeek: (sec: number) => void;
}

/**
 * 知识点「拉出来细看」弹窗：完整摘要（不截断）+ 转写原文（可折叠）+ 关键词 + 大图 + 跳转 + 收藏。
 * 黑底遮罩 + 居中卡片，Esc / 点击遮罩关闭。复用站点 apple-card 风格。
 */
export default function KeyPointModal({
  chunk, chunkIdx, noteId, keyframeBase, noteTitle, marks, onClose, onSeek,
}: Props) {
  const { lang } = useLang();

  useEffect(() => {
    if (!chunk) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); onClose(); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [chunk, onClose]);

  const headline = chunk ? (pickByLang(chunk, "headline", lang) || chunk.text.slice(0, 40)) : "";
  const summary = chunk ? pickByLang(chunk, "summary", lang) : "";
  const transcript = chunk ? pickByLang(chunk, "text", lang) : "";
  const kfRel = chunk?.keyframe?.rel;
  const langKws = chunk
    ? ((chunk as unknown as Record<string, unknown>)[`keywords_${lang}`] as string[] | undefined)
    : undefined;
  const keywords = (Array.isArray(langKws) && langKws.length ? langKws : chunk?.keywords) || [];

  return (
    <AnimatePresence>
      {chunk && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6"
          style={{ background: "rgba(0,0,0,0.6)", backdropFilter: "blur(8px)" }}
          onClick={onClose}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 10 }}
            transition={{ type: "spring", stiffness: 240, damping: 26 }}
            className="apple-card relative flex max-h-[88vh] w-full max-w-2xl flex-col overflow-hidden p-0"
            onClick={e => e.stopPropagation()}
          >
            {/* 关键帧大图 */}
            {kfRel && (
              <div className="relative aspect-video w-full shrink-0 overflow-hidden bg-[var(--bg-muted)]">
                <img src={`${keyframeBase}${kfRel}`} alt=""
                     className="h-full w-full object-cover dark:brightness-90" />
              </div>
            )}

            {/* 关闭按钮（右上，浮在图上或卡上） */}
            <button
              onClick={onClose}
              title={lang === "en" ? "Close (Esc)" : "关闭 (Esc)"}
              className="absolute right-3 top-3 flex h-8 w-8 items-center justify-center rounded-full
                         bg-black/45 text-white backdrop-blur-sm transition-colors hover:bg-black/65"
            >
              <X size={16} />
            </button>

            <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-5">
              {/* 时间 + 标记 + 跳转 + 收藏 */}
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm tabular-nums text-[var(--fg-tertiary)]">
                  {formatTime(chunk.start)} – {formatTime(chunk.end)}
                </span>
                {marks.includes("emphasis") && (
                  <span className="mark-emphasis"><Sparkles size={12} color="#b8851a" /></span>
                )}
                {marks.includes("hard") && (
                  <span className="mark-hard"><Target size={12} color="#b86a05" /></span>
                )}
                <div className="ml-auto flex items-center gap-2">
                  <BookmarkMenu
                    size={16}
                    bm={{
                      key: bookmarkKey(noteId, "chunk", chunkIdx),
                      noteId, noteTitle, kind: "chunk", idx: chunkIdx,
                      title: chunk.headline_zh || chunk.headline || chunk.text.slice(0, 30),
                      title_en: chunk.headline_en,
                      time: chunk.start,
                      keyframeRel: kfRel,
                    }}
                    className="flex h-8 w-8 items-center justify-center rounded-full
                               bg-[var(--bg-muted)] text-[var(--fg-secondary)] hover:text-[var(--accent)]"
                  />
                  <button
                    onClick={() => { onSeek(chunk.start); onClose(); }}
                    className="inline-flex items-center gap-1.5 rounded-full bg-[var(--accent)]
                               px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90"
                  >
                    <Play size={12} fill="currentColor" />
                    {lang === "en" ? "Jump to clip" : "跳转到此处"}
                  </button>
                </div>
              </div>

              {/* 标题 */}
              <h3 className="text-lg font-semibold leading-snug text-[var(--fg)]">{headline}</h3>

              {/* 完整摘要（不截断） */}
              {summary && (
                <p className="text-sm leading-relaxed text-[var(--fg-secondary)]">{summary}</p>
              )}

              {/* 关键词 */}
              {keywords.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {keywords.map((k, i) => <span key={`${k}-${i}`} className="tag-chip">{k}</span>)}
                </div>
              )}

              {/* 转写原文（可折叠） */}
              {transcript && (
                <details className="group mt-1">
                  <summary className="flex cursor-pointer list-none items-center gap-2 text-sm
                                      font-medium text-[var(--fg)]">
                    <ChevronDown size={14} className="-rotate-90 transition-transform group-open:rotate-0" />
                    {lang === "en" ? "Transcript" : "转写原文"}
                  </summary>
                  <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-[var(--fg-secondary)]">
                    {transcript}
                  </p>
                </details>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
