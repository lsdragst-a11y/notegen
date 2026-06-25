"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft, Bookmark, Check, Download, FileText, Link2, PanelLeft, Search, Share2, X,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import NavBar from "@/components/NavBar";
import VideoPlayer, { VideoPlayerHandle } from "@/components/VideoPlayer";
import ChapterNav from "@/components/ChapterNav";
import NotesContent from "@/components/NotesContent";
import ChapterDetailCard from "@/components/ChapterDetailCard";
import ChapterChip from "@/components/ChapterChip";
import Spotlight from "@/components/Spotlight";
import MiniPlayer from "@/components/MiniPlayer";
import ChapterRail from "@/components/ChapterRail";
import TranscriptPanel from "@/components/TranscriptPanel";
import ChatPanel from "@/components/ChatPanel";
import { formatTime, buildGlossary } from "@/lib/notes";
import type { NoteBundle } from "@/lib/notes";
import { getShare, postShare, revokeShare, ApiError } from "@/lib/api";
import { buildMarkdown, downloadMarkdown, downloadDocx } from "@/lib/export";
import { useChapterProgress } from "@/lib/progress";
import { useLang, pickByLang } from "@/components/LangContext";
import { useAuth } from "@/components/AuthContext";

type RailTab = "chapters" | "transcript";

interface Props {
  noteId: string;
  bundle: NoteBundle;
  backHref: string;
  /** 分享只读模式（/s/{token}）：隐藏分享/问答/书签入口 */
  shared?: boolean;
}

/** 加载失败卡（/notes/[id] 与 /s/[token] 共用） */
export function WorkspaceError({ error, backHref }: { error: string; backHref: string }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[var(--wf-canvas)] text-[var(--wf-text)]">
      <div className="max-w-md rounded-[var(--wf-radius-md)] border border-[var(--wf-border)] bg-[var(--wf-surface)] p-8 shadow-[var(--wf-shadow-sm)]">
        <h2 className="text-lg font-semibold mb-2">加载失败</h2>
        <p className="text-sm text-[var(--wf-text-secondary)]">{error}</p>
        <Link href={backHref} className="mt-4 inline-flex rounded-[var(--wf-radius-sm)] bg-[var(--wf-accent)] px-4 py-2 text-sm font-semibold text-[var(--wf-on-accent)] transition-colors hover:bg-[var(--wf-accent-hover)]">返回</Link>
      </div>
    </main>
  );
}

/** 三栏同构骨架屏（/notes/[id] 与 /s/[token] 共用） */
export function WorkspaceSkeleton({ backHref }: { backHref: string }) {
  return (
    <main className="min-h-screen bg-[var(--wf-canvas)] pb-24 text-[var(--wf-text)]">
      <NavBar>
        <div className="flex items-center gap-2 min-w-0">
          <Link href={backHref}
                className="inline-flex items-center gap-1 text-xs text-[var(--wf-text-tertiary)]
                           hover:text-[var(--wf-text)] transition-colors shrink-0">
            <ArrowLeft size={12} /> 返回
          </Link>
          <span className="text-[var(--wf-text-tertiary)] shrink-0">·</span>
          <span className="text-sm text-[var(--wf-text-tertiary)] truncate">加载中…</span>
        </div>
      </NavBar>
      <div className="mx-auto grid w-full max-w-[1680px] grid-cols-1 gap-5 px-5 pt-5 animate-pulse lg:grid-cols-[260px_minmax(0,1fr)_400px] lg:gap-0 lg:px-0">
        <div className="hidden space-y-2 border-r border-[var(--wf-border)] px-6 py-6 lg:block">
          <div className="h-3 w-10 rounded bg-[var(--wf-surface-muted)]" />
          <div className="h-10 rounded-xl bg-[var(--wf-surface-muted)]" />
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-9 rounded-xl bg-[var(--wf-surface-muted)]" />
          ))}
        </div>
        <div className="order-2 space-y-4 lg:order-none lg:px-8 lg:py-6">
          <div className="space-y-3 rounded-[var(--wf-radius-md)] border border-[var(--wf-border)] bg-[var(--wf-surface)] p-6 shadow-[var(--wf-shadow-sm)]">
            <div className="h-6 w-3/4 rounded bg-[var(--wf-surface-muted)]" />
            <div className="h-4 w-1/2 rounded bg-[var(--wf-surface-muted)]" />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="space-y-2 rounded-[var(--wf-radius-md)] border border-[var(--wf-border)] bg-[var(--wf-surface)] p-4 shadow-[var(--wf-shadow-sm)]">
                <div className="aspect-video rounded-lg bg-[var(--wf-surface-muted)]" />
                <div className="h-4 w-5/6 rounded bg-[var(--wf-surface-muted)]" />
              </div>
            ))}
          </div>
        </div>
        <div className="order-1 space-y-3 lg:order-none lg:border-l lg:border-[var(--wf-border)] lg:px-4 lg:py-6">
          <div className="aspect-video rounded-[var(--wf-radius-md)] border border-[var(--wf-border)] bg-[var(--wf-surface-muted)] shadow-[var(--wf-shadow-sm)]" />
          <div className="h-9 rounded-xl bg-[var(--wf-surface-muted)]" />
          <div className="h-9 rounded-xl bg-[var(--wf-surface-muted)]" />
        </div>
      </div>
    </main>
  );
}

