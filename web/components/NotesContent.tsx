"use client";
import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Sparkles, Target, Clock, Expand, ChevronDown } from "lucide-react";
import type { Chapter, Chunk, Category, Overview } from "@/lib/types";
import { chunkMarks, overviewKeywords, buildGlossary, filterStopwords, formatTime } from "@/lib/notes";
import { useLang, pickByLang } from "./LangContext";
import GlossaryList from "./GlossaryList";
import ChapterQuiz from "./ChapterQuiz";
import Lightbox, { LightboxItem } from "./Lightbox";
import VlogTimeline from "./VlogTimeline";
import OverviewHero from "./OverviewHero";

interface Props {
  keyframeBase: string;
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
  keyframeBase, title, summary, chapters, overview, currentTime, onSeek, category = "teaching",
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

      {/* 全文总结 hero：散文概览 + 你将学到 + 章节比例条（有 overview 才渲染） */}
      {overview && (
        <OverviewHero
          overview={overview}
          chapters={chapters}
          currentTime={currentTime}
          onSeek={onSeek}
        />
      )}

      {/* 中间主区：教学/科普 → 知识点速览卡片；vlog/talk → 时间轴 */}
      {showKnowledgePoints ? (
        <section>
          <h2 className="text-lg font-semibold mb-3 text-[var(--fg)]">
            {lang === "en" ? "💡 Key Points" : "💡 知识点速览"}
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {summary.map((c, i) => {
              const marks = showMarks ? chunkMarks(c) : [];
              const isActive = i === currentChunkIdx;
              const kfRel = c.keyframe?.rel;
              const lbi = lbIdxByChunk.get(i);
              const handleCardActivate = () => onSeek(c.start);
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
                  whileHover={{ y: -2 }}
                  className={`apple-card p-4 text-left flex gap-3 cursor-pointer
                              ${isActive ? "ring-2 ring-[var(--accent)]" : ""}`}
                  style={marks.includes("emphasis") ? {
                    boxShadow: "0 0 0 1px rgba(255, 186, 46, 0.45), var(--shadow-md)"
                  } : undefined}
                >
                  {kfRel && (
                    <button
                      type="button"
                      onClick={e => {
                        e.stopPropagation();
                        if (lbi !== undefined) setLbIdx(lbi);
                      }}
                      className="shrink-0 w-20 h-14 rounded-lg overflow-hidden bg-[var(--bg-muted)]
                                 relative group/kf"
                      title="查看大图"
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
                    <div className="flex items-center gap-1.5 mb-1">
                      <span className="text-xs text-[var(--fg-tertiary)] tabular-nums">
                        {formatTime(c.start)}
                      </span>
                      {marks.includes("emphasis") && (
                        <span className="mark-emphasis"><Sparkles size={11} color="#b8851a" /></span>
                      )}
                      {marks.includes("hard") && (
                        <span className="mark-hard"><Target size={11} color="#b86a05" /></span>
                      )}
                    </div>
                    <div className="text-sm font-medium leading-snug line-clamp-2">
                      {pickByLang(c, "headline", lang) || c.text.slice(0, 30)}
                    </div>
                    {(() => {
                      const summary_t = pickByLang(c, "summary", lang);
                      const text_t = pickByLang(c, "text", lang);
                      const preview = summary_t || text_t.slice(0, 120);
                      return preview ? (
                        <div className="mt-1.5 text-xs text-[var(--fg-secondary)] leading-relaxed line-clamp-3">
                          {preview}
                        </div>
                      ) : null;
                    })()}
                    {(() => {
                      const langKws =
                        (c as unknown as Record<string, unknown>)[`keywords_${lang}`];
                      const kws = (Array.isArray(langKws) && langKws.length
                        ? langKws : c.keywords) as string[] | undefined;
                      if (!kws || !kws.length) return null;
                      const clean = filterStopwords(kws).slice(0, 3);
                      return clean.length > 0 ? (
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {clean.map((kw, i) => (
                            <span key={`${kw}-${i}`} className="text-[10px] text-[var(--fg-tertiary)]">·{kw}</span>
                          ))}
                        </div>
                      ) : null;
                    })()}
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
                <button
                  onClick={() => onSeek(ch.start)}
                  className="shrink-0 text-xs tabular-nums text-[var(--accent)] hover:underline"
                >
                  {formatTime(ch.start)}
                </button>
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
    </div>
  );
}
