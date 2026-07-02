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
import { Play } from "lucide-react";

import { CINEMATIC_BEATS } from "@/app/landing-model";

import { PaperWorkbenchSurface } from "./NoteGenMotionPrimitives";

type Beat = (typeof CINEMATIC_BEATS)[number];

const SHOT_STATE_CLASSES = [
  "wf-story-shot--import",
  "wf-story-shot--chapter",
  "wf-story-shot--extract",
  "wf-story-shot--evidence",
] as const;

function clampIndex(value: number, length: number) {
  return Math.max(0, Math.min(length - 1, value));
}

export function CinematicStoryboard({ beats = CINEMATIC_BEATS }: { beats?: readonly Beat[] }) {
  const sectionRef = useRef<HTMLElement>(null);
  const reduceMotion = useReducedMotion();
  const [activeIndex, setActiveIndex] = useState(0);
  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start start", "end end"],
  });
  const smoothProgress = useSpring(scrollYProgress, {
    stiffness: 110,
    damping: 30,
    mass: 0.24,
  });
  const scaleY = useTransform(smoothProgress, [0, 1], [0.16, 1]);
  const scrubX = useTransform(smoothProgress, [0, 1], ["10%", "90%"]);
  const filmX = useTransform(smoothProgress, [0, 1], ["0%", "-18%"]);
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
      className="wf-story-choreography relative px-5 py-16 sm:px-6 md:py-24"
      aria-labelledby="cinematic-story-title"
    >
      <PaperWorkbenchSurface variant="story" className="relative mx-auto max-w-7xl">
        <div className="wf-story-grid">
          <div className="wf-story-shot-wrap">
            <motion.article
              key={activeBeat.id}
              className={clsx(
                "wf-story-shot",
                SHOT_STATE_CLASSES[visualIndex % SHOT_STATE_CLASSES.length],
              )}
              initial={reduceMotion ? false : { opacity: 0.78, y: 18, scale: 0.985 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ duration: 0.38, ease: [0.16, 1, 0.3, 1] }}
            >
              <div className="wf-story-shot__gate" aria-hidden="true" />
              <div className="wf-story-shot__scan" aria-hidden="true" />
              <div className="wf-story-shot__body">
                <p className="wf-story-shot__time">{activeBeat.timecode}</p>
                <h3 className="wf-story-shot__title">{activeBeat.title}</h3>
                <p className="wf-story-shot__copy">{activeBeat.copy}</p>
              </div>
              <div className="wf-story-shot__state" aria-hidden="true">
                <span />
                <span />
                <span />
              </div>
            </motion.article>

            <div className="wf-story-film-dock" aria-hidden="true">
              <motion.div
                className="wf-story-film-playhead"
                style={reduceMotion ? { left: "90%" } : { left: scrubX }}
              />
              <motion.div
                className="wf-story-film-track"
                style={reduceMotion ? { x: "-18%" } : { x: filmX }}
              >
                {beats.concat(beats).map((beat, index) => (
                  <div
                    key={`${beat.id}-${index}`}
                    className={clsx(
                      "wf-story-film-frame",
                      index % beats.length === visualIndex && "wf-story-film-frame--active",
                    )}
                  >
                    <span>{beat.timecode}</span>
                    <i />
                  </div>
                ))}
              </motion.div>
            </div>
          </div>

          <div className="wf-story-script">
            <div className="wf-story-script__intro">
              <p className="wf-story-script__label">Storyboard Cut</p>
              <h2 id="cinematic-story-title">像预告片一样展开学习过程</h2>
              <p>
                当前镜头固定在左侧，右侧脚本推进时，底部胶片轨同步切换视频如何折成笔记。
              </p>
            </div>

            <div className="wf-story-script__rail" aria-hidden="true">
              <motion.div style={reduceMotion ? { scaleY: 1 } : { scaleY }} />
            </div>

            <div className="wf-story-script__beats">
              {beats.map((beat, index) => {
                const active = index === visualIndex;
                const past = index < visualIndex;
                return (
                  <article
                    key={beat.id}
                    className={clsx(
                      "wf-story-script-card",
                      active && "wf-story-script-card--active",
                      past && "wf-story-script-card--past",
                    )}
                  >
                    <span className="wf-story-script-card__node">
                      {active ? <Play size={9} fill="currentColor" aria-hidden="true" /> : null}
                    </span>
                    <p>{beat.timecode}</p>
                    <h3>{beat.title}</h3>
                    <span>{beat.copy}</span>
                  </article>
                );
              })}
            </div>
          </div>
        </div>
      </PaperWorkbenchSurface>
    </section>
  );
}
