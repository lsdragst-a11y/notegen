"use client";

import { useRef, useState } from "react";
import {
  motion,
  useMotionValueEvent,
  useReducedMotion,
  useScroll,
  useSpring,
  useTransform,
} from "framer-motion";
import clsx from "clsx";
import { Film, Play } from "lucide-react";

import { CINEMATIC_BEATS } from "@/app/landing-model";

type Beat = (typeof CINEMATIC_BEATS)[number];

const THUMB_ANGLES = ["-rotate-2", "rotate-[1.4deg]", "-rotate-[0.8deg]", "rotate-2"] as const;

function clampIndex(value: number, length: number) {
  return Math.max(0, Math.min(length - 1, value));
}

export function CinematicStoryboard({ beats = CINEMATIC_BEATS }: { beats?: readonly Beat[] }) {
  const sectionRef = useRef<HTMLElement>(null);
  const reduceMotion = useReducedMotion();
  const [activeIndex, setActiveIndex] = useState(0);
  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start 70%", "end 30%"],
  });
  const smoothProgress = useSpring(scrollYProgress, {
    stiffness: 110,
    damping: 30,
    mass: 0.24,
  });
  const scaleY = useTransform(smoothProgress, [0, 1], [0.18, 1]);
  const scrubX = useTransform(smoothProgress, [0, 1], ["8%", "92%"]);
  const visualIndex = reduceMotion ? beats.length - 1 : activeIndex;
  const activeBeat = beats[visualIndex];

  useMotionValueEvent(smoothProgress, "change", (latest) => {
    if (reduceMotion) return;
    const next = clampIndex(Math.round(latest * (beats.length - 1)), beats.length);
    setActiveIndex((current) => (current === next ? current : next));
  });

  return (
    <section
      id="preview"
      ref={sectionRef}
      className="relative overflow-hidden px-5 py-16 sm:px-6 md:py-24"
      aria-labelledby="cinematic-story-title"
    >
      <div className="pointer-events-none absolute inset-x-0 top-28 h-[34rem] bg-[radial-gradient(ellipse_at_28%_28%,color-mix(in_srgb,var(--wf-cinema-bg)_13%,transparent),transparent_42%),radial-gradient(ellipse_at_72%_74%,color-mix(in_srgb,var(--wf-brand-coral)_12%,transparent),transparent_38%)]" />
      <div className="pointer-events-none absolute left-0 right-0 top-[28rem] h-px bg-gradient-to-r from-transparent via-[color-mix(in_srgb,var(--wf-brand-coral)_42%,transparent)] to-transparent" />

      <div className="relative mx-auto max-w-7xl">
        <div className="max-w-3xl">
          <div className="inline-flex items-center gap-2 rounded-full border border-[color-mix(in_srgb,var(--wf-brand-coral)_22%,transparent)] bg-[color-mix(in_srgb,var(--wf-surface)_72%,transparent)] px-3 py-1 text-xs font-semibold text-[var(--wf-accent)] shadow-[0_12px_28px_rgba(92,58,36,.08)] backdrop-blur">
            <Film size={14} aria-hidden="true" />
            Storyboard Cut
          </div>
          <h2
            id="cinematic-story-title"
            className="mt-5 font-[var(--wf-font-display)] text-4xl font-semibold leading-[0.96] tracking-[-0.045em] text-[var(--wf-text)] md:text-6xl"
          >
            像预告片一样
            <span className="block">展开学习过程</span>
          </h2>
          <p className="mt-5 max-w-xl text-sm leading-7 text-[var(--wf-text-secondary)] md:text-base">
            当前镜头放大成主画面，剪辑轨道和缩略胶片同步标记视频如何折成笔记。
          </p>
        </div>

        <div className="relative mt-10 grid gap-8 lg:min-h-[43rem] lg:grid-cols-[minmax(0,0.62fr)_minmax(20rem,0.38fr)] lg:items-start">
          <div className="relative z-10 lg:pt-14">
            <motion.article
              key={activeBeat.id}
              className="relative min-h-[24rem] overflow-hidden rounded-[1.6rem] border border-[color-mix(in_srgb,var(--wf-cinema-border)_86%,transparent)] bg-[linear-gradient(135deg,color-mix(in_srgb,var(--wf-cinema-bg)_96%,transparent),color-mix(in_srgb,var(--wf-film-frame)_82%,transparent))] p-6 text-[var(--wf-cinema-text)] shadow-[0_34px_100px_color-mix(in_srgb,var(--wf-cinema-bg)_32%,transparent)] md:min-h-[29rem] md:p-8 lg:-rotate-1"
              initial={reduceMotion ? false : { opacity: 0.72, y: 18, scale: 0.985 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ duration: 0.38, ease: [0.16, 1, 0.3, 1] }}
            >
              <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_70%_18%,color-mix(in_srgb,var(--wf-timecode)_18%,transparent),transparent_30%),linear-gradient(180deg,color-mix(in_srgb,var(--wf-paper-front)_7%,transparent),transparent_44%)]" />
              <div className="pointer-events-none absolute inset-x-0 top-0 h-9 border-b border-[color-mix(in_srgb,var(--wf-paper-front)_10%,transparent)] bg-[repeating-linear-gradient(90deg,color-mix(in_srgb,var(--wf-paper-front)_16%,transparent)_0_0.55rem,transparent_0.55rem_1.2rem)] opacity-55" />
              <div className="relative flex min-h-[20rem] flex-col justify-between md:min-h-[24rem]">
                <div>
                  <p className="font-mono text-xs font-semibold tabular-nums tracking-[0.14em] text-[var(--wf-timecode)]">
                    {activeBeat.timecode}
                  </p>
                  <h3 className="mt-4 max-w-2xl text-3xl font-semibold tracking-[-0.04em] text-[var(--wf-paper-front)] md:text-5xl">
                    {activeBeat.title}
                  </h3>
                  <p className="mt-4 max-w-lg text-sm leading-7 text-[var(--wf-cinema-muted)]">
                    {activeBeat.copy}
                  </p>
                </div>
                <div className="grid grid-cols-[1.3fr_0.8fr_1fr] gap-3 pt-8">
                  <span className="h-16 rounded-[0.9rem] bg-[color-mix(in_srgb,var(--wf-paper-front)_10%,transparent)]" />
                  <span className="h-16 rounded-[0.9rem] bg-[color-mix(in_srgb,var(--wf-timecode)_13%,transparent)]" />
                  <span className="h-16 rounded-[0.9rem] bg-[color-mix(in_srgb,var(--wf-paper-front)_8%,transparent)]" />
                </div>
              </div>
            </motion.article>
          </div>

          <div className="relative z-20 lg:pt-2">
            <div className="pointer-events-none absolute bottom-10 left-5 top-5 w-px bg-[color-mix(in_srgb,var(--wf-text)_12%,transparent)]" />
            <motion.div
              aria-hidden="true"
              className="pointer-events-none absolute left-5 top-5 h-[calc(100%-2.5rem)] w-px origin-top rounded-full bg-[var(--wf-playhead)]"
              style={reduceMotion ? { scaleY: 1 } : { scaleY }}
            />

            <div className="grid gap-4">
              {beats.map((beat, index) => {
                const active = index === visualIndex;
                const past = index < visualIndex;
                return (
                  <article
                    key={beat.id}
                    className={clsx(
                      "relative ml-10 rounded-[1.1rem] border p-4 shadow-[0_18px_46px_rgba(92,58,36,.08)] transition duration-300 ease-out",
                      THUMB_ANGLES[index % THUMB_ANGLES.length],
                      active
                        ? "border-[var(--wf-playhead)] bg-[color-mix(in_srgb,var(--wf-surface)_88%,transparent)] opacity-100"
                        : past
                          ? "border-[var(--wf-border)] bg-[color-mix(in_srgb,var(--wf-surface)_64%,transparent)] opacity-80"
                          : "border-[var(--wf-border)] bg-[color-mix(in_srgb,var(--wf-surface)_48%,transparent)] opacity-60",
                    )}
                  >
                    <span
                      className={clsx(
                        "absolute -left-[2.9rem] top-5 inline-flex h-6 w-6 items-center justify-center rounded-full border bg-[color-mix(in_srgb,var(--wf-surface)_82%,transparent)] transition duration-300",
                        active || past ? "border-[var(--wf-playhead)] text-[var(--wf-accent)]" : "border-[var(--wf-border)] text-[var(--wf-text-tertiary)]",
                      )}
                    >
                      {active ? <Play size={9} fill="currentColor" aria-hidden="true" /> : <span className="h-2 w-2 rounded-full bg-current" />}
                    </span>
                    <p className="font-mono text-xs font-semibold tabular-nums tracking-[0.12em] text-[var(--wf-accent)]">{beat.timecode}</p>
                    <h3 className="mt-2 text-lg font-semibold text-[var(--wf-text)]">{beat.title}</h3>
                    <p className="mt-2 text-sm leading-6 text-[var(--wf-text-secondary)]">{beat.copy}</p>
                  </article>
                );
              })}
            </div>
          </div>

          <div className="relative z-30 lg:absolute lg:bottom-32 lg:left-[8%] lg:right-[4%]">
            <div className="relative h-32 rotate-[-1.5deg] border-y border-[color-mix(in_srgb,var(--wf-cinema-bg)_18%,transparent)] bg-[linear-gradient(180deg,color-mix(in_srgb,var(--wf-cinema-bg)_78%,transparent),color-mix(in_srgb,var(--wf-film-frame)_68%,transparent))] p-3 shadow-[0_26px_70px_color-mix(in_srgb,var(--wf-cinema-bg)_20%,transparent)] backdrop-blur-sm">
              <motion.div
                aria-hidden="true"
                className="absolute bottom-0 top-0 z-20 w-px bg-[var(--wf-playhead)] shadow-[0_0_18px_color-mix(in_srgb,var(--wf-playhead)_54%,transparent)]"
                style={reduceMotion ? { left: "92%" } : { left: scrubX }}
              />
              <div className="grid h-full grid-cols-4 gap-2">
                {beats.map((beat, index) => (
                  <div
                    key={beat.id}
                    className={clsx(
                      "relative overflow-hidden rounded-[0.85rem] border bg-[linear-gradient(135deg,var(--wf-film-frame),var(--wf-cinema-bg))] p-3 transition duration-300",
                      index === visualIndex
                        ? "border-[var(--wf-playhead)] shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--wf-playhead)_32%,transparent)]"
                        : "border-[color-mix(in_srgb,var(--wf-paper-front)_14%,transparent)] opacity-65",
                    )}
                  >
                    <span className="block font-mono text-[10px] font-semibold text-[var(--wf-timecode)]">{beat.timecode}</span>
                    <span className="absolute inset-x-3 bottom-3 h-4 rounded-md bg-[color-mix(in_srgb,var(--wf-paper-front)_10%,transparent)]" />
                  </div>
                ))}
              </div>
            </div>
            <p className="mt-4 font-mono text-xs tabular-nums text-[var(--wf-accent)]">
              CURRENT CUT {visualIndex + 1} / {beats.length}
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
