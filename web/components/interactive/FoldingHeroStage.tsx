"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, useMotionValue, useReducedMotion, useTransform } from "framer-motion";
import { FileText, Film, MousePointer2, Play } from "lucide-react";

import { clampFoldProgress, getFoldPhase, type FoldPhase } from "./motionModel";

const PHASE_LABEL: Record<FoldPhase, string> = {
  import: "导入视频",
  fold: "折叠时间线",
  note: "生成笔记页",
};

const FILM_FRAMES = ["00:04", "03:11", "08:42", "12:18"];
const NOTE_CARDS = [
  { time: "03:11", title: "章节自动展开", copy: "把连续视频切成可复习的学习段落。" },
  { time: "08:42", title: "重点被折进纸页", copy: "关键概念、时间戳和摘要同时保留。" },
  { time: "12:18", title: "回答回到证据", copy: "提问后能跳回原视频片段。" },
];

function easeOutQuint(value: number) {
  return 1 - Math.pow(1 - value, 5);
}

function interpolate(start: number, end: number, progress: number) {
  return start + (end - start) * progress;
}

export function FoldingHeroStage() {
  const shouldReduceMotion = useReducedMotion();
  const stageRef = useRef<HTMLDivElement>(null);
  const progress = useMotionValue(0.72);
  const [rangeValue, setRangeValue] = useState(72);
  const [phase, setPhase] = useState<FoldPhase>("note");

  const playheadLeft = useTransform(progress, [0, 1], ["12%", "88%"]);
  const filmX = useTransform(progress, [0, 1], ["0%", "-16%"]);
  const foldScale = useTransform(progress, [0, 1], [0.88, 1.04]);
  const noteOpacity = useTransform(progress, [0.18, 0.72], [0.28, 1]);
  const noteX = useTransform(progress, [0, 1], [32, 0]);
  const beamOpacity = useTransform(progress, [0.1, 0.5, 1], [0.2, 0.92, 0.38]);

  const setFoldProgress = useCallback((value: number) => {
    const safe = clampFoldProgress(value);
    progress.set(safe);
    setRangeValue(Math.round(safe * 100));
    setPhase(getFoldPhase(safe));
  }, [progress]);

  const setFromClientX = useCallback((clientX: number) => {
    const rect = stageRef.current?.getBoundingClientRect();
    if (!rect) return;
    setFoldProgress((clientX - rect.left) / rect.width);
  }, [setFoldProgress]);

  useEffect(() => {
    if (shouldReduceMotion) {
      return;
    }

    let frame = 0;
    const started = performance.now();
    const duration = 1600;

    const tick = (now: number) => {
      const elapsed = Math.min(1, (now - started) / duration);
      const value = elapsed < 0.62
        ? interpolate(0.12, 0.84, easeOutQuint(elapsed / 0.62))
        : interpolate(0.84, 0.46, easeOutQuint((elapsed - 0.62) / 0.38));
      setFoldProgress(value);
      if (elapsed < 1) frame = window.requestAnimationFrame(tick);
    };

    frame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frame);
  }, [setFoldProgress, shouldReduceMotion]);

  return (
    <section
      className="relative mx-auto w-full max-w-2xl"
      aria-label="可交互的视频折叠成笔记演示"
      data-phase={phase}
    >
      <div className="absolute -left-6 top-8 hidden h-36 w-36 rounded-full bg-[var(--wf-brand-coral)] opacity-12 blur-3xl md:block" />
      <div
        ref={stageRef}
        className="group relative min-h-[35rem] overflow-hidden rounded-[2rem] border border-[var(--wf-border-strong)] bg-[#17120f] p-5 text-[#fff7ed] shadow-[var(--wf-shadow-lg)]"
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          setFromClientX(event.clientX);
        }}
        onPointerMove={(event) => {
          if (event.pointerType !== "touch") setFromClientX(event.clientX);
        }}
      >
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18%_16%,rgba(228,123,89,.24),transparent_34%),linear-gradient(135deg,rgba(255,250,243,.08),transparent_42%)]" />
        <motion.div
          aria-hidden="true"
          className="pointer-events-none absolute left-8 right-8 top-1/2 h-px bg-[#fff7ed]/14"
          style={{ opacity: beamOpacity }}
        />
        <motion.div
          aria-hidden="true"
          className="pointer-events-none absolute top-[17%] bottom-[18%] z-20 w-px bg-[var(--wf-brand-coral)] shadow-[0_0_22px_rgba(228,123,89,.72)]"
          style={{ left: playheadLeft }}
        >
          <span className="absolute -left-3 -top-3 flex h-6 w-6 items-center justify-center rounded-full border border-[#ffb28f]/70 bg-[#2a1710] text-[#ffb28f]">
            <Play size={10} fill="currentColor" aria-hidden="true" />
          </span>
        </motion.div>

        <div className="relative z-10 flex items-center justify-between">
          <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/10 px-3 py-1 text-xs font-medium text-[#ffcfb7]">
            <MousePointer2 size={13} aria-hidden="true" />
            拖动时间指针
          </span>
          <span className="rounded-full bg-white/10 px-3 py-1 text-xs tabular-nums text-[#d8c8ba]">
            {PHASE_LABEL[phase]}
          </span>
        </div>

        <div className="relative z-10 mt-8 grid min-h-[24rem] gap-5 md:grid-cols-[0.86fr_0.16fr_1fr] md:items-center">
          <motion.div
            className="relative overflow-hidden rounded-[1.4rem] border border-white/10 bg-black/28 p-3 shadow-[0_20px_60px_rgba(0,0,0,.28)]"
            style={{ x: filmX }}
          >
            <div className="mb-3 flex items-center justify-between text-xs text-[#d8c8ba]">
              <span className="inline-flex items-center gap-1.5">
                <Film size={14} aria-hidden="true" />
                Video strip
              </span>
              <span>16:42</span>
            </div>
            <div className="grid gap-2">
              {FILM_FRAMES.map((time, index) => (
                <div
                  key={time}
                  className="relative h-16 overflow-hidden rounded-xl border border-white/10 bg-[linear-gradient(135deg,rgba(255,247,237,.16),rgba(228,123,89,.08)),#211a16]"
                >
                  <div className="absolute inset-y-0 left-3 flex items-center text-[10px] tabular-nums text-[#ffb28f]">
                    {time}
                  </div>
                  <div
                    className="absolute right-3 top-1/2 h-8 w-[56%] -translate-y-1/2 rounded-lg bg-white/10"
                    style={{ opacity: 0.26 + index * 0.12 }}
                  />
                </div>
              ))}
            </div>
          </motion.div>

          <motion.div
            aria-hidden="true"
            className="mx-auto hidden h-36 w-12 items-center justify-center md:flex"
            style={{ scale: foldScale }}
          >
            <span className="h-full w-px bg-gradient-to-b from-transparent via-[#ffb28f] to-transparent" />
            <span className="absolute h-16 w-16 rounded-full border border-[#ffb28f]/35 bg-[#ffb28f]/10 blur-[1px]" />
          </motion.div>

          <motion.div className="relative min-h-[20rem]" style={{ opacity: noteOpacity, x: noteX }}>
            {NOTE_CARDS.map((card, index) => (
              <motion.article
                key={card.time}
                className="absolute left-0 right-0 rounded-[1.35rem] border border-[#3b2a22] bg-[#fff7ed] p-4 text-[#2d2925] shadow-[0_20px_48px_rgba(0,0,0,.22)]"
                style={{
                  top: `${index * 5.3}rem`,
                  rotate: `${index === 0 ? -2 : index === 1 ? 1.5 : 3}deg`,
                  transformOrigin: "12% 50%",
                }}
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-[rgba(182,92,58,.12)] px-2.5 py-1 text-xs font-semibold tabular-nums text-[var(--wf-accent)]">
                    <FileText size={12} aria-hidden="true" />
                    {card.time}
                  </span>
                  <span className="h-1.5 w-12 rounded-full bg-[rgba(182,92,58,.18)]" />
                </div>
                <h3 className="mt-3 text-base font-semibold tracking-[-0.02em]">{card.title}</h3>
                <p className="mt-2 text-sm leading-6 text-[#665d55]">{card.copy}</p>
              </motion.article>
            ))}
          </motion.div>
        </div>

        <div className="relative z-10 mt-7 rounded-[1.25rem] border border-white/10 bg-white/[0.075] p-4">
          <label className="flex items-center justify-between gap-3 text-xs text-[#d8c8ba]" htmlFor="fold-progress">
            <span>控制视频折叠进度</span>
            <span className="tabular-nums text-[#ffb28f]">{rangeValue}%</span>
          </label>
          <input
            id="fold-progress"
            type="range"
            min={0}
            max={100}
            value={rangeValue}
            onChange={(event) => setFoldProgress(Number(event.target.value) / 100)}
            className="wf-fold-range mt-3 w-full"
            aria-valuetext={PHASE_LABEL[phase]}
          />
        </div>

        <p className="sr-only" aria-live="polite">
          当前演示阶段：{PHASE_LABEL[phase]}
        </p>
      </div>
    </section>
  );
}
