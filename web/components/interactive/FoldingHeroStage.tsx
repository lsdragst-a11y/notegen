"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
} from "react";
import {
  animate,
  motion,
  useMotionValue,
  useMotionValueEvent,
  useReducedMotion,
  useTransform,
} from "framer-motion";

import { clampFoldProgress, getFoldPhase, type FoldPhase } from "./motionModel";
import {
  FilmTimelineRail,
  FoldingNoteSheet,
  PaperWorkbenchSurface,
  PlayheadBeam,
} from "./NoteGenMotionPrimitives";

const FINAL_PROGRESS = 0.78;
const INITIAL_PROGRESS = 0.08;
const KEYBOARD_STEP = 0.04;

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
  const initialProgress = reduceMotion ? FINAL_PROGRESS : INITIAL_PROGRESS;
  const stageRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);
  const controlsRef = useRef<{ stop: () => void } | null>(null);
  const lastRangeRef = useRef(Math.round(initialProgress * 100));
  const progress = useMotionValue(initialProgress);
  const pointerX = useMotionValue(0);
  const pointerY = useMotionValue(0);
  const [rangeValue, setRangeValue] = useState(Math.round(initialProgress * 100));
  const [phase, setPhase] = useState<FoldPhase>(() => resolvePhase(initialProgress));
  const [interactionMode, setInteractionMode] = useState<InteractionMode>("autoPlay");

  const playheadLeft = useTransform(progress, [0, 1], ["8%", "92%"]);
  const paperX = useTransform(progress, [0, 1], [52, 0]);
  const paperRotate = useTransform(pointerX, [-0.5, 0.5], [-1.4, 1.4]);
  const haloX = useTransform(pointerX, [-0.5, 0.5], [-18, 18]);
  const haloY = useTransform(pointerY, [-0.5, 0.5], [-10, 10]);
  const activeFrameIndex = useMemo(() => closestFrameIndex(rangeValue / 100), [rangeValue]);
  const mobileNote = useMemo(() => {
    const currentProgress = rangeValue / 100;
    return NOTE_CARDS.reduce(
      (current, card) => (currentProgress >= card.threshold ? card : current),
      NOTE_CARDS[0],
    );
  }, [rangeValue]);

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

  const scrubWithKeyboard = useCallback(
    (event: KeyboardEvent<HTMLInputElement>) => {
      const keyProgress = lastRangeRef.current / 100;
      let nextProgress: number | null = null;

      switch (event.key) {
        case "ArrowLeft":
        case "ArrowDown":
          nextProgress = keyProgress - KEYBOARD_STEP;
          break;
        case "ArrowRight":
        case "ArrowUp":
          nextProgress = keyProgress + KEYBOARD_STEP;
          break;
        case "Home":
          nextProgress = 0;
          break;
        case "End":
          nextProgress = 1;
          break;
        default:
          return;
      }

      event.preventDefault();
      stopAutoplay();
      setInteractionMode(reduceMotion ? "reducedMotion" : "dragScrub");
      setFoldProgress(nextProgress);
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
      className="wf-hero-fold-stage relative mx-auto h-[42rem] w-full max-w-7xl overflow-visible"
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
      <PaperWorkbenchSurface className="absolute inset-0" variant="hero">
        <motion.div
          aria-hidden="true"
          className="wf-hero-stage-halo"
          style={reduceMotion ? undefined : { x: haloX, y: haloY }}
        />

        <div className="wf-hero-film-plane">
          <FilmTimelineRail
            frames={FILM_FRAMES}
            activeIndex={activeFrameIndex}
            onFrameClick={(index) => setFrameProgress(FILM_FRAMES[index].value)}
            onFrameFocus={(index) => setFrameProgress(FILM_FRAMES[index].value)}
            onFrameHover={(index) => setFrameProgress(FILM_FRAMES[index].value)}
          />
        </div>

        <PlayheadBeam
          left={playheadLeft}
          onPointerDown={beginDrag}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          aria-hidden="true"
        />

        <motion.div
          className="wf-hero-note-cluster"
          style={reduceMotion ? { x: 0 } : { x: paperX, rotate: paperRotate }}
        >
          {NOTE_CARDS.map((card, index) => {
            const active = rangeValue / 100 >= card.threshold;
            return (
              <FoldingNoteSheet
                key={card.time}
                time={card.time}
                title={card.title}
                active={active}
                testId={`fold-note-${card.time}`}
                animate={
                  reduceMotion
                    ? undefined
                    : {
                        y: active ? -10 : 10,
                        opacity: active ? 1 : 0.58,
                        scale: active ? 1 : 0.955,
                      }
                }
                style={{
                  top: `${index * 5.55}rem`,
                  rotate: `${index === 0 ? -5 : index === 1 ? 1.2 : 5}deg`,
                  zIndex: active ? 10 + index : index,
                }}
              >
                {card.copy}
              </FoldingNoteSheet>
            );
          })}
        </motion.div>

        <motion.div
          className="wf-hero-mobile-note"
          style={reduceMotion ? undefined : { x: paperX }}
        >
          <FoldingNoteSheet
            time={mobileNote.time}
            title={mobileNote.title}
            active
            testId={`fold-mobile-note-${mobileNote.time}`}
          >
            {mobileNote.copy}
          </FoldingNoteSheet>
        </motion.div>
      </PaperWorkbenchSurface>

      <input
        id="fold-progress"
        type="range"
        min={0}
        max={100}
        value={rangeValue}
        aria-label="调整视频折叠进度"
        aria-valuetext={PHASE_LABEL[phase]}
        onKeyDown={scrubWithKeyboard}
        onFocus={() => {
          stopAutoplay();
          setInteractionMode(reduceMotion ? "reducedMotion" : "dragScrub");
        }}
        onChange={(event) => {
          stopAutoplay();
          setInteractionMode(reduceMotion ? "reducedMotion" : "dragScrub");
          setFoldProgress(Number(event.target.value) / 100);
        }}
        className="wf-fold-range sr-only"
      />
      <p className="sr-only" aria-live="polite">
        当前演示阶段：{PHASE_LABEL[phase]}
      </p>
    </section>
  );
}
