"use client";
import { useEffect, useMemo, useRef, useState, use } from "react";
import Link from "next/link";
import { ArrowLeft, Search } from "lucide-react";
import NavBar from "@/components/NavBar";
import VideoPlayer, { VideoPlayerHandle } from "@/components/VideoPlayer";
import ChapterNav from "@/components/ChapterNav";
import NotesContent from "@/components/NotesContent";
import ChapterDetailCard from "@/components/ChapterDetailCard";
import Spotlight from "@/components/Spotlight";
import MiniPlayer from "@/components/MiniPlayer";
import { fetchNote, formatTime, buildGlossary } from "@/lib/notes";
import type { NoteBundle } from "@/lib/notes";
import { useLang, pickByLang } from "@/components/LangContext";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function NoteDetailPage({ params }: PageProps) {
  const { id } = use(params);
  const { lang } = useLang();
  const [bundle, setBundle] = useState<NoteBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [spotOpen, setSpotOpen] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [mainInView, setMainInView] = useState(true);
  const [miniDismissed, setMiniDismissed] = useState(false);
  const playerRef = useRef<VideoPlayerHandle>(null);
  const mainWrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchNote(id).then(setBundle).catch(e => setError(String(e)));
  }, [id]);

  // ⌘K / Ctrl+K 全局唤起 Spotlight
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSpotOpen(o => !o);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

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

  const glossary = useMemo(
    () => (bundle ? buildGlossary(bundle.summary, 30) : []),
    [bundle]
  );

  const currentChapter = useMemo(() => {
    if (!bundle) return -1;
    const idx = bundle.chapters.findIndex(c => currentTime >= c.start && currentTime < c.end);
    if (idx >= 0) return idx;
    if (bundle.chapters.length > 0 && currentTime >= bundle.chapters[bundle.chapters.length - 1].end) {
      return bundle.chapters.length - 1;
    }
    return 0;
  }, [bundle, currentTime]);

  const seek = (sec: number) => {
    playerRef.current?.seek(sec);
    setCurrentTime(sec);
  };

  if (error) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <div className="apple-card p-8 max-w-md">
          <h2 className="text-lg font-semibold mb-2">加载失败</h2>
          <p className="text-sm text-[var(--fg-secondary)]">{error}</p>
          <Link href="/" className="apple-button inline-flex mt-4">返回</Link>
        </div>
      </main>
    );
  }
  if (!bundle) {
    return (
      <main className="min-h-screen pb-24">
        <NavBar>
          <div className="flex items-center gap-2 min-w-0">
            <Link href="/"
                  className="inline-flex items-center gap-1 text-xs text-[var(--fg-tertiary)]
                             hover:text-[var(--fg)] transition-colors shrink-0">
              <ArrowLeft size={12} /> 返回
            </Link>
            <span className="text-[var(--fg-tertiary)] shrink-0">·</span>
            <span className="text-sm text-[var(--fg-tertiary)] truncate">加载中…</span>
          </div>
        </NavBar>
        <div className="max-w-7xl mx-auto px-6 mt-6 grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-6 animate-pulse">
          <div className="space-y-3">
            <div className="apple-card aspect-video bg-[var(--bg-muted)]" />
            <div className="flex gap-2 overflow-hidden">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-9 w-32 rounded-2xl bg-[var(--bg-muted)] shrink-0" />
              ))}
            </div>
            <div className="apple-card p-5 space-y-3">
              <div className="h-4 w-2/3 rounded bg-[var(--bg-muted)]" />
              <div className="h-3 w-full rounded bg-[var(--bg-muted)]" />
              <div className="h-3 w-5/6 rounded bg-[var(--bg-muted)]" />
              <div className="h-1 w-full rounded bg-[var(--bg-muted)]" />
            </div>
          </div>
          <div className="space-y-6">
            <div className="apple-card p-6 space-y-3">
              <div className="h-6 w-3/4 rounded bg-[var(--bg-muted)]" />
              <div className="h-4 w-1/2 rounded bg-[var(--bg-muted)]" />
              <div className="flex gap-2 pt-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="h-6 w-16 rounded-full bg-[var(--bg-muted)]" />
                ))}
              </div>
            </div>
            <div>
              <div className="h-5 w-32 rounded bg-[var(--bg-muted)] mb-3" />
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="apple-card p-4 flex gap-3">
                    <div className="w-20 h-14 rounded-lg bg-[var(--bg-muted)] shrink-0" />
                    <div className="flex-1 space-y-2">
                      <div className="h-3 w-1/3 rounded bg-[var(--bg-muted)]" />
                      <div className="h-4 w-5/6 rounded bg-[var(--bg-muted)]" />
                      <div className="h-3 w-full rounded bg-[var(--bg-muted)]" />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </main>
    );
  }

  const title = bundle.meta?.title || id;

  return (
    <main className="min-h-screen pb-24">
      <NavBar>
        <div className="flex items-center gap-2 min-w-0">
          <Link href="/"
                className="inline-flex items-center gap-1 text-xs text-[var(--fg-tertiary)]
                           hover:text-[var(--fg)] transition-colors shrink-0">
            <ArrowLeft size={12} /> 返回
          </Link>
          <span className="text-[var(--fg-tertiary)] shrink-0">·</span>
          <span className="text-sm font-medium truncate">{title}</span>
          <button
            onClick={() => setSpotOpen(true)}
            className="ml-auto hidden sm:inline-flex items-center gap-1.5 text-xs
                       text-[var(--fg-tertiary)] hover:text-[var(--fg)]
                       px-2 py-1 rounded-lg border border-[var(--border)]
                       hover:bg-[var(--bg-muted)] transition-colors shrink-0"
            title="搜索（⌘K）"
          >
            <Search size={11} />
            <span>搜索</span>
            <kbd className="text-[10px] opacity-70">⌘K</kbd>
          </button>
        </div>
      </NavBar>

      <div className="max-w-7xl mx-auto px-6 mt-6 grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-6">
        {/* 左：视频 + 章节快速导航 */}
        <div className="lg:sticky lg:top-20 lg:self-start space-y-3">
          <div ref={mainWrapRef} className="apple-card overflow-hidden p-0">
            <VideoPlayer
              ref={playerRef}
              src={bundle.videoUrl}
              chapters={bundle.chapters}
              onTimeUpdate={setCurrentTime}
              onPlayStateChange={setIsPlaying}
            />
          </div>
          {bundle.chapters.length > 1 && (
            <ChapterNav
              chapters={bundle.chapters}
              currentIdx={currentChapter}
              currentTime={currentTime}
              onSeek={seek}
            />
          )}
          {bundle.chapters.length > 0 && currentChapter >= 0 && (
            <div className="lg:hidden text-xs text-[var(--fg-tertiary)] flex items-center gap-2 px-1">
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
        </div>

        {/* 右：笔记 */}
        <div className="min-w-0">
          <NotesContent
            noteId={id}
            title={title}
            summary={bundle.summary}
            chapters={bundle.chapters}
            overview={bundle.overview}
            currentTime={currentTime}
            onSeek={seek}
            category={bundle.meta?.category}
          />
        </div>
      </div>

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
