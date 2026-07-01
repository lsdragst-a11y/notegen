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
    offset: ["start 65%", "end 35%"],
  });
  const smoothProgress = useSpring(scrollYProgress, {
    stiffness: 110,
    damping: 28,
    mass: 0.24,
  });
  const scaleY = useTransform(smoothProgress, [0, 1], [0.08, 1]);
  const scrubX = useTransform(smoothProgress, [0, 1], ["8%", "92%"]);

  useMotionValueEvent(smoothProgress, "change", (latest) => {
    if (reduceMotion) return;
    const next = clampIndex(Math.round(latest * (beats.length - 1)), beats.length);
    setActiveIndex((current) => (current === next ? current : next));
  });

  return (
    <section id="preview" ref={sectionRef} className="relative px-5 py-14 sm:px-6 md:py-24" aria-labelledby="cinematic-story-title">
      <div className="mx-auto max-w-7xl">
        <div className="relative overflow-hidden rounded-[2.25rem] border border-[rgba(255,238,220,.10)] bg-[#1f1814] text-[#fff7ed] shadow-[0_34px_110px_rgba(55,36,24,.30),inset_0_1px_0_rgba(255,245,230,.08)]">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18%_14%,rgba(228,123,89,.25),transparent_34%),radial-gradient(circle_at_72%_62%,rgba(255,178,143,.10),transparent_36%),linear-gradient(90deg,rgba(255,250,243,.055),transparent_42%,rgba(0,0,0,.16))]" />
          <div className="pointer-events-none absolute inset-y-0 left-[42%] hidden w-px bg-white/10 lg:block" />

          <div className="relative grid gap-0 lg:grid-cols-[0.42fr_0.58fr]">
            <div className="relative min-h-[35rem] p-7 md:p-10">
              <div className="relative z-10">
                <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/10 px-3 py-1 text-xs font-semibold text-[#ffb28f]">
                  <Film size={14} aria-hidden="true" />
                  Storyboard Cut
                </div>
                <h2 id="cinematic-story-title" className="mt-6 font-[var(--wf-font-display)] text-4xl font-semibold leading-[0.98] tracking-[-0.045em] md:text-6xl">
                  像预告片一样
                  <span className="block">展开学习过程</span>
                </h2>
                <p className="mt-6 max-w-md text-sm leading-7 text-[#d8c8ba]">
                  静态时能看到完整分镜，滚动时播放头沿时间线推进，当前镜头会从暗部浮到前景。
                </p>
              </div>

              <div className="absolute bottom-10 left-7 right-7 z-10 md:left-10 md:right-10">
                <div className="relative h-28 overflow-hidden rounded-[1.35rem] border border-white/10 bg-black/22 p-3">
                  <motion.div
                    aria-hidden="true"
                    className="absolute bottom-0 top-0 z-20 w-px bg-[#ffb28f] shadow-[0_0_18px_rgba(255,178,143,.54)]"
                    style={reduceMotion ? { left: "72%" } : { left: scrubX }}
                  />
                  <div className="grid h-full grid-cols-4 gap-2">
                    {beats.map((beat, index) => (
                      <div
                        key={beat.id}
                        className={clsx(
                          "relative overflow-hidden rounded-[1rem] border bg-gradient-to-br p-3 transition duration-300",
                          index <= activeIndex
                            ? "border-[#ffb28f]/40 from-[#553024] to-[#1c1411]"
                            : "border-white/10 from-[#2b211d] to-[#17110f] opacity-65",
                        )}
                      >
                        <span className="block font-mono text-[10px] font-semibold text-[#ffb28f]">{beat.timecode}</span>
                        <span className="absolute inset-x-3 bottom-3 h-4 rounded-md bg-white/10" />
                      </div>
                    ))}
                  </div>
                </div>
                <p className="mt-4 font-mono text-xs tabular-nums text-[#ffb28f]">
                  CURRENT CUT {activeIndex + 1} / {beats.length}
                </p>
              </div>
            </div>

            <div className="relative min-h-[35rem] border-t border-white/10 p-5 lg:border-t-0 md:p-8">
              <div className="pointer-events-none absolute bottom-10 left-10 top-10 w-px bg-white/12" />
              <motion.div
                aria-hidden="true"
                className="pointer-events-none absolute left-[1.88rem] top-10 h-[calc(100%-5rem)] w-px origin-top rounded-full bg-[#ffb28f] md:left-[2.38rem]"
                style={reduceMotion ? { scaleY: 1 } : { scaleY }}
              />

              <div className="relative z-10 grid gap-4">
                {beats.map((beat, index) => {
                  const active = index === activeIndex;
                  const past = index < activeIndex;
                  return (
                    <article
                      key={beat.id}
                      className={clsx(
                        "relative ml-8 rounded-[1.45rem] border p-5 shadow-[0_18px_44px_rgba(0,0,0,.18)] transition duration-300 ease-out md:ml-10",
                        index % 2 === 1 ? "lg:ml-[4.5rem]" : "lg:mr-10",
                        active
                          ? "z-20 -translate-y-1 border-[#ffb28f]/38 bg-white/[0.10]"
                          : past
                            ? "border-white/10 bg-white/[0.055] opacity-78"
                            : "border-white/10 bg-white/[0.035] opacity-58",
                      )}
                    >
                      <span
                        className={clsx(
                          "absolute -left-[2.55rem] top-6 inline-flex h-6 w-6 items-center justify-center rounded-full border bg-[#211a16] transition duration-300 md:-left-[3.05rem]",
                          active || past ? "border-[#ffb28f] text-[#ffb28f]" : "border-white/20 text-white/35",
                        )}
                      >
                        {active ? <Play size={9} fill="currentColor" aria-hidden="true" /> : <span className="h-2 w-2 rounded-full bg-current" />}
                      </span>
                      <p className="font-mono text-xs font-semibold tabular-nums tracking-[0.12em] text-[#ffb28f]">{beat.timecode}</p>
                      <h3 className="mt-2 text-xl font-semibold text-[#fff7ed]">{beat.title}</h3>
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
