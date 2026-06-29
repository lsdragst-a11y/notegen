"use client";

import { motion, useReducedMotion } from "framer-motion";
import { Archive, AudioLines, CheckCircle2, FileVideo, ListTree, TriangleAlert } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { getGenerationVisualState, type GenerationStep } from "./motionModel";

export interface GenerationCompanionProps {
  stage: string;
  percent: number;
  error: string | null;
  message: string;
  title?: string;
  elapsed: number;
}

const STEPS: Array<{ id: GenerationStep; label: string; icon: LucideIcon }> = [
  { id: "receive", label: "接收视频", icon: FileVideo },
  { id: "transcribe", label: "转写声音", icon: AudioLines },
  { id: "structure", label: "折叠章节", icon: ListTree },
  { id: "archive", label: "整理归档", icon: Archive },
];

function formatElapsed(seconds: number) {
  return `${Math.floor(seconds / 60).toString().padStart(2, "0")}:${(Math.floor(seconds) % 60).toString().padStart(2, "0")}`;
}

export function GenerationCompanion({
  stage,
  percent,
  error,
  message,
  title,
  elapsed,
}: GenerationCompanionProps) {
  const shouldReduceMotion = useReducedMotion();
  const visual = getGenerationVisualState({ stage, percent, error });
  const activeIndex = STEPS.findIndex(step => step.id === visual.activeStep);
  const isFailed = visual.status === "failed";
  const isDone = visual.status === "done";

  return (
    <section
      className="mt-6 overflow-hidden rounded-[1.5rem] border border-[var(--wf-border)] bg-[var(--wf-surface)] text-[var(--wf-text)] shadow-[var(--wf-shadow-sm)]"
      aria-label="笔记生成进度"
    >
      <div className="grid gap-0 lg:grid-cols-[0.42fr_0.58fr]">
        <div className="relative min-h-64 overflow-hidden bg-[#17120f] p-5 text-[#fff7ed]">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_18%,rgba(228,123,89,.26),transparent_32%),linear-gradient(145deg,rgba(255,247,237,.07),transparent_48%)]" />
          <motion.div
            className="relative z-10 mx-auto mt-4 h-40 w-32 rounded-[1.15rem] border border-[#ffcfb7]/35 bg-[#fff7ed] text-[#2d2925] shadow-[0_22px_48px_rgba(0,0,0,.3)]"
            animate={shouldReduceMotion ? undefined : {
              y: isFailed || isDone ? 0 : [0, -4, 0],
              rotate: isFailed ? -2 : isDone ? 0 : [0, 1.2, 0],
            }}
            transition={{ duration: 2.8, repeat: isFailed || isDone ? 0 : Infinity, ease: "easeInOut" }}
          >
            <div className="absolute right-0 top-0 h-12 w-12 rounded-bl-[1rem] border-b border-l border-[#d8c8ba] bg-[#f0dfcf]" />
            <div className="px-4 pt-12">
              <div className="h-2 w-16 rounded-full bg-[rgba(182,92,58,.22)]" />
              <div className="mt-3 h-2 w-20 rounded-full bg-[rgba(45,41,37,.14)]" />
              <div className="mt-2 h-2 w-14 rounded-full bg-[rgba(45,41,37,.1)]" />
            </div>
            <motion.div
              className={`absolute -bottom-3 left-1/2 flex h-10 w-10 -translate-x-1/2 items-center justify-center rounded-full ${
                isFailed ? "bg-[var(--wf-danger)] text-[var(--wf-on-danger)]" : "bg-[var(--wf-brand-coral)] text-[var(--wf-on-accent)]"
              }`}
              animate={shouldReduceMotion ? undefined : { scale: isDone ? [1, 1.08, 1] : 1 }}
              transition={{ duration: 0.42, ease: "easeOut" }}
            >
              {isFailed ? <TriangleAlert size={18} /> : isDone ? <CheckCircle2 size={18} /> : <Archive size={18} />}
            </motion.div>
          </motion.div>
          <div className="relative z-10 mt-8 text-center">
            <p className="text-xs uppercase tracking-[0.18em] text-[#ffb28f]">Generation ritual</p>
            <p className="mt-2 text-sm leading-6 text-[#d8c8ba]">
              {isFailed ? "页面停在出错时间点，方便重试。" : "视频正在被折叠成可复习的笔记页。"}
            </p>
          </div>
        </div>

        <div className="p-5">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-xs font-semibold text-[var(--wf-accent)]">{visual.label}</p>
              <h2 className="mt-1 truncate text-lg font-semibold tracking-[-0.02em]">
                {title || (isFailed ? "生成未完成" : isDone ? "笔记生成完成" : "正在生成笔记")}
              </h2>
            </div>
            <span className="shrink-0 rounded-full bg-[var(--wf-surface-muted)] px-3 py-1 text-xs tabular-nums text-[var(--wf-text-secondary)]">
              {formatElapsed(elapsed)}
            </span>
          </div>

          <p className={`mt-3 text-sm leading-6 ${isFailed ? "text-[var(--wf-danger)]" : "text-[var(--wf-text-secondary)]"}`}>
            {message}
          </p>

          <div className="mt-5">
            <div className="relative h-2 overflow-hidden rounded-full bg-[color-mix(in_srgb,var(--wf-text)_10%,transparent)]">
              <motion.span
                className={`absolute inset-y-0 left-0 w-full origin-left rounded-full ${
                  isFailed ? "bg-[var(--wf-danger)]" : "bg-[var(--wf-brand-coral)]"
                }`}
                initial={false}
                animate={{ scaleX: visual.safePercent / 100 }}
                transition={{ duration: shouldReduceMotion ? 0 : 0.34, ease: [0.22, 1, 0.36, 1] }}
              />
            </div>
            <div className="mt-2 flex justify-between text-xs tabular-nums text-[var(--wf-text-tertiary)]">
              <span>{stage}</span>
              <span>{visual.safePercent}%</span>
            </div>
          </div>

          <div className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {STEPS.map((step, index) => {
              const Icon = step.icon;
              const complete = isDone || index < activeIndex;
              const active = index === activeIndex && !isDone && !isFailed;
              const failedHere = isFailed && index === activeIndex;
              return (
                <div
                  key={step.id}
                  className={`rounded-xl border p-2.5 text-center transition-colors ${
                    complete
                      ? "border-[var(--wf-brand-coral)] bg-[color-mix(in_srgb,var(--wf-brand-coral)_14%,var(--wf-surface))] text-[var(--wf-accent)]"
                      : failedHere
                        ? "border-[var(--wf-danger-border)] bg-[var(--wf-danger-surface)] text-[var(--wf-danger)]"
                        : active
                          ? "border-[var(--wf-border-strong)] bg-[var(--wf-surface-muted)] text-[var(--wf-text)]"
                          : "border-[var(--wf-border)] bg-[var(--wf-surface)] text-[var(--wf-text-tertiary)]"
                  }`}
                >
                  <Icon size={15} className="mx-auto" aria-hidden="true" />
                  <span className="mt-1 block text-[11px] font-medium">{step.label}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
