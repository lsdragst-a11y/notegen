"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  animate,
  motion,
  useMotionValue,
  useMotionValueEvent,
  useReducedMotion,
  useTransform,
} from "framer-motion";
import clsx from "clsx";
import { FileText, Film, MousePointer2, Play, Sparkles } from "lucide-react";

import { clampFoldProgress, getFoldPhase, type FoldPhase } from "./motionModel";

const PHASE_LABEL: Record<FoldPhase, string> = {
  import: "正在识别章节",
  fold: "正在提取重点",
  note: "已生成可回看笔记",
};

const FILM_FRAMES = [
  { time: "00:04", label: "视频导入" },
  { time: "03:11", label: "章节展开" },
  { time: "08:42", label: "重点折叠" },
  { time: "12:18", label: "证据回放" },
] as const;

const NOTE_CARDS = [
  {
    threshold: 0.32,
    time: "03:11",
    title: "章节自动展开",
    copy: "长视频被切成可复习的学习段落。",
  },
  {
    threshold: 0.55,
    time: "08:42",
    title: "重点被折进纸页",
    copy: "关键概念、时间戳和摘要同时保留。",
  },
  {
    threshold: 0.72,
    time: "12:18",
    title: "回答回到证据",
    copy: "提问后能跳回原视频片段。",
  },
] as const;

const PROGRESS_POINTS = [
  { value: 0.18, label: "导入", time: "00:04" },
  { value: 0.36, label: "章节", time: "03:11" },
  { value: 0.58, label: "重点", time: "08:42" },
  { value: 0.76, label: "问答", time: "12:18" },
] as const;

function resolvePhase(value: number) {
  return getFoldPhase(clampFoldProgress(value));
}

