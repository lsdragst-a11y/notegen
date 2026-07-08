"use client";
import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Clock } from "lucide-react";
import type { Chapter, Chunk, Category, Overview } from "@/lib/types";
import { chunkMarks, overviewKeywords, buildGlossary, formatTime } from "@/lib/notes";
import { useLang } from "./LangContext";
import KeyPointsGrid from "./KeyPointsGrid";
import ChapterSection from "./ChapterSection";
import GlossarySection from "./GlossarySection";
import Lightbox, { LightboxItem } from "./Lightbox";
import VlogTimeline from "./VlogTimeline";
import OverviewHero from "./OverviewHero";
import KeyPointModal from "./KeyPointModal";

interface Props {
  keyframeBase: string;
  noteId: string;
  title: string;
  summary: Chunk[];
  chapters: Chapter[];
  overview?: Overview | null;
  currentTime: number;
  onSeek: (sec: number, sourceElement?: HTMLElement | null) => void;
  /** 视频内容大类。teaching=保留全部；popsci=去🎯且术语表折叠；
   *  vlog/talk=时间轴卡片替代知识点速览且无术语表。 */
  category?: Category;
  /** 章节学习进度（page 层 useChapterProgress 单一来源） */
  chaptersDone?: number[];
  onToggleChapterDone?: (idx: number) => void;
  readOnly?: boolean;
}

/**
 * 笔记内容编排层：算派生量 + 管 Lightbox/详情弹层状态，
 * 渲染交给 KeyPointsGrid / ChapterSection / GlossarySection（§3.3 拆分）。
 */
export default function NotesContent({
  keyframeBase, noteId, title, summary, chapters, overview, currentTime, onSeek, category = "teaching",
  chaptersDone, onToggleChapterDone, readOnly = false,
}: Props) {
  const { lang } = useLang();
  // currentTime 每秒驱动 ~4 次重渲染，这些纯派生量（正则/排序扫全部 chunks）
  // 必须 memo，否则每次 timeupdate 都白算一遍
  const keywords = useMemo(() => overviewKeywords(summary, 8, lang), [summary, lang]);
  const glossary = useMemo(() => buildGlossary(summary, 15, lang), [summary, lang]);
  const marksByChunk = useMemo(() => summary.map(c => chunkMarks(c)), [summary]);
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
        className="rounded-[var(--wf-radius-md)] border border-[var(--wf-border)] bg-[var(--wf-surface)] p-6 shadow-[var(--wf-shadow-sm)]"
      >
        <h1 className="text-2xl font-semibold leading-tight tracking-tight">{title}</h1>
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-[var(--wf-text-secondary)]">
          <span className="inline-flex items-center gap-1"><Clock size={14} />{formatTime(total)}</span>
          <span>·</span>
          <span>
            {chapters.length} {chapterHeaderLabel} / {summary.length} {lang === "en" ? "clips" : "段"}
          </span>
        </div>
        {keywords.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {keywords.map((k, i) => (
              <span
                key={`${k}-${i}`}
                className="rounded-[var(--wf-radius-full)] border border-[var(--wf-border)] bg-[var(--wf-surface-muted)] px-2.5 py-1 text-xs font-medium text-[var(--wf-text-secondary)]"
              >
                {k}
              </span>
            ))}
          </div>
        )}
      </motion.section>

      {/* 全文总结 hero：散文概览 + 你将学到（有 overview 才渲染） */}
      {overview && <OverviewHero overview={overview} />}

      {/* 中间主区：教学/科普 → 知识点速览卡片；vlog/talk → 时间轴 */}
      {showKnowledgePoints ? (
        <KeyPointsGrid
          summary={summary}
          keyframeBase={keyframeBase}
          noteId={noteId}
          noteTitle={title}
          currentChunkIdx={currentChunkIdx}
          marksByChunk={marksByChunk}
          showMarks={showMarks}
          onSeek={onSeek}
          onOpenDetail={setDetailIdx}
          onOpenLightbox={openLightboxForChunk}
          readOnly={readOnly}
        />
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
      <ChapterSection
        chapters={chapters}
        summary={summary}
        noteId={noteId}
        noteTitle={title}
        marksByChunk={marksByChunk}
        showMarks={showMarks}
        headerLabel={chapterHeaderLabel}
        headerIcon={chapterHeaderIcon}
        onSeek={onSeek}
        done={chaptersDone}
        onToggleDone={onToggleChapterDone}
        readOnly={readOnly}
      />

      {/* 术语表（vlog/talk 完全隐藏；popsci 折叠；teaching 展开） */}
      {showGlossary && glossary.length > 0 && (
        <GlossarySection glossary={glossary} defaultOpen={glossaryDefaultOpen} onSeek={onSeek} />
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
        marks={detailIdx !== null && showMarks ? marksByChunk[detailIdx] ?? [] : []}
        onClose={() => setDetailIdx(null)}
        onSeek={onSeek}
        readOnly={readOnly}
      />
    </div>
  );
}
