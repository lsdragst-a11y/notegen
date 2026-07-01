"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
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

const FINAL_PROGRESS = 0.78;

const PHASE_LABEL: Record<FoldPhase, string> = {
  import: "正在识别章节",
  fold: "正在提取重点",
  note: "已生成回看笔记",
};

const FILM_FRAMES = [
  { value: 0.18, time: "00:04", label: "导入视频", phase: "import" },
  { value: 0.36, time: "03:11", label: "章节展开", phase: "fold" },
  { value: 0.58, time: "08:42", label: "重点折页", phase: "fold" },
  { value: 0.76, time: "12:18", label: "证据回放", phase: "note" },
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

type InteractionMode = "autoPlay" | "hoverFrame" | "dragScrub" | "reducedMotion";

function resolvePhase(value: number) {
  return getFoldPhase(clampFoldProgress(value));
}

function closestFrameIndex(value: number) {
  let bestIndex = 0;
  let bestDistance = Number.POSITIVE_INFINITY;

  FILM_FRAMES.forEach((frame, index) => {
    const distance = Math.abs(frame.value - value);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  });

  return bestIndex;
}

export function FoldingHeroStage() {
  const reduceMotion = useReducedMotion();
  const stageRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);
  const controlsRef = useRef<{ stop: () => void } | null>(null);
  const lastRangeRef = useRef(Math.round(FINAL_PROGRESS * 100));
  const progress = useMotionValue(FINAL_PROGRESS);
  const pointerX = useMotionValue(0);
  const pointerY = useMotionValue(0);
  const [rangeValue, setRangeValue] = useState(Math.round(FINAL_PROGRESS * 100));
  const [phase, setPhase] = useState<FoldPhase>("note");
  const [interactionMode, setInteractionMode] = useState<InteractionMode>("autoPlay");

  const playheadLeft = useTransform(progress, [0, 1], ["6%", "94%"]);
  const paperX = useTransform(progress, [0, 1], [52, 0]);
  const paperRotate = useTransform(pointerX, [-0.5, 0.5], [-1.4, 1.4]);
  const haloX = useTransform(pointerX, [-0.5, 0.5], [-18, 18]);
  const haloY = useTransform(pointerY, [-0.5, 0.5], [-10, 10]);
  const progressScale = useTransform(progress, [0, 1], [0.06, 1]);
  const activeFrameIndex = useMemo(() => closestFrameIndex(rangeValue / 100), [rangeValue]);

  const stopAutoplay = useCallback(() => {
    controlsRef.current?.stop();
    controlsRef.current = null;
  }, []);

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

  const setFrameProgress = useCallback(
    (value: number) => {
      stopAutoplay();
      setInteractionMode(reduceMotion ? "reducedMotion" : "hoverFrame");
      setFoldProgress(value);
    },
    [reduceMotion, setFoldProgress, stopAutoplay],
  );

  const beginDrag = useCallback(
    (event: PointerEvent<HTMLElement>) => {
      stopAutoplay();
      draggingRef.current = true;
      setInteractionMode("dragScrub");
      event.currentTarget.setPointerCapture(event.pointerId);
      setPointerMotion(event.clientX, event.clientY);
      setFromClientX(event.clientX);
    },
    [setFromClientX, setPointerMotion, stopAutoplay],
  );

  const endDrag = useCallback((event: PointerEvent<HTMLElement>) => {
    draggingRef.current = false;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }, []);

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
    if (reduceMotion) {
      stopAutoplay();
      setFoldProgress(FINAL_PROGRESS);
      return;
    }

    controlsRef.current = animate(progress, [0.08, 0.28, 0.46, 0.62, FINAL_PROGRESS], {
      duration: 4.6,
      ease: [0.16, 1, 0.3, 1],
      times: [0, 0.25, 0.52, 0.76, 1],
    });

    return () => {
      controlsRef.current?.stop();
      controlsRef.current = null;
    };
  }, [progress, reduceMotion, setFoldProgress, stopAutoplay]);

  return (
    <section
      ref={stageRef}
      className="relative mx-auto h-[34rem] w-full max-w-7xl overflow-visible"
      aria-label="可交互的视频折叠成笔记演示"
      data-phase={phase}
      data-mode={reduceMotion ? "reducedMotion" : interactionMode}
      onPointerMove={(event) => {
        setPointerMotion(event.clientX, event.clientY);
        if (draggingRef.current) setFromClientX(event.clientX);
      }}
      onPointerLeave={() => {
        pointerX.set(0);
        pointerY.set(0);
      }}
    >
      <motion.div
        aria-hidden="true"
        className="absolute -inset-x-10 top-10 h-80 rounded-full bg-[radial-gradient(circle_at_50%_50%,color-mix(in_srgb,var(--wf-warm-glow)_28%,transparent),color-mix(in_srgb,var(--wf-cinema-bg)_18%,transparent)_38%,transparent_72%)] blur-2xl"
        style={reduceMotion ? undefined : { x: haloX, y: haloY }}
      />

      <div className="absolute left-[3%] right-[3%] top-[15rem] h-28 rounded-[999px] border border-[var(--wf-cinema-border)] bg-[var(--wf-cinema-bg)] shadow-[0_30px_90px_color-mix(in_srgb,var(--wf-cinema-bg)_42%,transparent),inset_0_1px_0_color-mix(in_srgb,var(--wf-paper-front)_12%,transparent)]" />
      <div className="absolute left-[6%] right-[6%] top-[18.15rem] h-px bg-gradient-to-r from-transparent via-[var(--wf-cinema-line)] to-transparent" />

      <motion.div
        className="absolute top-[7rem] bottom-[3.4rem] z-30 w-px cursor-ew-resize bg-[var(--wf-playhead)] shadow-[0_0_28px_color-mix(in_srgb,var(--wf-playhead)_68%,transparent)]"
        style={{ left: playheadLeft }}
        onPointerDown={beginDrag}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        role="slider"
        aria-label="拖动播放指针调整视频折叠进度"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={rangeValue}
        tabIndex={0}
      >
        <span className="absolute -left-3 -top-3 flex h-7 w-7 items-center justify-center rounded-full border border-[color-mix(in_srgb,var(--wf-playhead)_58%,var(--wf-paper-front))] bg-[var(--wf-cinema-panel)] text-[var(--wf-timecode)] shadow-[0_12px_28px_color-mix(in_srgb,var(--wf-cinema-bg)_34%,transparent)]">
          <Play size={11} fill="currentColor" aria-hidden="true" />
        </span>
        <span className="absolute -bottom-2 -left-2 h-4 w-4 rotate-45 rounded-[0.2rem] bg-[var(--wf-playhead)]" />
      </motion.div>

      <div className="absolute left-3 top-5 z-20 flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-2 rounded-full border border-[var(--wf-cinema-border)] bg-[color-mix(in_srgb,var(--wf-cinema-panel)_88%,transparent)] px-3 py-1 text-xs font-medium text-[var(--wf-cinema-text)] shadow-[0_12px_28px_color-mix(in_srgb,var(--wf-cinema-bg)_18%,transparent)] backdrop-blur">
          <MousePointer2 size={13} aria-hidden="true" />
          悬停时间点
        </span>
        <span className="rounded-full border border-[var(--wf-cinema-border)] bg-[color-mix(in_srgb,var(--wf-cinema-panel)_88%,transparent)] px-3 py-1 text-xs tabular-nums text-[var(--wf-cinema-muted)] shadow-[0_12px_28px_color-mix(in_srgb,var(--wf-cinema-bg)_18%,transparent)] backdrop-blur">
          {PHASE_LABEL[phase]}
        </span>
      </div>

      <div className="absolute left-[2%] right-[22rem] top-[11.8rem] z-20 overflow-visible max-lg:right-[2%]">
        <div className="relative h-36 rounded-[1.5rem] border border-[var(--wf-cinema-border)] bg-[var(--wf-cinema-panel)] p-3 shadow-[0_24px_70px_color-mix(in_srgb,var(--wf-cinema-bg)_38%,transparent)]">
          <div className="absolute inset-y-3 left-3 flex flex-col justify-between">
            {Array.from({ length: 5 }).map((_, index) => (
              <span key={index} className="h-2.5 w-2 rounded-sm bg-[color-mix(in_srgb,var(--wf-paper-front)_18%,transparent)]" />
            ))}
          </div>
          <div className="absolute inset-y-3 right-3 flex flex-col justify-between">
            {Array.from({ length: 5 }).map((_, index) => (
              <span key={index} className="h-2.5 w-2 rounded-sm bg-[color-mix(in_srgb,var(--wf-paper-front)_18%,transparent)]" />
            ))}
          </div>
          <div className="ml-8 mr-8 grid h-full grid-cols-4 gap-2">
            {FILM_FRAMES.map((frame, index) => {
              const active = index === activeFrameIndex;
              return (
                <button
                  key={frame.time}
                  type="button"
                  aria-label={`跳到 ${frame.time}，${frame.label}`}
                  aria-pressed={active}
                  data-testid={`fold-frame-${frame.time}`}
                  className={clsx(
                    "relative overflow-hidden rounded-[1rem] border p-3 text-left transition duration-300 ease-out focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--wf-playhead)]",
                    active ? "border-[var(--wf-playhead)]" : "border-[var(--wf-cinema-border)]",
                  )}
                  onFocus={() => setFrameProgress(frame.value)}
                  onMouseEnter={() => setFrameProgress(frame.value)}
                >
                  <span className="absolute inset-0 bg-[linear-gradient(135deg,color-mix(in_srgb,var(--wf-film-frame)_88%,transparent),var(--wf-cinema-bg))]" />
                  <span className="absolute inset-x-3 top-9 h-8 rounded-lg bg-[color-mix(in_srgb,var(--wf-paper-front)_10%,transparent)]" />
                  <span className="relative block font-mono text-[10px] font-semibold tabular-nums text-[var(--wf-timecode)]">
                    {frame.time}
                  </span>
                  <span className="relative mt-12 block text-xs text-[var(--wf-cinema-text)]">{frame.label}</span>
                  {active ? <span className="absolute right-3 top-3 h-2 w-2 rounded-full bg-[var(--wf-timecode)] shadow-[0_0_14px_color-mix(in_srgb,var(--wf-timecode)_72%,transparent)]" /> : null}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <motion.div
        className="absolute right-[2%] top-[5.6rem] z-20 h-[23rem] w-[21rem] max-lg:right-[5%] max-lg:top-[20rem] max-sm:hidden"
        style={reduceMotion ? { x: 0 } : { x: paperX, rotate: paperRotate }}
      >
        {NOTE_CARDS.map((card, index) => {
          const active = rangeValue / 100 >= card.threshold;
          return (
            <motion.article
              key={card.time}
              data-testid={`fold-note-${card.time}`}
              data-active={active ? "true" : "false"}
              className={clsx(
                "absolute left-0 right-0 rounded-[1.25rem] border p-4 text-[var(--wf-text)] shadow-[0_20px_54px_color-mix(in_srgb,var(--wf-cinema-bg)_22%,transparent)] transition duration-300 ease-out",
                active ? "border-[var(--wf-border-strong)] bg-[var(--wf-paper-front)]" : "border-[var(--wf-border)] bg-[var(--wf-paper-back)]",
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
                top: `${index * 6.05}rem`,
                rotate: `${index === 0 ? -3 : index === 1 ? 1.5 : 4}deg`,
                zIndex: active ? 10 + index : index,
              }}
            >
              <div className="absolute right-0 top-0 h-14 w-14 rounded-bl-[1rem] rounded-tr-[1.25rem] bg-[linear-gradient(135deg,color-mix(in_srgb,var(--wf-caramel)_24%,transparent),color-mix(in_srgb,var(--wf-paper-front)_62%,transparent))]" />
              <div className="absolute left-0 top-4 h-[calc(100%-2rem)] w-1 rounded-r-full bg-[color-mix(in_srgb,var(--wf-playhead)_28%,transparent)]" />
              <div className="relative flex items-center justify-between">
                <span className="inline-flex items-center gap-1.5 rounded-full bg-[color-mix(in_srgb,var(--wf-playhead)_12%,var(--wf-paper-front))] px-2.5 py-1 font-mono text-[10px] font-semibold tabular-nums text-[var(--wf-accent)]">
                  <FileText size={12} aria-hidden="true" />
                  {card.time}
                </span>
                <span className="h-1.5 w-12 rounded-full bg-[color-mix(in_srgb,var(--wf-playhead)_16%,transparent)]" />
              </div>
              <h3 className="relative mt-3 text-base font-semibold tracking-[-0.02em]">{card.title}</h3>
              <p className="relative mt-2 text-sm leading-6 text-[var(--wf-text-secondary)]">{card.copy}</p>
            </motion.article>
          );
        })}
      </motion.div>

      <div className="absolute bottom-7 left-[7%] right-[7%] z-20 rounded-[1.2rem] border border-[var(--wf-cinema-border)] bg-[color-mix(in_srgb,var(--wf-cinema-panel)_88%,transparent)] p-4 text-[var(--wf-cinema-text)] shadow-[0_18px_50px_color-mix(in_srgb,var(--wf-cinema-bg)_22%,transparent)] backdrop-blur">
        <div className="flex items-center justify-between gap-3 text-xs text-[var(--wf-cinema-muted)]">
          <span>视频折叠进度</span>
          <span className="font-mono tabular-nums text-[var(--wf-timecode)]">{rangeValue}%</span>
        </div>
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-[color-mix(in_srgb,var(--wf-paper-front)_12%,transparent)]">
          <motion.div className="h-full origin-left rounded-full bg-[var(--wf-playhead)]" style={{ scaleX: progressScale }} />
        </div>
      </div>

      <input
        id="fold-progress"
        type="range"
        min={0}
        max={100}
        value={rangeValue}
        onChange={(event) => {
          stopAutoplay();
          setInteractionMode("dragScrub");
          setFoldProgress(Number(event.target.value) / 100);
        }}
        className="wf-fold-range sr-only"
        aria-valuetext={PHASE_LABEL[phase]}
      />
      <p className="sr-only" aria-live="polite">
        当前演示阶段：{PHASE_LABEL[phase]}
      </p>
    </section>
  );
}