export function FoldingHeroStage() {
  const shouldReduceMotion = useReducedMotion();
  const stageRef = useRef<HTMLDivElement>(null);
  const lastRangeRef = useRef(72);
  const progress = useMotionValue(0.72);
  const pointerX = useMotionValue(0);
  const pointerY = useMotionValue(0);
  const [rangeValue, setRangeValue] = useState(72);
  const [phase, setPhase] = useState<FoldPhase>("note");

  const playheadLeft = useTransform(progress, [0, 1], ["11%", "89%"]);
  const progressScale = useTransform(progress, [0, 1], [0.04, 1]);
  const filmX = useTransform(progress, [0, 1], ["2%", "-14%"]);
  const foldScale = useTransform(progress, [0, 1], [0.88, 1.06]);
  const noteOpacity = useTransform(progress, [0.16, 0.72], [0.28, 1]);
  const noteX = useTransform(progress, [0, 1], [38, 0]);
  const beamOpacity = useTransform(progress, [0.08, 0.44, 1], [0.16, 0.88, 0.42]);
  const haloX = useTransform(pointerX, [-0.5, 0.5], [-18, 18]);
  const haloY = useTransform(pointerY, [-0.5, 0.5], [-12, 12]);
  const filmParallax = useTransform(pointerX, [-0.5, 0.5], [-7, 7]);
  const paperRotate = useTransform(pointerX, [-0.5, 0.5], [-1.4, 1.4]);

  const setFoldProgress = useCallback(
    (value: number) => {
      progress.set(clampFoldProgress(value));
    },
    [progress],
  );

  const setFromClientX = useCallback(
    (clientX: number) => {
      const rect = stageRef.current?.getBoundingClientRect();
      if (!rect) return;
      setFoldProgress((clientX - rect.left) / rect.width);
    },
    [setFoldProgress],
  );

  const setPointerMotion = useCallback(
    (clientX: number, clientY: number) => {
      const rect = stageRef.current?.getBoundingClientRect();
      if (!rect) return;
      pointerX.set((clientX - rect.left) / rect.width - 0.5);
      pointerY.set((clientY - rect.top) / rect.height - 0.5);
    },
    [pointerX, pointerY],
  );

  useMotionValueEvent(progress, "change", (latest) => {
    const nextRange = Math.round(clampFoldProgress(latest) * 100);
    if (nextRange !== lastRangeRef.current) {
      lastRangeRef.current = nextRange;
      setRangeValue(nextRange);
    }

    const nextPhase = resolvePhase(latest);
    setPhase((current) => (current === nextPhase ? current : nextPhase));
  });

  useEffect(() => {
    if (shouldReduceMotion) return;

    const controls = animate(progress, [0.08, 0.34, 0.58, 0.76, 0.72], {
      duration: 4.2,
      ease: [0.16, 1, 0.3, 1],
      times: [0, 0.28, 0.56, 0.82, 1],
    });

    return () => controls.stop();
  }, [progress, shouldReduceMotion]);

  return (
    <section
      className="relative mx-auto w-full max-w-2xl"
      aria-label="可交互的视频折叠成笔记演示"
      data-phase={phase}
    >
      <motion.div
        aria-hidden="true"
        className="absolute -left-8 top-10 hidden h-40 w-40 rounded-full bg-[var(--wf-brand-coral)] opacity-15 blur-3xl md:block"
        style={shouldReduceMotion ? undefined : { x: haloX, y: haloY }}
      />
      <div
        ref={stageRef}
        className="group relative min-h-[31rem] overflow-hidden rounded-[2rem] border border-white/10 bg-[#1f1814] p-4 text-[#fff7ed] shadow-[0_24px_80px_rgba(55,36,24,.28),inset_0_1px_0_rgba(255,245,230,.08)] md:p-5"
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          setPointerMotion(event.clientX, event.clientY);
          setFromClientX(event.clientX);
        }}
        onPointerMove={(event) => {
          setPointerMotion(event.clientX, event.clientY);
          if (event.pointerType !== "touch") setFromClientX(event.clientX);
        }}
        onPointerLeave={() => {
          pointerX.set(0);
          pointerY.set(0);
        }}
      >
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18%_15%,rgba(228,123,89,.25),transparent_34%),radial-gradient(circle_at_80%_82%,rgba(211,161,115,.16),transparent_32%),linear-gradient(135deg,rgba(255,250,243,.08),transparent_42%)]" />
        <div className="pointer-events-none absolute inset-x-6 top-6 h-px bg-gradient-to-r from-transparent via-white/18 to-transparent" />
        <motion.div
          aria-hidden="true"
          className="pointer-events-none absolute left-8 right-8 top-1/2 h-px bg-[#fff7ed]/14"
          style={{ opacity: beamOpacity }}
        />
        <motion.div
          aria-hidden="true"
          className="pointer-events-none absolute top-[16%] bottom-[17%] z-20 w-px bg-[var(--wf-brand-coral)] shadow-[0_0_24px_rgba(228,123,89,.72)]"
          style={{ left: playheadLeft }}
        >
          <span className="absolute -left-3 -top-3 flex h-6 w-6 items-center justify-center rounded-full border border-[#ffb28f]/70 bg-[#2a1710] text-[#ffb28f]">
            <Play size={10} fill="currentColor" aria-hidden="true" />
          </span>
          <span className="absolute -bottom-3 -left-2 h-4 w-4 rotate-45 rounded-[0.2rem] bg-[var(--wf-brand-coral)]" />
        </motion.div>

        <div className="relative z-10 flex flex-wrap items-center justify-between gap-3">
          <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/10 px-3 py-1 text-xs font-medium text-[#ffcfb7]">
            <MousePointer2 size={13} aria-hidden="true" />
            悬停或拖动时间指针
          </span>
          <span className="rounded-full border border-white/10 bg-white/10 px-3 py-1 text-xs tabular-nums text-[#d8c8ba]">
            {PHASE_LABEL[phase]}
          </span>
        </div>

        <div className="relative z-10 mt-6 grid min-h-[21rem] gap-5 md:grid-cols-[0.88fr_0.14fr_1fr] md:items-center">
          <motion.div
            className="relative overflow-hidden rounded-[1.45rem] border border-white/10 bg-black/30 p-3 shadow-[0_20px_60px_rgba(0,0,0,.28)]"
            style={shouldReduceMotion ? { x: filmX } : { x: filmX, translateX: filmParallax }}
          >
            <div className="mb-3 flex items-center justify-between text-xs text-[#d8c8ba]">
              <span className="inline-flex items-center gap-1.5">
                <Film size={14} aria-hidden="true" />
                Video strip
              </span>
              <span className="tabular-nums">16:42</span>
            </div>
            <div className="relative overflow-hidden rounded-[1.1rem] border border-white/10 bg-[#120f0d] p-3">
              <div className="pointer-events-none absolute inset-y-2 left-2 flex flex-col justify-between">
                {Array.from({ length: 7 }).map((_, index) => (
                  <span key={index} className="h-2 w-1.5 rounded-sm bg-white/16" />
                ))}
              </div>
              <div className="pointer-events-none absolute inset-y-2 right-2 flex flex-col justify-between">
                {Array.from({ length: 7 }).map((_, index) => (
                  <span key={index} className="h-2 w-1.5 rounded-sm bg-white/16" />
                ))}
              </div>
              <div className="grid gap-2 px-4">
                {FILM_FRAMES.map((frame, index) => {
                  const active = rangeValue >= PROGRESS_POINTS[Math.min(index, PROGRESS_POINTS.length - 1)].value * 100;
                  return (
                    <button
                      key={frame.time}
                      type="button"
                      className={clsx(
                        "relative h-14 overflow-hidden rounded-xl border px-3 text-left transition duration-300 ease-out focus:outline-none focus-visible:ring-2 focus-visible:ring-[#ffb28f]",
                        active
                          ? "border-[#ffb28f]/42 bg-[linear-gradient(135deg,rgba(255,247,237,.22),rgba(228,123,89,.16)),#2a1d17]"
                          : "border-white/10 bg-[linear-gradient(135deg,rgba(255,247,237,.10),rgba(228,123,89,.05)),#211a16]",
                      )}
                      onFocus={() => setFoldProgress(PROGRESS_POINTS[Math.min(index, PROGRESS_POINTS.length - 1)].value)}
                      onMouseEnter={() => setFoldProgress(PROGRESS_POINTS[Math.min(index, PROGRESS_POINTS.length - 1)].value)}
                    >
                      <span className="block text-[10px] font-semibold tabular-nums text-[#ffb28f]">{frame.time}</span>
                      <span className="mt-1 block text-xs text-[#e4d1c1]">{frame.label}</span>
                      <span className="absolute bottom-3 right-3 h-1.5 w-[42%] rounded-full bg-white/12" />
                      {active ? <span className="absolute right-3 top-3 h-2 w-2 rounded-full bg-[#ffb28f] shadow-[0_0_14px_rgba(255,178,143,.7)]" /> : null}
                    </button>
                  );
                })}
              </div>
            </div>
          </motion.div>

          <motion.div
            aria-hidden="true"
            className="mx-auto hidden h-36 w-12 items-center justify-center md:flex"
            style={{ scale: foldScale }}
          >
            <span className="h-full w-px bg-gradient-to-b from-transparent via-[#ffb28f] to-transparent" />
            <span className="absolute h-16 w-16 rounded-full border border-[#ffb28f]/35 bg-[#ffb28f]/10 blur-[1px]" />
            <Sparkles size={16} className="absolute text-[#ffb28f]" />
          </motion.div>

          <motion.div
            className="relative min-h-[20rem]"
            style={shouldReduceMotion ? { opacity: noteOpacity, x: noteX } : { opacity: noteOpacity, x: noteX, rotate: paperRotate }}
          >
            {NOTE_CARDS.map((card, index) => {
              const active = rangeValue / 100 >= card.threshold;
              return (
                <motion.article
                  key={card.time}
                  className={clsx(
                    "absolute left-0 right-0 rounded-[1.35rem] border p-4 text-[#2d2925] shadow-[0_20px_48px_rgba(0,0,0,.22)] transition duration-300 ease-out",
                    active
                      ? "border-[rgba(182,92,58,.30)] bg-[#fff7ed]"
                      : "border-[rgba(45,41,37,.10)] bg-[#f3e7d8]",
                  )}
                  animate={
                    shouldReduceMotion
                      ? undefined
                      : {
                          y: active ? -4 : 10,
                          scale: active ? 1 : 0.965,
                          opacity: active ? 1 : 0.58,
                        }
                  }
                  transition={{ duration: 0.34, ease: [0.16, 1, 0.3, 1] }}
                  style={{
                    top: `${index * 5.2}rem`,
                    rotate: `${index === 0 ? -2 : index === 1 ? 1.4 : 3}deg`,
                    transformOrigin: "12% 50%",
                    zIndex: active ? 8 + index : index,
                  }}
                >
                  <div className="absolute right-0 top-0 h-12 w-12 rounded-bl-[1rem] rounded-tr-[1.35rem] bg-[rgba(211,161,115,.22)]" />
                  <div className="relative flex items-center justify-between gap-3">
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-[rgba(182,92,58,.12)] px-2.5 py-1 text-xs font-semibold tabular-nums text-[var(--wf-accent)]">
                      <FileText size={12} aria-hidden="true" />
                      {card.time}
                    </span>
                    <span className="h-1.5 w-12 rounded-full bg-[rgba(182,92,58,.18)]" />
                  </div>
                  <h3 className="relative mt-3 text-base font-semibold tracking-[-0.02em]">{card.title}</h3>
                  <p className="relative mt-2 text-sm leading-6 text-[#665d55]">{card.copy}</p>
                </motion.article>
              );
            })}
          </motion.div>
        </div>

        <div className="relative z-10 mt-7 rounded-[1.25rem] border border-white/10 bg-white/[0.075] p-4">
          <label className="flex items-center justify-between gap-3 text-xs text-[#d8c8ba]" htmlFor="fold-progress">
            <span>视频折叠进度</span>
            <span className="tabular-nums text-[#ffb28f]">{rangeValue}%</span>
          </label>
          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/12">
            <motion.div className="h-full origin-left rounded-full bg-[var(--wf-brand-coral)]" style={{ scaleX: progressScale }} />
          </div>
          <div className="mt-3 hidden grid-cols-4 gap-2 2xl:grid">
            {PROGRESS_POINTS.map((point) => (
              <button
                key={point.time}
                type="button"
                className="rounded-xl border border-white/10 bg-white/[0.06] px-2 py-2 text-left text-[10px] text-[#d8c8ba] transition hover:border-[#ffb28f]/50 hover:bg-white/[0.11] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#ffb28f]"
                onClick={() => setFoldProgress(point.value)}
              >
                <span className="block font-semibold tabular-nums text-[#ffb28f]">{point.time}</span>
                <span>{point.label}</span>
              </button>
            ))}
          </div>
          <input
            id="fold-progress"
            type="range"
            min={0}
            max={100}
            value={rangeValue}
            onChange={(event) => setFoldProgress(Number(event.target.value) / 100)}
            className="wf-fold-range sr-only"
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
