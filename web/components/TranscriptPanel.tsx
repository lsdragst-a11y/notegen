"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { LocateFixed } from "lucide-react";
import type { Chunk } from "@/lib/types";
import { formatTime } from "@/lib/notes";
import { useLang } from "./LangContext";

interface Sentence {
  start: number;
  end: number;
  text: string;
}

interface Props {
  summary: Chunk[];
  currentTime: number;
  onSeek: (sec: number) => void;
}

/**
 * 逐字稿面板（左栏「章节 | 逐字稿」tab 的逐字稿侧）。
 * 句级数据来自 ASR segments（带时间戳）；旧笔记缺 segments 时回落到 chunk 粒度。
 * 随播放高亮当前句 + 自动滚动（可关），点句跳转视频。
 * 性能：行列表只依赖 currentIdx（不依赖 currentTime），timeupdate 不会重渲染整列。
 */
export default function TranscriptPanel({ summary, currentTime, onSeek }: Props) {
  const { lang } = useLang();
  const [follow, setFollow] = useState(true);
  const activeRef = useRef<HTMLButtonElement>(null);

  const sentences: Sentence[] = useMemo(
    () => summary
      .flatMap(c =>
        c.segments && c.segments.length
          ? c.segments.map(s => ({ start: s.start, end: s.end, text: (s.text || "").trim() }))
          : [{ start: c.start, end: c.end, text: (c.text || "").trim() }])
      .filter(s => s.text),
    [summary],
  );

  // 当前句 = 最后一个 start <= currentTime 的句子（句间间隙落到上一句）
  const currentIdx = useMemo(() => {
    let idx = -1;
    for (let i = 0; i < sentences.length; i++) {
      if (sentences[i].start <= currentTime) idx = i;
      else break;
    }
    return idx;
  }, [sentences, currentTime]);

  useEffect(() => {
    if (follow) {
      activeRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [currentIdx, follow]);

  // 行列表 memo 到 currentIdx：播放中每秒 ~4 次的 currentTime 变化不触发整列重渲染
  const rows = useMemo(
    () => sentences.map((s, i) => {
      const active = i === currentIdx;
      return (
        <button
          key={i}
          ref={active ? activeRef : undefined}
          onClick={() => onSeek(s.start)}
          aria-current={active ? "true" : undefined}
          className={`w-full rounded-lg px-2.5 py-1.5 text-left transition-colors
                      ${active
                        ? "bg-[color-mix(in_srgb,var(--accent)_12%,transparent)]"
                        : "hover:bg-[var(--bg-muted)]"}`}
        >
          <span className={`mr-1.5 text-[10px] tabular-nums
                            ${active ? "text-[var(--accent)]" : "text-[var(--fg-tertiary)]"}`}>
            {formatTime(s.start)}
          </span>
          <span className={`text-xs leading-relaxed
                            ${active ? "text-[var(--accent)]" : "text-[var(--fg-secondary)]"}`}>
            {s.text}
          </span>
        </button>
      );
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sentences, currentIdx, onSeek],
  );

  if (sentences.length === 0) {
    return (
      <p className="px-3 py-4 text-xs text-[var(--fg-tertiary)]">
        {lang === "en" ? "No transcript available." : "这篇笔记没有逐字稿数据。"}
      </p>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between px-2.5 pb-1.5">
        <span className="text-[11px] text-[var(--fg-tertiary)] tabular-nums">
          {sentences.length} {lang === "en" ? "lines" : "句"}
        </span>
        <button
          type="button"
          onClick={() => setFollow(f => !f)}
          aria-pressed={follow}
          title={lang === "en" ? "Follow playback" : "跟随播放自动滚动"}
          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] transition-colors
                      ${follow
                        ? "bg-[color-mix(in_srgb,var(--accent)_14%,transparent)] text-[var(--accent)]"
                        : "text-[var(--fg-tertiary)] hover:bg-[var(--bg-muted)] hover:text-[var(--fg-secondary)]"}`}
        >
          <LocateFixed size={11} />
          {lang === "en" ? "Follow" : "跟随"}
        </button>
      </div>
      <div className="flex flex-col gap-0.5">{rows}</div>
    </div>
  );
}
