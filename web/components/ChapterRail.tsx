"use client";
import { useEffect, useRef } from "react";
import { CheckCircle2, Circle } from "lucide-react";
import type { Chapter } from "@/lib/types";
import { formatTime } from "@/lib/notes";
import { useLang, pickByLang } from "./LangContext";

interface Props {
  chapters: Chapter[];
  currentIdx: number;
  currentTime: number;
  onSeek: (sec: number) => void;
  /** 学习进度：已学完章节下标 + 勾选回调（不传则不显示勾选 UI） */
  done?: number[];
  onToggleDone?: (idx: number) => void;
}

/**
 * 三栏工作台左栏的垂直章节导航（docs/frontend-redesign.md §3.2）。
 * 当前章高亮 + 章内进度条，子章节仅在当前章下展开，随播放自动滚入视口。
 * 横向版 ChapterNav 保留给 <lg 断点。
 */
export default function ChapterRail({
  chapters, currentIdx, currentTime, onSeek, done, onToggleDone,
}: Props) {
  const { lang } = useLang();
  const activeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [currentIdx]);

  const showProgress = !!onToggleDone;
  const doneCount = (done ?? []).filter(i => i < chapters.length).length;

  return (
    <nav aria-label={lang === "en" ? "Chapters" : "章节"} className="flex flex-col gap-0.5">
      {showProgress && chapters.length > 0 && (
        <div className="flex items-center justify-between px-3 pb-1.5">
          <span className="text-[11px] tabular-nums text-[var(--fg-tertiary)]">
            {doneCount}/{chapters.length} {lang === "en" ? "done" : "已学完"}
          </span>
          <span className="h-1 w-16 overflow-hidden rounded-full bg-[var(--bg-muted)]">
            <span
              className="block h-full rounded-full bg-[#1d9e75] transition-[width] duration-300"
              style={{ width: `${chapters.length ? (doneCount / chapters.length) * 100 : 0}%` }}
            />
          </span>
        </div>
      )}
      {chapters.map((ch, i) => {
        const active = i === currentIdx;
        const isDone = !!done?.includes(i);
        const progress = active
          ? Math.min(1, Math.max(0, (currentTime - ch.start) / Math.max(1, ch.end - ch.start)))
          : 0;
        return (
          <div key={i} className="group/ch relative">
            <button
              ref={active ? activeRef : undefined}
              onClick={() => onSeek(ch.start)}
              aria-current={active ? "location" : undefined}
              className={`relative w-full overflow-hidden rounded-xl px-3 py-2 text-left transition-colors
                          ${showProgress ? "pr-9" : ""}
                          ${active
                            ? "bg-[color-mix(in_srgb,var(--accent)_12%,transparent)]"
                            : "hover:bg-[var(--bg-muted)]"}`}
            >
              <span className={`block text-[11px] tabular-nums
                                ${active ? "text-[var(--accent)]" : "text-[var(--fg-tertiary)]"}`}>
                {formatTime(ch.start)}
              </span>
              <span className={`mt-0.5 line-clamp-2 block text-[13px] font-medium leading-snug
                                ${isDone && !active ? "opacity-60" : ""}
                                ${active ? "text-[var(--accent)]" : "text-[var(--fg-secondary)]"}`}>
                {pickByLang(ch, "title", lang)}
              </span>
              {active && (
                <span
                  className="absolute bottom-0 left-0 h-0.5 bg-[var(--accent)] transition-[width] duration-150"
                  style={{ width: `${progress * 100}%` }}
                />
              )}
            </button>
            {showProgress && (
              <button
                type="button"
                onClick={e => { e.stopPropagation(); onToggleDone!(i); }}
                aria-pressed={isDone}
                title={isDone
                  ? (lang === "en" ? "Mark as not done" : "取消已学完")
                  : (lang === "en" ? "Mark as done" : "标记已学完")}
                className={`absolute right-1.5 top-1/2 inline-flex h-7 w-7 -translate-y-1/2 items-center
                            justify-center rounded-full transition-all
                            ${isDone
                              ? "text-[#1d9e75]"
                              : "text-[var(--fg-tertiary)] opacity-0 hover:text-[var(--fg-secondary)] group-hover/ch:opacity-100"}`}
              >
                {isDone ? <CheckCircle2 size={15} /> : <Circle size={15} />}
              </button>
            )}
            {active && !!ch.children?.length && (
              <div className="mb-1 ml-3 mt-0.5 flex flex-col gap-0.5 border-l border-[var(--border)] pl-2">
                {ch.children.map((sub, si) => {
                  const subActive = currentTime >= sub.start && currentTime < sub.end;
                  return (
                    <button
                      key={si}
                      onClick={() => onSeek(sub.start)}
                      aria-current={subActive ? "location" : undefined}
                      className={`rounded-lg px-2 py-1.5 text-left text-xs leading-snug transition-colors
                                  ${subActive
                                    ? "text-[var(--accent)]"
                                    : "text-[var(--fg-tertiary)] hover:bg-[var(--bg-muted)] hover:text-[var(--fg-secondary)]"}`}
                    >
                      <span className="mr-1.5 tabular-nums opacity-70">{formatTime(sub.start)}</span>
                      {pickByLang(sub, "title", lang)}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </nav>
  );
}