function WorkspaceRail({
  bundle,
  chaptersDone,
  currentChapter,
  currentTime,
  lang,
  onSeek,
  railTab,
  setRailTab,
  shared,
  sourceLabel,
  sourceUrl,
  title,
  toggleChapterDone,
}: {
  bundle: NoteBundle;
  chaptersDone: number[];
  currentChapter: number;
  currentTime: number;
  lang: "zh" | "en";
  onSeek: (sec: number) => void;
  railTab: RailTab;
  setRailTab: (tab: RailTab) => void;
  shared: boolean;
  sourceLabel: string;
  sourceUrl: string;
  title: string;
  toggleChapterDone: (idx: number) => void;
}) {
  return (
    <>
      <p className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--wf-text-tertiary)]">
        {lang === "en" ? "Source" : "来源"}
      </p>
      {sourceUrl ? (
        <a
          href={sourceUrl}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-2 rounded-[var(--wf-radius-sm)] bg-[var(--wf-surface-muted)] px-3 py-2 transition-opacity hover:opacity-80"
        >
          <Link2 size={13} className="shrink-0 text-[var(--wf-accent)]" />
          <span className="min-w-0">
            <span className="block truncate text-xs font-medium text-[var(--wf-text)]">{sourceLabel}</span>
            <span className="block truncate text-[11px] text-[var(--wf-text-tertiary)]">
              {bundle.meta?.uploader || title}
            </span>
          </span>
        </a>
      ) : (
        <div className="flex items-center gap-2 rounded-[var(--wf-radius-sm)] bg-[var(--wf-surface-muted)] px-3 py-2">
          <Link2 size={13} className="shrink-0 text-[var(--wf-text-tertiary)]" />
          <span className="min-w-0">
            <span className="block truncate text-xs font-medium text-[var(--wf-text)]">{sourceLabel}</span>
            <span className="block truncate text-[11px] text-[var(--wf-text-tertiary)]">
              {bundle.meta?.uploader || title}
            </span>
          </span>
        </div>
      )}
      <div className="mb-2 mt-5 flex items-center gap-1 px-1" role="tablist">
        {([
          ["chapters", lang === "en" ? "Chapters" : "章节"],
          ["transcript", lang === "en" ? "Transcript" : "逐字稿"],
        ] as const).map(([key, label]) => {
          const active = railTab === key;
          return (
            <button
              key={key}
              role="tab"
              aria-selected={active}
              onClick={() => setRailTab(key)}
              className={`rounded-full px-3 py-1 text-xs font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--wf-focus)] ${
                active
                  ? "bg-[color-mix(in_srgb,var(--wf-brand-coral)_14%,var(--wf-surface))] text-[var(--wf-accent)]"
                  : "text-[var(--wf-text-secondary)] hover:bg-[var(--wf-surface-muted)] hover:text-[var(--wf-text)]"
              }`}
            >
              {label}
            </button>
          );
        })}
      </div>
      {railTab === "chapters" ? (
        bundle.chapters.length > 0 ? (
          <ChapterRail
            chapters={bundle.chapters}
            currentIdx={currentChapter}
            currentTime={currentTime}
            onSeek={onSeek}
            done={shared ? undefined : chaptersDone}
            onToggleDone={shared ? undefined : toggleChapterDone}
          />
        ) : (
          <p className="px-3 py-4 text-xs text-[var(--wf-text-tertiary)]">
            {lang === "en" ? "No chapters." : "这篇笔记没有章节数据。"}
          </p>
        )
      ) : (
        <TranscriptPanel summary={bundle.summary} currentTime={currentTime} onSeek={onSeek} />
      )}
    </>
  );
}

