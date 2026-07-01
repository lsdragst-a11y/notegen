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
  const scrubX = useTransform(smoothProgress, [0, 1], ["12%", "88%"]);
  const visualIndex = reduceMotion ? beats.length - 1 : activeIndex;
  const activeBeat = beats[visualIndex];

  useMotionValueEvent(smoothProgress, "change", (latest) => {
    if (reduceMotion) return;
    const next = clampIndex(Math.round(latest * (beats.length - 1)), beats.length);
    setActiveIndex((current) => (current === next ? current : next));
  });

  return (
    <section id="preview" ref={sectionRef} className="relative px-5 py-14 sm:px-6 md:py-24" aria-labelledby="cinematic-story-title">
      <div className="mx-auto max-w-7xl">
        <div className="relative overflow-hidden rounded-[2.4rem] border border-[var(--wf-cinema-border)] bg-[var(--wf-cinema-bg)] text-[var(--wf-cinema-text)] shadow-[0_34px_110px_color-mix(in_srgb,var(--wf-cinema-bg)_36%,transparent),inset_0_1px_0_color-mix(in_srgb,var(--wf-paper-front)_8%,transparent)]">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18%_14%,color-mix(in_srgb,var(--wf-warm-glow)_24%,transparent),transparent_34%),radial-gradient(circle_at_72%_62%,color-mix(in_srgb,var(--wf-timecode)_10%,transparent),transparent_36%),linear-gradient(90deg,color-mix(in_srgb,var(--wf-paper-front)_5%,transparent),transparent_42%,rgba(0,0,0,.16))]" />

          <div className="relative grid gap-0 lg:grid-cols-[0.6fr_0.4fr]">
            <div className="relative min-h-[39rem] p-6 md:p-10">
              <div className="relative z-10 max-w-xl">
                <div className="inline-flex items-center gap-2 rounded-full border border-[var(--wf-cinema-border)] bg-[color-mix(in_srgb,var(--wf-cinema-panel)_82%,transparent)] px-3 py-1 text-xs font-semibold text-[var(--wf-timecode)]">
                  <Film size={14} aria-hidden="true" />
                  Storyboard Cut
                </div>
                <h2 id="cinematic-story-title" className="mt-6 font-[var(--wf-font-display)] text-4xl font-semibold leading-[0.98] tracking-[-0.045em] md:text-6xl">
                  像预告片一样
                  <span className="block">展开学习过程</span>
                </h2>
                <p className="mt-6 max-w-md text-sm leading-7 text-[var(--wf-cinema-muted)]">
                  当前镜头被放大成主画面，时间线和缩略镜头同步标记视频如何折成笔记。
                </p>
              </div>

              <motion.article
                key={activeBeat.id}
                className="relative z-10 mt-10 min-h-[18rem] overflow-hidden rounded-[2rem] border border-[var(--wf-cinema-border)] bg-[linear-gradient(135deg,color-mix(in_srgb,var(--wf-film-frame)_76%,transparent),color-mix(in_srgb,var(--wf-cinema-panel)_92%,transparent))] p-6 shadow-[0_28px_80px_color-mix(in_srgb,var(--wf-cinema-bg)_42%,transparent)]"
                initial={reduceMotion ? false : { opacity: 0.72, y: 14, scale: 0.985 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ duration: 0.38, ease: [0.16, 1, 0.3, 1] }}
              >
                <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_72%_20%,color-mix(in_srgb,var(--wf-timecode)_20%,transparent),transparent_34%),linear-gradient(180deg,color-mix(in_srgb,var(--wf-paper-front)_7%,transparent),transparent_48%)]" />
                <div className="relative flex h-full min-h-[14.5rem] flex-col justify-between">
                  <div>
                    <p className="font-mono text-xs font-semibold tabular-nums tracking-[0.14em] text-[var(--wf-timecode)]">
                      {activeBeat.timecode}
                    </p>
                    <h3 className="mt-4 max-w-lg text-3xl font-semibold tracking-[-0.04em] text-[var(--wf-paper-front)] md:text-5xl">
                      {activeBeat.title}
                    </h3>
                    <p className="mt-4 max-w-md text-sm leading-7 text-[var(--wf-cinema-muted)]">
                      {activeBeat.copy}
                    </p>
                  </div>
                  <div className="grid grid-cols-3 gap-3 pt-8">
                    <span className="h-12 rounded-[1rem] bg-[color-mix(in_srgb,var(--wf-paper-front)_10%,transparent)]" />
                    <span className="h-12 rounded-[1rem] bg-[color-mix(in_srgb,var(--wf-timecode)_12%,transparent)]" />
                    <span className="h-12 rounded-[1rem] bg-[color-mix(in_srgb,var(--wf-paper-front)_8%,transparent)]" />
                  </div>
                </div>
              </motion.article>
            </div>

            <div className="relative min-h-[39rem] border-t border-[var(--wf-cinema-border)] p-6 lg:border-l lg:border-t-0 md:p-10">
              <div className="pointer-events-none absolute bottom-32 left-10 top-12 w-px bg-[color-mix(in_srgb,var(--wf-paper-front)_12%,transparent)] md:left-12" />
              <motion.div
                aria-hidden="true"
                className="pointer-events-none absolute left-10 top-12 h-[calc(100%-11rem)] w-px origin-top rounded-full bg-[var(--wf-playhead)] md:left-12"
                style={reduceMotion ? { scaleY: 1 } : { scaleY }}
              />

              <div className="relative z-10 grid gap-4">
                {beats.map((beat, index) => {
                  const active = index === visualIndex;
                  const past = index < visualIndex;
                  return (
                    <article
                      key={beat.id}
                      className={clsx(
                        "relative ml-10 rounded-[1.35rem] border p-4 transition duration-300 ease-out",
                        active
                          ? "border-[var(--wf-playhead)] bg-[color-mix(in_srgb,var(--wf-paper-front)_10%,transparent)] shadow-[0_18px_48px_color-mix(in_srgb,var(--wf-cinema-bg)_24%,transparent)]"
                          : past
                            ? "border-[var(--wf-cinema-border)] bg-[color-mix(in_srgb,var(--wf-paper-front)_5%,transparent)] opacity-78"
                            : "border-[var(--wf-cinema-border)] bg-[color-mix(in_srgb,var(--wf-paper-front)_3%,transparent)] opacity-58",
                      )}
                    >
                      <span
                        className={clsx(
                          "absolute -left-[3.1rem] top-5 inline-flex h-6 w-6 items-center justify-center rounded-full border bg-[var(--wf-cinema-panel)] transition duration-300",
                          active || past ? "border-[var(--wf-playhead)] text-[var(--wf-timecode)]" : "border-[var(--wf-cinema-border)] text-[color-mix(in_srgb,var(--wf-paper-front)_35%,transparent)]",
                        )}
                      >
                        {active ? <Play size={9} fill="currentColor" aria-hidden="true" /> : <span className="h-2 w-2 rounded-full bg-current" />}
                      </span>
                      <p className="font-mono text-xs font-semibold tabular-nums tracking-[0.12em] text-[var(--wf-timecode)]">{beat.timecode}</p>
                      <h3 className="mt-2 text-lg font-semibold text-[var(--wf-paper-front)]">{beat.title}</h3>
                      <p className="mt-2 text-sm leading-6 text-[var(--wf-cinema-muted)]">{beat.copy}</p>
                    </article>
                  );
                })}
              </div>

              <div className="absolute bottom-8 left-6 right-6 z-10 md:left-10 md:right-10">
                <div className="relative h-28 overflow-hidden rounded-[1.35rem] border border-[var(--wf-cinema-border)] bg-[color-mix(in_srgb,var(--wf-cinema-panel)_78%,transparent)] p-3">
                  <motion.div
                    aria-hidden="true"
                    className="absolute bottom-0 top-0 z-20 w-px bg-[var(--wf-playhead)] shadow-[0_0_18px_color-mix(in_srgb,var(--wf-playhead)_54%,transparent)]"
                    style={reduceMotion ? { left: "88%" } : { left: scrubX }}
                  />
                  <div className="grid h-full grid-cols-4 gap-2">
                    {beats.map((beat, index) => (
                      <div
                        key={beat.id}
                        className={clsx(
                          "relative overflow-hidden rounded-[1rem] border bg-[linear-gradient(135deg,var(--wf-film-frame),var(--wf-cinema-bg))] p-3 transition duration-300",
                          index === visualIndex ? "border-[var(--wf-playhead)]" : "border-[var(--wf-cinema-border)] opacity-62",
                        )}
                      >
                        <span className="block font-mono text-[10px] font-semibold text-[var(--wf-timecode)]">{beat.timecode}</span>
                        <span className="absolute inset-x-3 bottom-3 h-4 rounded-md bg-[color-mix(in_srgb,var(--wf-paper-front)_10%,transparent)]" />
                      </div>
                    ))}
                  </div>
                </div>
                <p className="mt-4 font-mono text-xs tabular-nums text-[var(--wf-timecode)]">
                  CURRENT CUT {visualIndex + 1} / {beats.length}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
