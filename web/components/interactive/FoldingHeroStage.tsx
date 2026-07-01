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
import { FileText, MousePointer2, Play } from "lucide-react";

import { clampFoldProgress, getFoldPhase, type FoldPhase } from "./motionModel";

const PHASE_LABEL: Record<FoldPhase, string> = {
  import: "正在识别章节",
  fold: "正在提取重点",
  note: "已生成回看笔记",
};

const FILM_FRAMES = [
  { time: "00:04", label: "导入", tone: "from-[#38231b] to-[#1b1411]" },
  { time: "03:11", label: "章节", tone: "from-[#553023] to-[#211713]" },
  { time: "08:42", label: "重点", tone: "from-[#4a2b1f] to-[#1b1411]" },
  { time: "12:18", label: "问答", tone: "from-[#39251d] to-[#17110f]" },
] as const;

const NOTE_CARDS = [
  {
    threshold: 0.34,
    time: "03:11",
    title: "章节自动展开",
    copy: "长视频被切成可复习段落。",
  },
  {
    threshold: 0.56,
    time: "08:42",
    title: "重点折进纸页",
    copy: "关键概念和摘要保留时间戳。",
  },
  {
    threshold: 0.74,
    time: "12:18",
    title: "答案回到证据",
    copy: "提问后跳回原视频片段。",
  },
] as const;

const PROGRESS_POINTS = [
  { value: 0.18, label: "Import", time: "00:04" },
  { value: 0.36, label: "Chapter", time: "03:11" },
  { value: 0.58, label: "Notes", time: "08:42" },
  { value: 0.76, label: "Replay", time: "12:18" },
] as const;

function resolvePhase(value: number) {
  return getFoldPhase(clampFoldProgress(value));
}