/**
 * 三栏笔记工作台（docs/frontend-redesign.md §3.2）。
 * /notes/[id] 与 /s/[token] 共用；后者以 shared 模式渲染。
 */
export default function NoteWorkspace({ noteId, bundle, backHref, shared = false }: Props) {
  const { lang } = useLang();
  const { user } = useAuth();
  // 书签深链：?t=秒 → 播放器就绪后定位 + 初始章节高亮
  const [startTime] = useState(() => {
    if (typeof window === "undefined") return 0;
    const t = new URLSearchParams(window.location.search).get("t");
    const n = t ? parseFloat(t) : NaN;
    return Number.isFinite(n) && n > 0 ? n : 0;
  });
  const [currentTime, setCurrentTime] = useState(startTime);
  const [spotOpen, setSpotOpen] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [mainInView, setMainInView] = useState(true);
  const [miniDismissed, setMiniDismissed] = useState(false);
  const [railOpen, setRailOpen] = useState(false);   // <lg 章节抽屉
  const [railTab, setRailTab] = useState<RailTab>("chapters");
  const [shareToken, setShareToken] = useState<string | null>(null);
  const [shareCopied, setShareCopied] = useState(false);
  const [shareHint, setShareHint] = useState<string | null>(null);
  const [docxState, setDocxState] = useState<"idle" | "busy" | "error">("idle");
  const { done: chaptersDone, toggle: toggleChapterDone } = useChapterProgress(noteId);
  const playerRef = useRef<VideoPlayerHandle>(null);
  const mainWrapRef = useRef<HTMLDivElement>(null);

  const glossary = useMemo(
    () => buildGlossary(bundle.summary, 30, lang),
    [bundle, lang]
  );

  const currentChapter = useMemo(() => {
    const idx = bundle.chapters.findIndex(c => currentTime >= c.start && currentTime < c.end);
    if (idx >= 0) return idx;
    if (bundle.chapters.length > 0 && currentTime >= bundle.chapters[bundle.chapters.length - 1].end) {
      return bundle.chapters.length - 1;
    }
    return 0;
  }, [bundle, currentTime]);

  // useCallback：identity 稳定，TranscriptPanel 的行列表 memo 才不会被
  // 每秒 ~4 次的页面重渲染连带打穿
  const seek = useCallback((sec: number) => {
    playerRef.current?.seek(sec);
    setCurrentTime(sec);
  }, []);
  const seekAndCloseRail = useCallback((sec: number) => {
    seek(sec);
    setRailOpen(false);
  }, [seek]);

  // 全局快捷键：⌘K Spotlight；Esc 关抽屉；Space 播放/暂停；←/→ ±5s；[ ] 上/下一章。
  // 输入框/可编辑元素/Plyr 容器内/带 data-overlay 的弹层打开时不劫持。
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSpotOpen(o => !o);
        return;
      }
      if (e.key === "Escape") { setRailOpen(false); return; }
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      if (t?.closest?.(".plyr")) return;            // Plyr 聚焦时用它自带的键盘控制
      if (document.querySelector("[data-overlay]")) return;  // Lightbox/弹窗打开时让位
      const cur = () => playerRef.current?.getCurrentTime() ?? currentTime;
      if (e.key === " ") {
        e.preventDefault();
        playerRef.current?.toggle();
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        seek(Math.max(0, cur() - 5));
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        seek(cur() + 5);
      } else if (e.key === "[" && currentChapter > 0) {
        seek(bundle.chapters[currentChapter - 1].start);
      } else if (e.key === "]" && currentChapter < bundle.chapters.length - 1) {
        seek(bundle.chapters[currentChapter + 1].start);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [bundle, currentChapter, currentTime, seek]);

  // 主视频可见性观察，决定 Mini PiP 是否弹出
  useEffect(() => {
    const el = mainWrapRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      entries => {
        for (const e of entries) {
          const inView = e.isIntersecting && e.intersectionRatio > 0.1;
          setMainInView(inView);
          if (inView) setMiniDismissed(false);  // 滚回主视频时重置 dismiss 状态
        }
      },
      { threshold: [0, 0.1, 0.5] }
    );
    io.observe(el);
    return () => io.disconnect();
  }, [bundle]);  // bundle 变化后 wrap 元素 ref 才到位

  // 已有分享 token 则恢复状态（仅 owner 拿得到，404/401 静默）
  useEffect(() => {
    if (shared || !user) return;
    let alive = true;
    getShare(noteId)
      .then(r => { if (alive && r) setShareToken(r.token); })
      .catch(() => {});
    return () => { alive = false; };
  }, [noteId, user, shared]);

  const handleShare = async () => {
    setShareHint(null);
    try {
      const token = shareToken ?? (await postShare(noteId)).token;
      setShareToken(token);
      await navigator.clipboard.writeText(`${window.location.origin}/s/${token}`);
      setShareCopied(true);
      setTimeout(() => setShareCopied(false), 2000);
    } catch (e) {
      setShareHint(e instanceof ApiError && e.status === 404
        ? (lang === "en" ? "Only the note owner can share." : "仅笔记创建者可以分享")
        : (lang === "en" ? "Share failed, try again." : "分享失败，请重试"));
    }
  };

  const handleRevoke = async () => {
    try {
      await revokeShare(noteId);
      setShareToken(null);
      setShareHint(lang === "en" ? "Link revoked." : "分享已撤销，旧链接立即失效");
      setTimeout(() => setShareHint(null), 2500);
    } catch {
      setShareHint(lang === "en" ? "Revoke failed." : "撤销失败，请重试");
    }
  };

  const title = bundle.meta?.title || noteId;

  const handleExport = () => {
    downloadMarkdown(`${title}.md`, buildMarkdown({
      title, meta: bundle.meta, overview: bundle.overview,
      chapters: bundle.chapters, summary: bundle.summary, lang,
    }));
  };

  const handleExportDocx = async () => {
    if (docxState === "busy") return;
    setDocxState("busy");
    try {
      await downloadDocx(`${title}.docx`, buildMarkdown({
        title, meta: bundle.meta, overview: bundle.overview,
        chapters: bundle.chapters, summary: bundle.summary, lang,
      }));
      setDocxState("idle");
    } catch {
      setDocxState("error");
      setTimeout(() => setDocxState("idle"), 2500);
    }
  };

  const sourceUrl = bundle.meta?.webpage_url || "";
  const sourceLabel = sourceUrl
    ? (sourceUrl.includes("bilibili") ? "Bilibili"
       : sourceUrl.includes("youtu") ? "YouTube"
       : (lang === "en" ? "Web link" : "网页链接"))
    : (lang === "en" ? "Local file" : "本地上传");

  return (
    <main className="flex min-h-screen flex-col bg-[var(--wf-canvas)] pb-24 text-[var(--wf-text)] lg:h-screen lg:overflow-hidden lg:pb-0">
      <NavBar>
        <div className="flex items-center gap-2 min-w-0">
          <Link href={backHref}
                className="inline-flex items-center gap-1 text-xs text-[var(--wf-text-tertiary)]
                           hover:text-[var(--wf-text)] transition-colors shrink-0">
            <ArrowLeft size={12} /> 返回
          </Link>
          <button
            type="button"
            onClick={() => setRailOpen(true)}
            aria-label={lang === "en" ? "Open chapter navigation" : "打开章节导航"}
            className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-md
                       text-[var(--wf-text-tertiary)] transition-colors hover:bg-[var(--wf-surface-muted)]
                       hover:text-[var(--wf-text)] lg:hidden"
          >
            <PanelLeft size={15} />
          </button>
          <span className="text-[var(--wf-text-tertiary)] shrink-0 max-lg:hidden">·</span>
          <span className="text-sm font-medium truncate">{title}</span>
          {shared && (
            <span className="shrink-0 rounded-full bg-[var(--wf-surface-muted)] px-2 py-0.5 text-[10px] text-[var(--wf-text-secondary)]">
              {lang === "en" ? "Shared" : "分享页"}
            </span>
          )}
          <button
            onClick={() => setSpotOpen(true)}
            className="ml-auto hidden lg:inline-flex items-center gap-1.5 text-xs
                       text-[var(--wf-text-tertiary)] hover:text-[var(--wf-text)]
                       px-2 py-1 rounded-lg border border-[var(--wf-border)]
                       hover:bg-[var(--wf-surface-muted)] transition-colors shrink-0"
            title="搜索（⌘K）"
          >
            <Search size={11} />
            <span>搜索</span>
            <kbd className="text-[10px] opacity-70">⌘K</kbd>
          </button>
        </div>
      </NavBar>

      {/* 三栏工作台：来源/章节 · 笔记 · 视频/工具（docs/frontend-redesign.md §3.2）。
          lg 整页不滚、三栏独立滚动；<lg 回落单列（视频在上，笔记在下）。 */}
      <div className="mx-auto grid w-full max-w-[1680px] flex-1 grid-cols-1 lg:min-h-0 lg:grid-cols-[280px_minmax(0,1fr)_420px]">
        {/* 左栏：来源 + 垂直章节（仅 lg；<lg 走顶栏抽屉 + 视频下方横向 ChapterNav） */}
        <aside
          aria-label={lang === "en" ? "Source and chapters" : "来源与章节"}
          className="hidden border-r border-[var(--wf-border)] bg-[var(--wf-surface)]/55 px-3 py-5 lg:block lg:overflow-y-auto"
        >
          <WorkspaceRail
            bundle={bundle}
            chaptersDone={chaptersDone}
            currentChapter={currentChapter}
            currentTime={currentTime}
            lang={lang}
            onSeek={seek}
            railTab={railTab}
            setRailTab={setRailTab}
            shared={shared}
            sourceLabel={sourceLabel}
            sourceUrl={sourceUrl}
            title={title}
            toggleChapterDone={toggleChapterDone}
          />
        </aside>

        {/* 中栏：笔记内容 + 问答 */}
        <div className="order-2 min-w-0 px-5 pt-5 lg:order-none lg:overflow-y-auto lg:px-8 lg:py-6">
          <NotesContent
            keyframeBase={bundle.keyframeBase}
            noteId={noteId}
            title={title}
            summary={bundle.summary}
            chapters={bundle.chapters}
            overview={bundle.overview}
            currentTime={currentTime}
            onSeek={seek}
            category={bundle.meta?.category}
            chaptersDone={shared ? undefined : chaptersDone}
            onToggleChapterDone={shared ? undefined : toggleChapterDone}
            readOnly={shared}
          />
          {!shared && (
            <div className="sticky bottom-3 mt-6">
              <ChatPanel noteId={noteId} onSeek={seek} chapters={bundle.chapters} />
            </div>
          )}
        </div>

        {/* 右栏：视频 + 当前章 + 工具组（<lg 时排最上） */}
        <aside
          aria-label={lang === "en" ? "Video and tools" : "视频与工具"}
          className="order-1 space-y-3 px-5 pt-5 lg:order-none lg:overflow-y-auto lg:border-l lg:border-[var(--wf-border)] lg:bg-[var(--wf-surface)]/55 lg:px-4 lg:py-6"
        >
          <div ref={mainWrapRef} className="relative overflow-hidden rounded-[var(--wf-radius-lg)] border border-[var(--wf-border)] bg-[var(--wf-surface)] p-0 shadow-[var(--wf-shadow-md)]">
            <VideoPlayer
              ref={playerRef}
              src={bundle.videoUrl}
              chapters={bundle.chapters}
              onTimeUpdate={setCurrentTime}
              onPlayStateChange={setIsPlaying}
              startTime={startTime}
            />
            {/* Dynamic Island 章节 chip：播放时浮在视频顶部，章节切换 spring 滑动 */}
            {isPlaying && bundle.chapters.length > 0 && currentChapter >= 0 && (
              <div className="pointer-events-none absolute left-1/2 top-3 z-10 -translate-x-1/2">
                <ChapterChip
                  chapterTitle={pickByLang(bundle.chapters[currentChapter], "title", lang)}
                  chapterIdx={currentChapter}
                  totalChapters={bundle.chapters.length}
                  currentTime={currentTime}
                  chapterStart={bundle.chapters[currentChapter].start}
                  chapterEnd={bundle.chapters[currentChapter].end}
                />
              </div>
            )}
          </div>
          {bundle.chapters.length > 1 && (
            <div className="lg:hidden">
              <ChapterNav
                chapters={bundle.chapters}
                currentIdx={currentChapter}
                currentTime={currentTime}
                onSeek={seek}
              />
            </div>
          )}
          {bundle.chapters.length > 0 && currentChapter >= 0 && (
            <div className="lg:hidden text-xs text-[var(--wf-text-tertiary)] flex items-center gap-2 px-1">
              <span className="tabular-nums">{formatTime(currentTime)}</span>
              <span>·</span>
              <span className="truncate">
                {lang === "en" ? "Ch" : "第"} {currentChapter + 1}{lang === "en" ? "" : " 章"} · {pickByLang(bundle.chapters[currentChapter], "title", lang)}
              </span>
            </div>
          )}
          {bundle.chapters.length > 0 && (
            <ChapterDetailCard
              chapters={bundle.chapters}
              currentIdx={currentChapter}
              currentTime={currentTime}
              summary={bundle.summary}
              onSeek={seek}
            />
          )}
          {/* 工具组 */}
          <div className="grid grid-cols-1 gap-2">
            <button
              type="button"
              onClick={handleExport}
              className="flex items-center gap-2 rounded-xl border border-[var(--wf-border)] bg-[var(--wf-surface)]
                         px-3 py-2 text-xs text-[var(--wf-text-secondary)] transition-colors
                         hover:bg-[var(--wf-surface-muted)] hover:text-[var(--wf-text)] max-lg:min-h-11"
            >
              <Download size={14} className="text-[var(--wf-accent)]" />
              {lang === "en" ? "Export Markdown" : "导出 Markdown"}
            </button>
            <button
              type="button"
              onClick={handleExportDocx}
              disabled={docxState === "busy"}
              className="flex items-center gap-2 rounded-xl border border-[var(--wf-border)] bg-[var(--wf-surface)]
                         px-3 py-2 text-xs text-[var(--wf-text-secondary)] transition-colors
                         hover:bg-[var(--wf-surface-muted)] hover:text-[var(--wf-text)] max-lg:min-h-11
                         disabled:opacity-60 disabled:cursor-wait"
            >
              <FileText size={14} className={docxState === "error" ? "text-[var(--wf-danger)]" : "text-[var(--wf-accent)]"} />
              {docxState === "busy"
                ? (lang === "en" ? "Exporting…" : "导出中…")
                : docxState === "error"
                  ? (lang === "en" ? "Export failed, retry" : "导出失败，点击重试")
                  : (lang === "en" ? "Export Word" : "导出 Word")}
            </button>
            {!shared && (
              <>
                <button
                  type="button"
                  onClick={handleShare}
                  className="flex items-center gap-2 rounded-xl border border-[var(--wf-border)] bg-[var(--wf-surface)]
                             px-3 py-2 text-xs text-[var(--wf-text-secondary)] transition-colors
                             hover:bg-[var(--wf-surface-muted)] hover:text-[var(--wf-text)] max-lg:min-h-11"
                >
                  {shareCopied
                    ? <Check size={14} className="text-[#1d9e75]" />
                    : <Share2 size={14} className="text-[var(--wf-accent)]" />}
                  {shareCopied
                    ? (lang === "en" ? "Link copied" : "链接已复制")
                    : shareToken
                      ? (lang === "en" ? "Copy share link" : "复制分享链接")
                      : (lang === "en" ? "Share link" : "生成分享链接")}
                  {shareToken && (
                    <span
                      role="button"
                      tabIndex={0}
                      onClick={e => { e.stopPropagation(); handleRevoke(); }}
                      onKeyDown={e => {
                        if (e.key === "Enter") { e.stopPropagation(); handleRevoke(); }
                      }}
                      title={lang === "en" ? "Revoke link" : "撤销分享"}
                      className="ml-auto rounded-full px-1.5 py-0.5 text-[10px] text-[var(--wf-text-tertiary)]
                                 hover:bg-[var(--wf-danger-surface)] hover:text-[var(--wf-danger)]"
                    >
                      {lang === "en" ? "Revoke" : "撤销"}
                    </span>
                  )}
                </button>
                {shareHint && (
                  <p className="px-1 text-[11px] text-[var(--wf-text-tertiary)]">{shareHint}</p>
                )}
                <Link
                  href="/bookmarks"
                  className="flex items-center gap-2 rounded-xl border border-[var(--wf-border)] bg-[var(--wf-surface)]
                             px-3 py-2 text-xs text-[var(--wf-text-secondary)] transition-colors
                             hover:bg-[var(--wf-surface-muted)] hover:text-[var(--wf-text)] max-lg:min-h-11"
                >
                  <Bookmark size={14} className="text-[var(--wf-accent)]" />
                  {lang === "en" ? "My bookmarks" : "我的书签"}
                </Link>
              </>
            )}
          </div>
        </aside>
      </div>

      {/* <lg 章节抽屉 */}
      <AnimatePresence>
        {railOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-black/40 lg:hidden"
            onClick={() => setRailOpen(false)}
          >
            <motion.aside
              initial={{ x: -288 }}
              animate={{ x: 0 }}
              exit={{ x: -288 }}
              transition={{ type: "spring", stiffness: 320, damping: 32 }}
              role="dialog"
              aria-modal="true"
              aria-label={lang === "en" ? "Chapter navigation" : "章节导航"}
              className="absolute left-0 top-0 h-full w-72 overflow-y-auto border-r
                         border-[var(--wf-border)] bg-[var(--wf-surface)] px-3 py-4"
              onClick={e => e.stopPropagation()}
            >
              <div className="mb-2 flex items-center justify-between px-3">
                <span className="text-sm font-medium">{lang === "en" ? "Chapters" : "章节导航"}</span>
                <button
                  type="button"
                  onClick={() => setRailOpen(false)}
                  aria-label={lang === "en" ? "Close" : "关闭"}
                  className="inline-flex h-11 w-11 items-center justify-center rounded-full
                             text-[var(--wf-text-tertiary)] hover:bg-[var(--wf-surface-muted)] hover:text-[var(--wf-text)]"
                >
                  <X size={15} />
                </button>
              </div>
              <WorkspaceRail
                bundle={bundle}
                chaptersDone={chaptersDone}
                currentChapter={currentChapter}
                currentTime={currentTime}
                lang={lang}
                onSeek={seekAndCloseRail}
                railTab={railTab}
                setRailTab={setRailTab}
                shared={shared}
                sourceLabel={sourceLabel}
                sourceUrl={sourceUrl}
                title={title}
                toggleChapterDone={toggleChapterDone}
              />
            </motion.aside>
          </motion.div>
        )}
      </AnimatePresence>

      <Spotlight
        open={spotOpen}
        onClose={() => setSpotOpen(false)}
        onSeek={seek}
        chapters={bundle.chapters}
        summary={bundle.summary}
        glossary={glossary}
      />

      <MiniPlayer
        visible={!mainInView && !miniDismissed}
        src={bundle.videoUrl}
        currentTime={currentTime}
        isPlaying={isPlaying}
        chapterLabel={
          currentChapter >= 0 && bundle.chapters[currentChapter]
            ? pickByLang(bundle.chapters[currentChapter], "title", lang)
            : undefined
        }
        onClose={() => setMiniDismissed(true)}
        onExpand={() => mainWrapRef.current?.scrollIntoView({ behavior: "smooth", block: "center" })}
      />
    </main>
  );
}
