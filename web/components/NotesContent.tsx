"use client";
import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Sparkles, Target, Clock, Expand, ChevronDown, Play } from "lucide-react";
import type { Chapter, Chunk, Category, Overview } from "@/lib/types";
import { chunkMarks, overviewKeywords, buildGlossary, formatTime } from "@/lib/notes";
import { useLang, pickByLang } from "./LangContext";
import GlossaryList from "./GlossaryList";
import ChapterQuiz from "./ChapterQuiz";
import Lightbox, { LightboxItem } from "./Lightbox";
import VlogTimeline from "./VlogTimeline";
import OverviewHero from "./OverviewHero";
import KeyPointModal from "./KeyPointModal";
import BookmarkMenu from "./BookmarkMenu";
import { bookmarkKey } from "@/lib/bookmarks";

interface Props {
  keyframeBase: string;
  noteId: string;
  title: string;
  summary: Chunk[];
  chapters: Chapter[];
  overview?: Overview | null;
  currentTime: number;
  onSeek: (sec: number) => void;
  /** 视频内容大类。teaching=保留全部；popsci=去🎯且术语表折叠；
   *  vlog/talk=时间轴卡片替代知识点速览且无术语表。 */
  category?: Category;
}

export default function NotesContent({
  keyframeBase, noteId, title, summary, chapters, overview, currentTime, onSeek, category = "teaching",
}: Props) {
  const { lang } = useLang();
  const keywords = overviewKeywords(summary, 8, lang);
  const glossary = buildGlossary(summary, 15, lang);
  const total = summary.length > 0
    ? summary[summary.length - 1].end - summary[0].start
    : 0;

  // category 派生 flag —— 单点决定 UI 差异，方便日后调
  const showKnowledgePoints = category === "teaching" || category === "popsci";
  const showMarks = category === "teaching";                   // ⭐ 🎯 标记
  const showGlossary = category === "teaching" || category === "popsci";
  const glossaryDefaultOpen = category === "teaching";
  const chapterHeaderLabel = (category === "vlog" || category === "talk")
    ? (lang === "en" ? "Segments" : "片段")
    : (lang === "en" ? "Chapters" : "章节");
  const chapterHeaderIcon = (category === "vlog" || category === "talk") ? "🎬" : "📑";

  // 当前 chunk idx（用于高亮）
  const currentChunkIdx = summary.findIndex(
    c => currentTime >= c.start && currentTime < c.end
  );

  // 关键帧 lightbox：扁平所有带 keyframe 的 chunk
  const lightboxItems: LightboxItem[] = useMemo(
    () => summary.flatMap(c => c.keyframe ? [{
      src: `${keyframeBase}${c.keyframe.rel}`,
      time: c.start,
      headline: c.headline || c.text.slice(0, 30),
    }] : []),
    [summary, keyframeBase]
  );
  const [lbIdx, setLbIdx] = useState<number | null>(null);
  const [detailIdx, setDetailIdx] = useState<number | null>(null);

  // chunk idx → lightbox idx 映射（用于打开时定位）
  const lbIdxByChunk = useMemo(() => {
    const m = new Map<number, number>();
    let li = 0;
    summary.forEach((c, i) => {
      if (c.keyframe) { m.set(i, li); li++; }
    });
    return m;
  }, [summary]);

  const openLightboxForChunk = (chunkIdx: number) => {
    const lbi = lbIdxByChunk.get(chunkIdx);
    if (lbi !== undefined) setLbIdx(lbi);
  };

  return (
    <div className="flex flex-col gap-6">
      {/* 顶部摘要卡 */}
      <motion.section
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ type: "spring", stiffness: 200, damping: 24 }}
        className="apple-card p-6"
      >
        <h1 className="text-2xl font-semibold leading-tight tracking-tight">{title}</h1>
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-[var(--fg-secondary)]">
          <span className="inline-flex items-center gap-1"><Clock size={14} />{formatTime(total)}</span>
          <span>·</span>
          <span>
            {chapters.length} {chapterHeaderLabel} / {summary.length} {lang === "en" ? "clips" : "段"}
          </span>
        </div>
        {keywords.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {keywords.map((k, i) => <span key={`${k}-${i}`} className="tag-chip">{k}</span>)}
          </div>
        )}
      </motion.section>

      {/* 全文总结 hero：散文概览 + 你将学到（有 overview 才渲染） */}
      {overview && <OverviewHero overview={overview} />}

      {/* 中间主区：教学/科普 → 知识点速览卡片；vlog/talk → 时间轴 */}
      {showKnowledgePoints ? (
        <section>
          <h2 className="text-lg font-semibold mb-3 text-[var(--fg)]">
            {lang === "en" ? "💡 Key Points" : "💡 知识点速览"}
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {summary.map((c, i) => {
              const marks = showMarks ? chunkMarks(c) : [];
              const isActive = i === currentChunkIdx;
              const kfRel = c.keyframe?.rel;
              const lbi = lbIdxByChunk.get(i);
              const headline = pickByLang(c, "headline", lang) || c.text.slice(0, 30);
              const caption = pickByLang(c, "summary", lang) || pickByLang(c, "text", lang).slice(0, 80);
              const handleCardActivate = () => setDetailIdx(i);
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
                  transition={{ delay: i * 0.04, type: "spring", stiffness: 200, damping: 24 }}
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
                      <img src={`${keyframeBase}${kfRel}`}
                           alt="" className="h-full w-full object-cover dark:brightness-90
                                              transition-transform duration-300 group-hover/kf:scale-[1.04]" />
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
                          onClick={e => { e.stopPropagation(); if (lbi !== undefined) setLbIdx(lbi); }}
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
                    <BookmarkMenu
                      size={14}
                      bm={{
                        key: bookmarkKey(noteId, "chunk", i),
                        noteId, noteTitle: title, kind: "chunk", idx: i,
                        title: c.headline_zh || c.headline || c.text.slice(0, 30),
                        title_en: c.headline_en,
                        time: c.start,
                        keyframeRel: kfRel,
                      }}
                      className="absolute left-2 top-2 flex h-7 w-7 items-center justify-center
                                 rounded-full bg-white/90 text-[var(--fg-secondary)] shadow-sm
                                 hover:text-[var(--accent)]"
                    />
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
      ) : (
        <VlogTimeline
          keyframeBase={keyframeBase}
          summary={summary}
          currentTime={currentTime}
          onSeek={onSeek}
          onOpenLightbox={openLightboxForChunk}
          variant={category === "talk" ? "talk" : "vlog"}
        />
      )}

      {/* 章节内容（所有 category 都展示，但措辞按 category 微调） */}
      <section className="flex flex-col gap-5">
        <h2 className="text-lg font-semibold text-[var(--fg)]">
          {chapterHeaderIcon} {chapterHeaderLabel}
        </h2>
        {chapters.map((ch, ci) => {
          const hasChildren = !!(ch.children && ch.children.length > 0);
          return (
            <motion.div
              key={ci}
              id={`chapter-${ci + 1}`}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: ci * 0.06, type: "spring", stiffness: 180, damping: 22 }}
              className="apple-card p-5"
            >
              <div className="flex items-start justify-between gap-3 mb-2">
                <h3 className="text-base font-semibold leading-tight">
                  <span className="text-[var(--fg-tertiary)] mr-2 tabular-nums">{ci + 1}</span>
                  {pickByLang(ch, "title", lang)}
                </h3>
                <div className="flex shrink-0 items-center gap-2">
                  <BookmarkMenu
                    size={15}
                    bm={{
                      key: bookmarkKey(noteId, "chapter", ci),
                      noteId, noteTitle: title, kind: "chapter", idx: ci,
                      title: ch.title_zh || ch.title,
                      title_en: ch.title_en,
                      time: ch.start,
                    }}
                    className="text-[var(--fg-tertiary)] hover:text-[var(--accent)]"
                  />
                  <button
                    onClick={() => onSeek(ch.start)}
                    className="text-xs tabular-nums text-[var(--accent)] hover:underline"
                  >
                    {formatTime(ch.start)}
                  </button>
                </div>
              </div>
              {(() => { const ab = pickByLang(ch, "abstract", lang); return ab ? (
                <p className="text-sm text-[var(--fg-secondary)] leading-relaxed mb-2">
                  {ab}
                </p>
              ) : null; })()}
              {hasChildren ? (
                <div className="mt-3 flex flex-col gap-2 border-l-2 border-[var(--border)] pl-3">
                  {ch.children!.map((sub, si) => (
                    <div key={si} className="rounded-xl bg-[var(--bg-muted)] p-3">
                      <div className="flex items-start justify-between gap-2 mb-1">
                        <h4 className="text-sm font-medium leading-tight text-[var(--fg)]">
                          <span className="text-[var(--fg-tertiary)] mr-1.5 tabular-nums">
                            {ci + 1}.{si + 1}
                          </span>
                          {pickByLang(sub, "title", lang)}
                        </h4>
                        <button
                          onClick={() => onSeek(sub.start)}
                          className="shrink-0 text-[10px] tabular-nums text-[var(--accent)] hover:underline"
                        >
                          {formatTime(sub.start)}
                        </button>
                      </div>
                      {(() => { const sab = pickByLang(sub, "abstract", lang); return sab ? (
                        <p className="text-xs text-[var(--fg-secondary)] leading-relaxed mb-1.5">
                          {sab}
                        </p>
                      ) : null; })()}
                      <div className="flex flex-wrap gap-1.5">
                        {sub.indices.map(idx => {
                          const c = summary[idx];
                          if (!c) return null;
                          const marks = showMarks ? chunkMarks(c) : [];
                          return (
                            <button
                              key={idx}
                              onClick={() => onSeek(c.start)}
                              className="tag-chip hover:bg-[var(--accent)] hover:text-white transition-colors"
                            >
                              {marks.includes("emphasis") && "⭐"}
                              {marks.includes("hard") && "🎯"}
                              {(c.headline || `段 ${idx + 1}`).slice(0, 20)}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {ch.indices.map(idx => {
                    const c = summary[idx];
                    if (!c) return null;
                    const marks = showMarks ? chunkMarks(c) : [];
                    return (
                      <button
                        key={idx}
                        onClick={() => onSeek(c.start)}
                        className="tag-chip hover:bg-[var(--accent)] hover:text-white transition-colors"
                      >
                        {marks.includes("emphasis") && "⭐"}
                        {marks.includes("hard") && "🎯"}
                        {(c.headline || `段 ${idx + 1}`).slice(0, 20)}
                      </button>
                    );
                  })}
                </div>
              )}
              {ch.quiz?.questions?.length ? (
                <details className="group mt-3">
                  <summary className="flex cursor-pointer list-none items-center gap-2
                                      text-sm font-semibold text-[var(--fg)]">
                    <ChevronDown
                      size={14}
                      className="transition-transform group-open:rotate-0 -rotate-90"
                    />
                    {lang === "en" ? "🎓 Chapter Quiz" : "🎓 本章自测"}
                    <span className="text-xs font-normal text-[var(--fg-tertiary)]">
                      {ch.quiz.questions.length} {lang === "en" ? "questions" : "题"}
                    </span>
                  </summary>
                  <ChapterQuiz quiz={ch.quiz} />
                </details>
              ) : null}
            </motion.div>
          );
        })}
      </section>

      {/* 术语表（vlog/talk 完全隐藏；popsci 折叠；teaching 展开） */}
      {showGlossary && glossary.length > 0 && (
        <section>
          <details open={glossaryDefaultOpen} className="group">
            <summary className="text-lg font-semibold mb-3 text-[var(--fg)]
                                cursor-pointer list-none flex items-center gap-2">
              <ChevronDown size={16} className="transition-transform group-open:rotate-0 -rotate-90" />
              {lang === "en" ? "📚 Glossary" : "📚 术语表"}
              <span className="text-xs font-normal text-[var(--fg-tertiary)]">
                {glossary.length} {lang === "en" ? "terms" : "项"}
              </span>
            </summary>
            <GlossaryList glossary={glossary} onSeek={onSeek} />
          </details>
        </section>
      )}

      <Lightbox
        items={lightboxItems}
        index={lbIdx}
        onClose={() => setLbIdx(null)}
        onIndexChange={setLbIdx}
        onSeek={onSeek}
      />

      <KeyPointModal
        chunk={detailIdx !== null ? summary[detailIdx] : null}
        chunkIdx={detailIdx ?? -1}
        noteId={noteId}
        keyframeBase={keyframeBase}
        noteTitle={title}
        marks={detailIdx !== null && showMarks ? chunkMarks(summary[detailIdx]) : []}
        onClose={() => setDetailIdx(null)}
        onSeek={onSeek}
      />
    </div>
  );
}