export function FoldingHeroStage() {
  const reduceMotion = useReducedMotion();
  const stageRef = useRef<HTMLDivElement>(null);
  const lastRangeRef = useRef(72);
  const progress = useMotionValue(0.72);
  const pointerX = useMotionValue(0);
  const pointerY = useMotionValue(0);
  const [rangeValue, setRangeValue] = useState(72);
  const [phase, setPhase] = useState<FoldPhase>("note");

  const playheadLeft = useTransform(progress, [0, 1], ["8%", "92%"]);
  const filmX = useTransform(progress, [0, 1], [18, -44]);
  const paperX = useTransform(progress, [0, 1], [44, 0]);
  const paperRotate = useTransform(pointerX, [-0.5, 0.5], [-1.8, 1.8]);
  const haloX = useTransform(pointerX, [-0.5, 0.5], [-18, 18]);
  const haloY = useTransform(pointerY, [-0.5, 0.5], [-12, 12]);
  const progressScale = useTransform(progress, [0, 1], [0.06, 1]);

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
    if (reduceMotion) return;

    const controls = animate(progress, [0.1, 0.36, 0.58, 0.78, 0.72], {
      duration: 4.4,
      ease: [0.16, 1, 0.3, 1],
      times: [0, 0.28, 0.56, 0.82, 1],
    });

    return () => controls.stop();
  }, [progress, reduceMotion]);

  return (
    <section
      ref={stageRef}
      className="relative mx-auto h-[32rem] w-full max-w-[50rem] overflow-visible"
      aria-label="可交互的视频折叠成笔记演示"
      data-phase={phase}
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
      <motion.div
        aria-hidden="true"
        className="absolute -inset-x-10 top-10 h-80 rounded-full bg-[radial-gradient(circle_at_50%_50%,rgba(228,123,89,.22),rgba(63,38,25,.20)_35%,transparent_72%)] blur-2xl"
        style={reduceMotion ? undefined : { x: haloX, y: haloY }}
      />

      <div className="absolute left-2 right-2 top-[13.5rem] h-28 rounded-[999px] border border-[rgba(255,238,220,.10)] bg-[#211812] shadow-[0_30px_90px_rgba(55,36,24,.34),inset_0_1px_0_rgba(255,245,230,.08)]" />
      <div className="absolute left-8 right-8 top-[16.65rem] h-px bg-gradient-to-r from-transparent via-[#ffb28f]/60 to-transparent" />

      <motion.div
        aria-hidden="true"
        className="absolute top-[6rem] bottom-[3.2rem] z-30 w-px bg-[var(--wf-brand-coral)] shadow-[0_0_28px_rgba(228,123,89,.68)]"
        style={{ left: playheadLeft }}
      >
        <span className="absolute -left-3 -top-3 flex h-7 w-7 items-center justify-center rounded-full border border-[#ffb28f]/70 bg-[#2a1710] text-[#ffb28f] shadow-[0_12px_28px_rgba(0,0,0,.24)]">
          <Play size={11} fill="currentColor" aria-hidden="true" />
        </span>
        <span className="absolute -bottom-2 -left-2 h-4 w-4 rotate-45 rounded-[0.2rem] bg-[var(--wf-brand-coral)]" />
      </motion.div>

      <div className="absolute left-3 top-5 z-20 flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-2 rounded-full border border-[rgba(255,238,220,.12)] bg-[#241a15]/82 px-3 py-1 text-xs font-medium text-[#ffcfb7] shadow-[0_12px_28px_rgba(0,0,0,.18)] backdrop-blur">
          <MousePointer2 size={13} aria-hidden="true" />
          悬停时间点
        </span>
        <span className="rounded-full border border-[rgba(255,238,220,.12)] bg-[#241a15]/82 px-3 py-1 text-xs tabular-nums text-[#d8c8ba] shadow-[0_12px_28px_rgba(0,0,0,.18)] backdrop-blur">
          {PHASE_LABEL[phase]}
        </span>
      </div>

      <motion.div
        className="absolute left-0 right-[16rem] top-[10.4rem] z-20 overflow-visible"
        style={reduceMotion ? undefined : { x: filmX }}
      >
        <div className="relative h-32 rounded-[1.35rem] border border-white/10 bg-[#14100e] p-3 shadow-[0_24px_70px_rgba(0,0,0,.32)]">
          <div className="absolute inset-y-3 left-3 flex flex-col justify-between">
            {Array.from({ length: 5 }).map((_, index) => (
              <span key={index} className="h-2.5 w-2 rounded-sm bg-white/18" />
            ))}
          </div>
          <div className="absolute inset-y-3 right-3 flex flex-col justify-between">
            {Array.from({ length: 5 }).map((_, index) => (
              <span key={index} className="h-2.5 w-2 rounded-sm bg-white/18" />
            ))}
          </div>
          <div className="ml-8 mr-8 grid h-full grid-cols-4 gap-2">
            {FILM_FRAMES.map((frame, index) => {
              const active = rangeValue >= PROGRESS_POINTS[index].value * 100;
              return (
                <button
                  key={frame.time}
                  type="button"
                  className={clsx(
                    "relative overflow-hidden rounded-[1rem] border p-3 text-left transition duration-300 ease-out focus:outline-none focus-visible:ring-2 focus-visible:ring-[#ffb28f]",
                    active ? "border-[#ffb28f]/45" : "border-white/10",
                  )}
                  onFocus={() => setFoldProgress(PROGRESS_POINTS[index].value)}
                  onMouseEnter={() => setFoldProgress(PROGRESS_POINTS[index].value)}
                >
                  <span className={clsx("absolute inset-0 bg-gradient-to-br opacity-95", frame.tone)} />
                  <span className="absolute inset-x-3 top-9 h-8 rounded-lg bg-white/10" />
                  <span className="relative block font-mono text-[10px] font-semibold tabular-nums text-[#ffb28f]">
                    {frame.time}
                  </span>
                  <span className="relative mt-12 block text-xs text-[#efe0d2]">{frame.label}</span>
                  {active ? <span className="absolute right-3 top-3 h-2 w-2 rounded-full bg-[#ffb28f] shadow-[0_0_14px_rgba(255,178,143,.72)]" /> : null}
                </button>
              );
            })}
          </div>
        </div>
      </motion.div>

      <motion.div
        className="absolute right-0 top-[5rem] z-20 h-[22rem] w-[19.5rem]"
        style={reduceMotion ? { x: paperX } : { x: paperX, rotate: paperRotate }}
      >
        {NOTE_CARDS.map((card, index) => {
          const active = rangeValue / 100 >= card.threshold;
          return (
            <motion.article
              key={card.time}
              className={clsx(
                "absolute left-0 right-0 rounded-[1.25rem] border p-4 text-[#2d2925] shadow-[0_20px_54px_rgba(35,22,15,.22)] transition duration-300 ease-out",
                active ? "border-[rgba(182,92,58,.28)] bg-[#fff8ec]" : "border-[rgba(45,41,37,.10)] bg-[#f2e4d3]",
              )}
              animate={
                reduceMotion
                  ? undefined
                  : {
                      y: active ? -8 : 8,
                      opacity: active ? 1 : 0.62,
                      scale: active ? 1 : 0.965,
                    }
              }
              transition={{ duration: 0.34, ease: [0.16, 1, 0.3, 1] }}
              style={{
                top: `${index * 5.9}rem`,
                rotate: `${index === 0 ? -3 : index === 1 ? 1.5 : 4}deg`,
                zIndex: active ? 10 + index : index,
              }}
            >
              <div className="absolute right-0 top-0 h-14 w-14 rounded-bl-[1rem] rounded-tr-[1.25rem] bg-[linear-gradient(135deg,rgba(211,161,115,.28),rgba(255,250,243,.62))]" />
              <div className="absolute left-0 top-4 h-[calc(100%-2rem)] w-1 rounded-r-full bg-[rgba(182,92,58,.28)]" />
              <div className="relative flex items-center justify-between">
                <span className="inline-flex items-center gap-1.5 rounded-full bg-[rgba(182,92,58,.12)] px-2.5 py-1 font-mono text-[10px] font-semibold tabular-nums text-[var(--wf-accent)]">
                  <FileText size={12} aria-hidden="true" />
                  {card.time}
                </span>
                <span className="h-1.5 w-12 rounded-full bg-[rgba(182,92,58,.16)]" />
              </div>
              <h3 className="relative mt-3 text-base font-semibold tracking-[-0.02em]">{card.title}</h3>
              <p className="relative mt-2 text-sm leading-6 text-[#665d55]">{card.copy}</p>
            </motion.article>
          );
        })}
      </motion.div>

      <div className="absolute bottom-7 left-7 right-7 z-20 rounded-[1.2rem] border border-[rgba(255,238,220,.12)] bg-[#241a15]/86 p-4 text-[#fff7ed] shadow-[0_18px_50px_rgba(0,0,0,.22)] backdrop-blur">
        <div className="flex items-center justify-between gap-3 text-xs text-[#d8c8ba]">
          <span>视频折叠进度</span>
          <span className="font-mono tabular-nums text-[#ffb28f]">{rangeValue}%</span>
        </div>
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/12">
          <motion.div className="h-full origin-left rounded-full bg-[var(--wf-brand-coral)]" style={{ scaleX: progressScale }} />
        </div>
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
      <p className="sr-only" aria-live="polite">
        当前演示阶段：{PHASE_LABEL[phase]}
      </p>
    </section>
  );
}
