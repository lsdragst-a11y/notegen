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
    offset: ["start 70%", "end 35%"],
  });
  const smoothProgress = useSpring(scrollYProgress, {
    stiffness: 110,
    damping: 26,
    mass: 0.24,
  });
  const scaleX = useTransform(smoothProgress, [0, 1], [0.05, 1]);
  const beamY = useTransform(smoothProgress, [0, 1], ["0%", "100%"]);

  useMotionValueEvent(smoothProgress, "change", (latest) => {
    if (reduceMotion) return;
    const next = clampIndex(Math.round(latest * (beats.length - 1)), beats.length);
    setActiveIndex((current) => (current === next ? current : next));
  });

  return (
    <section id="preview" ref={sectionRef} className="relative px-5 py-12 sm:px-6 md:py-20" aria-labelledby="cinematic-story-title">
      <div className="mx-auto max-w-7xl">
        <div className="relative overflow-hidden rounded-[2rem] border border-[rgba(255,238,220,.10)] bg-[#211a16] text-[#fff7ed] shadow-[0_28px_90px_rgba(55,36,24,.26),inset_0_1px_0_rgba(255,245,230,.08)]">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_12%,rgba(228,123,89,.25),transparent_34%),radial-gradient(circle_at_82%_72%,rgba(211,161,115,.13),transparent_32%),linear-gradient(180deg,rgba(255,250,243,.06),transparent_54%)]" />
          <div className="grid gap-0 lg:grid-cols-[0.42fr_0.58fr]">
            <div className="relative min-h-[27rem] p-7 md:p-10 lg:sticky lg:top-24 lg:self-start">
              <div className="relative z-10">
                <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/10 px-3 py-1 text-xs font-semibold text-[#ffb28f]">
                  <Film size={14} aria-hidden="true" />
                  Cinematic Flow
                </div>
                <h2 id="cinematic-story-title" className="mt-6 font-[var(--wf-font-display)] text-4xl font-semibold leading-tight tracking-[-0.04em] md:text-6xl">
                  像预告片一样
                  <span className="block">展开学习过程</span>
                </h2>
                <p className="mt-5 max-w-md text-sm leading-7 text-[#d8c8ba]">
                  滚动时，镜头按视频时间点点亮。用户能看到导入、拆分、折页和回到证据这条完整路径。
                </p>
              </div>

              <div className="absolute bottom-8 left-7 right-7 z-10 md:left-10 md:right-10">
                <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.16em] text-white/42">
                  <span>Import</span>
                  <span>Replay</span>
                </div>
                <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/12">
                  <motion.div
                    className="h-full origin-left rounded-full bg-[var(--wf-brand-coral)]"
                    style={reduceMotion ? { scaleX: 1 } : { scaleX }}
                  />
                </div>
                <p className="mt-4 text-xs tabular-nums text-[#ffb28f]">
                  当前镜头 {activeIndex + 1} / {beats.length}
                </p>
              </div>
            </div>

            <div className="relative border-t border-white/10 bg-[#1b1512]/72 p-5 lg:border-l lg:border-t-0 md:p-8">
              <div className="pointer-events-none absolute inset-y-8 left-9 w-px bg-white/12 md:left-12" />
              <motion.div
                aria-hidden="true"
                className="pointer-events-none absolute left-[1.86rem] top-8 h-8 w-8 -translate-y-1/2 rounded-full border border-[#ffb28f]/50 bg-[#2a1710] shadow-[0_0_26px_rgba(228,123,89,.35)] md:left-[2.38rem]"
                style={reduceMotion ? undefined : { y: beamY }}
              >
                <span className="absolute left-1/2 top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#ffb28f]" />
              </motion.div>

              <div className="space-y-4">
                {beats.map((beat, index) => {
                  const active = index === activeIndex;
                  const past = index < activeIndex;
                  return (
                    <article
                      key={beat.id}
                      className={clsx(
                        "relative rounded-[1.35rem] border p-5 pl-12 shadow-[0_18px_44px_rgba(0,0,0,.18)] transition duration-300 ease-out",
                        active
                          ? "z-10 -translate-y-1 border-[#ffb28f]/32 bg-white/[0.09]"
                          : past
                            ? "border-white/10 bg-white/[0.052] opacity-75"
                            : "border-white/10 bg-white/[0.035] opacity-60",
                      )}
                    >
                      <span
                        className={clsx(
                          "absolute left-4 top-5 inline-flex h-5 w-5 items-center justify-center rounded-full border bg-[#211a16] transition duration-300",
                          active || past ? "border-[#ffb28f]" : "border-white/18",
                        )}
                      >
                        {active ? <Play size={9} fill="currentColor" className="text-[#ffb28f]" aria-hidden="true" /> : <span className="h-2 w-2 rounded-full bg-[#ffb28f]/70" />}
                      </span>
                      <p className="text-xs font-semibold tabular-nums tracking-[0.16em] text-[#ffb28f]">{beat.timecode}</p>
                      <h3 className="mt-2 text-lg font-semibold text-[#fff7ed]">{beat.title}</h3>
                      <p className="mt-2 text-sm leading-6 text-[#d8c8ba]">{beat.copy}</p>
                    </article>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
