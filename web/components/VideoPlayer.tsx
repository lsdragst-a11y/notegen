"use client";
import { useEffect, useRef, useImperativeHandle, forwardRef } from "react";
import type Plyr from "plyr";
import type { Chapter } from "@/lib/types";
import { formatTime } from "@/lib/notes";
import { useLang, pickByLang } from "./LangContext";

// Plyr 在 module top-level new 时引用 document → SSR 阶段炸；
// 必须在 effect 里 dynamic import（client-only）。type 用 import type 不引入 runtime。

export interface VideoPlayerHandle {
  seek: (sec: number) => void;
  getCurrentTime: () => number;
}

interface Props {
  src: string;
  chapters: Chapter[];
  onTimeUpdate?: (t: number) => void;
  onPlayStateChange?: (playing: boolean) => void;
  poster?: string;
  /** 深链初始定位（秒）：从书签页 ?t= 跳转时，播放器就绪后自动 seek 一次。 */
  startTime?: number;
}

/**
 * Plyr 视频播放器封装。
 * - 进度条上方叠加章节色块（按 chapter.start/end 比例分布）
 * - 暴露 seek/getCurrentTime 给父组件控制
 * - 苹果蓝主色（在 globals.css 用 --plyr-color-main 覆盖）
 */
const VideoPlayer = forwardRef<VideoPlayerHandle, Props>(function VideoPlayer(
  { src, chapters, onTimeUpdate, onPlayStateChange, poster, startTime }, ref
) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const plyrRef = useRef<Plyr | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const { lang } = useLang();
  const chPrefix = lang === "en" ? "Ch" : "第";
  const chSuffix = lang === "en" ? "" : "章：";

  useImperativeHandle(ref, () => ({
    seek: (sec: number) => {
      if (plyrRef.current) plyrRef.current.currentTime = sec;
    },
    getCurrentTime: () => plyrRef.current?.currentTime ?? 0,
  }), []);

  useEffect(() => {
    if (!videoRef.current) return;
    let cancelled = false;
    let cleanup: (() => void) | null = null;
    (async () => {
      const { default: PlyrCtor } = await import("plyr");
      if (cancelled || !videoRef.current) return;
      const player = new PlyrCtor(videoRef.current, {
        controls: ["play-large", "play", "progress", "current-time", "duration",
                   "mute", "volume", "settings", "fullscreen"],
        settings: ["speed"],
        speed: { selected: 1, options: [0.5, 0.75, 1, 1.25, 1.5, 2] },
        keyboard: { focused: true, global: false },
        tooltips: { controls: true, seek: true },
      });
      plyrRef.current = player;
      // 深链定位：就绪/元数据加载后 seek 一次（多事件兜底，首次命中即止）
      if (startTime && startTime > 0) {
        let seeked = false;
        const doSeek = () => {
          if (seeked) return;
          try { player.currentTime = startTime; seeked = true; } catch {}
        };
        player.once("ready", doSeek);
        player.once("loadedmetadata", doSeek);
        player.once("canplay", doSeek);
      }
      const handler = () => {
        if (onTimeUpdate && plyrRef.current) onTimeUpdate(plyrRef.current.currentTime);
      };
      const onPlay = () => onPlayStateChange?.(true);
      const onPause = () => onPlayStateChange?.(false);
      player.on("timeupdate", handler);
      player.on("play", onPlay);
      player.on("pause", onPause);
      cleanup = () => {
        player.off("timeupdate", handler);
        player.off("play", onPlay);
        player.off("pause", onPause);
        try { player.destroy(); } catch {}
        plyrRef.current = null;
      };
    })();
    return () => {
      cancelled = true;
      cleanup?.();
    };
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  // 章节色块（覆盖在 Plyr progress 上）
  const total = chapters.length > 0
    ? chapters[chapters.length - 1].end - chapters[0].start
    : 0;
  const start0 = chapters.length > 0 ? chapters[0].start : 0;
  const chapterColors = ["#0a84ff", "#bf5af2", "#30d158", "#ff9f0a", "#ff375f", "#5e5ce6"];

  return (
    <div ref={containerRef} className="relative">
      <video
        ref={videoRef}
        src={src}
        poster={poster}
        playsInline
        controls
        preload="metadata"
        className="w-full"
      />
      {/* 章节色带：放在播放器下方，跟进度条对齐 */}
      {chapters.length > 0 && total > 0 && (
        <div className="relative h-1.5 mt-1 rounded-full overflow-hidden bg-[var(--bg-muted)]"
             aria-label="章节分布">
          {chapters.map((ch, i) => {
            const left = ((ch.start - start0) / total) * 100;
            const width = ((ch.end - ch.start) / total) * 100;
            return (
              <div
                key={i}
                className="absolute top-0 h-full"
                style={{
                  left: `${left}%`,
                  width: `${width}%`,
                  background: chapterColors[i % chapterColors.length],
                  opacity: 0.55,
                }}
                title={`${chPrefix} ${i + 1} ${chSuffix}${pickByLang(ch, "title", lang)} (${formatTime(ch.start)} - ${formatTime(ch.end)})`}
              />
            );
          })}
        </div>
      )}
    </div>
  );
});

export default VideoPlayer;
