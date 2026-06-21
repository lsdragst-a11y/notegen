"use client";

import { motion, useReducedMotion } from "framer-motion";
import {
  BookOpenText,
  CheckCircle2,
  ListChecks,
  ListTree,
  Mic2,
  Play,
  ScanText,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

const WAVE_BARS = [18, 28, 14, 34, 22, 40, 16, 30, 48, 22, 36, 56, 28, 42, 66, 30, 54, 24, 46, 34, 52, 20, 44, 30, 38, 18, 34, 26, 46, 20, 32, 16];

const CHAPTERS = [
  { t: "00:00", title: "线性代数基础与强化" },
  { t: "03:11", title: "基础换元与行列式计算" },
  { t: "08:11", title: "特征值与矩阵函数" },
  { t: "12:00", title: "真题与习题解答" },
];

function VisualShell({ children }: { children: ReactNode }) {
  return (
    <div
      aria-hidden="true"
      className="relative flex aspect-[4/3] items-center justify-center overflow-hidden rounded-3xl border border-white/10 bg-[#151719] p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_24px_70px_rgba(15,23,42,0.18)] sm:aspect-[16/9] sm:p-7"
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/25 to-transparent" />
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(135deg,rgba(255,255,255,0.04),transparent_42%,rgba(138,180,248,0.06))]" />
      <div className="relative h-full w-full">{children}</div>
    </div>
  );
}

function Waveform({ className = "" }: { className?: string }) {
  const shouldReduceMotion = useReducedMotion();

  return (
    <div className={`relative flex h-14 items-center gap-1 overflow-hidden rounded-xl bg-[#101215]/70 px-3 ${className}`}>
      <div className="absolute inset-x-3 top-1/2 h-px bg-[#293141]" />
      {WAVE_BARS.map((height, index) => (
        <motion.span
          key={`${height}-${index}`}
          animate={shouldReduceMotion ? undefined : { opacity: [0.35, 1, 0.45] }}
          transition={{ duration: 1.8, repeat: Infinity, delay: index * 0.035, ease: "easeInOut" }}
          className="relative z-10 w-1 rounded-full bg-[#2f7df6]"
          style={{ height: `${height}%` }}
        />
      ))}
    </div>
  );
}

function MovingPlayhead({ top = "38%", delay = 0 }: { top?: string; delay?: number }) {
  const shouldReduceMotion = useReducedMotion();

  return (
    <motion.div
      className="absolute z-20 h-[58%] w-px bg-[#5c9dff]"
      style={{ top }}
      animate={shouldReduceMotion ? { left: "50%" } : { left: ["17%", "47%", "82%", "17%"] }}
      transition={{ duration: 6.5, repeat: Infinity, delay, ease: "easeInOut" }}
    >
      <span className="absolute -left-[5px] -top-[5px] h-3 w-3 rounded-full bg-[#5c9dff] shadow-[0_0_18px_rgba(92,157,255,0.95)]" />
    </motion.div>
  );
}

function ProcessStep({
  icon: Icon,
  label,
  active,
}: {
  icon: LucideIcon;
  label: string;
  active?: boolean;
}) {
  return (
    <div
      className={`flex min-w-0 items-center gap-2 rounded-xl border px-3 py-2 text-[10px] font-medium shadow-[0_10px_28px_rgba(0,0,0,0.25)] sm:text-xs ${
        active
          ? "border-[#5c9dff]/80 bg-[#183053] text-[#e8f0fe]"
          : "border-white/10 bg-white/[0.07] text-[#c6cad3]"
      }`}
    >
      <span
        className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-lg ${
          active ? "bg-[#5c9dff] text-[#09111f]" : "bg-white/10 text-[#8ab4f8]"
        }`}
      >
        <Icon size={13} />
      </span>
      <span className="truncate">{label}</span>
    </div>
  );
}

export function UploadTimelineVisual() {
  const shouldReduceMotion = useReducedMotion();

  return (
    <VisualShell>
      <motion.div
        className="absolute left-1/2 top-4 z-20 w-48 -translate-x-1/2 rounded-2xl border border-white/10 bg-[#26282d] p-3 shadow-[0_22px_46px_rgba(0,0,0,0.42)] sm:top-6 sm:w-56 sm:p-4"
        animate={shouldReduceMotion ? undefined : { y: [0, 6, 0] }}
        transition={{ duration: 4.2, repeat: Infinity, ease: "easeInOut" }}
      >
        <span className="inline-flex rounded-lg bg-white/10 px-2 py-1 text-[10px] font-medium text-[#bdc1c6]">
          Notebook
        </span>
        <p className="mt-3 truncate text-sm font-medium text-[#e8eaed] sm:text-base">线代基础与强化</p>
        <p className="mt-1 text-[10px] text-[#9aa0a6]">bilibili.com · 16:42</p>
      </motion.div>

      <motion.div
        className="absolute left-1/2 top-[36%] h-10 w-px bg-[#5c9dff]"
        animate={shouldReduceMotion ? undefined : { scaleY: [0.72, 1.15, 0.72] }}
        transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
      >
        <span className="absolute -bottom-1.5 -left-[5px] h-3 w-3 rounded-full bg-[#5c9dff]" />
      </motion.div>

      <div className="absolute inset-x-6 top-[48%] sm:inset-x-10">
        <div className="mb-1 flex justify-between text-[10px] tabular-nums text-[#bdc1c6]">
          <span>00:00</span>
          <span>16:42</span>
        </div>
        <Waveform />
        <motion.div
          className="absolute left-[18%] top-7 h-1.5 w-1.5 rounded-full bg-[#5c9dff]"
          animate={shouldReduceMotion ? undefined : { left: ["18%", "48%", "80%", "18%"] }}
          transition={{ duration: 6.5, repeat: Infinity, ease: "easeInOut" }}
        />
      </div>

      <div className="absolute inset-x-5 bottom-5 grid grid-cols-2 gap-2 sm:inset-x-8 sm:grid-cols-4">
        <ProcessStep icon={Mic2} label="语音识别" active />
        <ProcessStep icon={ScanText} label="关键帧提取" />
        <ProcessStep icon={ListTree} label="内容理解" />
        <ProcessStep icon={CheckCircle2} label="处理完成" />
      </div>
    </VisualShell>
  );
}

export function ChaptersTimelineVisual() {
  const shouldReduceMotion = useReducedMotion();

  return (
    <VisualShell>
      <div className="absolute inset-x-6 top-5 sm:inset-x-10">
        <div className="mb-3 flex justify-between text-[10px] tabular-nums text-[#9aa0a6]">
          {["00:00", "03:11", "08:11", "12:00", "16:42"].map((time) => (
            <span key={time}>{time}</span>
          ))}
        </div>
        <div className="relative h-10">
          <div className="absolute inset-x-0 top-1/2 h-px bg-white/10" />
          {[14, 31, 50, 70, 90].map((left, index) => (
            <motion.div
              key={left}
              className="absolute top-0 h-8 w-16 rounded-lg border border-white/10 bg-white/[0.06]"
              style={{ left: `${left - 8}%` }}
              animate={shouldReduceMotion ? undefined : { opacity: [0.42, 0.85, 0.42] }}
              transition={{ duration: 3.2, repeat: Infinity, delay: index * 0.35, ease: "easeInOut" }}
            />
          ))}
        </div>
        <Waveform className="h-9 rounded-lg bg-transparent px-0" />
      </div>

      <MovingPlayhead top="18%" delay={0.2} />

      <div className="absolute inset-x-6 bottom-5 space-y-2 sm:inset-x-10">
        {CHAPTERS.map((chapter, index) => (
          <motion.div
            key={chapter.t}
            animate={
              shouldReduceMotion
                ? undefined
                : {
                    backgroundColor: index === 1 ? ["rgba(255,255,255,0.07)", "rgba(49,115,232,0.28)", "rgba(255,255,255,0.07)"] : undefined,
                    borderColor: index === 1 ? ["rgba(255,255,255,0.1)", "rgba(92,157,255,0.85)", "rgba(255,255,255,0.1)"] : undefined,
                  }
            }
            transition={{ duration: 4.8, repeat: Infinity, ease: "easeInOut" }}
            className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/[0.07] px-3 py-2.5"
          >
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#5c9dff]/15 text-[#5c9dff]">
              {index === 1 ? <Play size={10} fill="currentColor" /> : <span className="h-1.5 w-1.5 rounded-full bg-current" />}
            </span>
            <span className="text-[11px] tabular-nums text-[#8ab4f8]">{chapter.t}</span>
            <span className="min-w-0 truncate text-xs font-medium text-[#e8eaed]">{chapter.title}</span>
          </motion.div>
        ))}
      </div>
    </VisualShell>
  );
}

export function BilingualQuizTimelineVisual() {
  const shouldReduceMotion = useReducedMotion();

  return (
    <VisualShell>
      <div className="absolute bottom-10 left-6 top-8 w-20 rounded-2xl border border-white/10 bg-white/[0.07] p-3 sm:left-8 sm:w-24">
        <div className="relative h-full">
          <div className="absolute bottom-4 left-1/2 top-4 w-px -translate-x-1/2 bg-white/15" />
          {CHAPTERS.map((chapter, index) => (
            <div
              key={chapter.t}
              className="absolute left-0 right-0 flex items-center justify-between text-[10px] tabular-nums text-[#9aa0a6]"
              style={{ top: `${index * 26}%` }}
            >
              <span className={index === 1 ? "text-[#8ab4f8]" : ""}>{chapter.t}</span>
              <span className={`h-2.5 w-2.5 rounded-full ${index === 1 ? "bg-[#5c9dff] shadow-[0_0_16px_rgba(92,157,255,0.9)]" : "bg-white/25"}`} />
            </div>
          ))}
        </div>
      </div>

      <motion.div
        className="absolute left-[28%] top-[28%] h-px w-[15%] bg-[#5c9dff]"
        animate={shouldReduceMotion ? undefined : { opacity: [0.45, 1, 0.45] }}
        transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute left-[28%] top-[58%] h-px w-[15%] bg-[#5c9dff]"
        animate={shouldReduceMotion ? undefined : { opacity: [1, 0.45, 1] }}
        transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
      />

      <motion.div
        className="absolute right-6 top-7 w-[58%] rounded-2xl border border-white/10 bg-[#25272c] p-4 shadow-[0_22px_48px_rgba(0,0,0,0.36)] sm:right-9 sm:top-8"
        animate={shouldReduceMotion ? undefined : { y: [0, -4, 0] }}
        transition={{ duration: 4.5, repeat: Infinity, ease: "easeInOut" }}
      >
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-medium text-[#e8eaed]">
            <BookOpenText size={14} className="text-[#8ab4f8]" />
            中 / EN 双语笔记
          </div>
          <span className="rounded-full bg-[#21382c] px-2 py-0.5 text-[10px] font-medium text-[#8be79e]">EN</span>
        </div>
        <div className="grid gap-3 text-[10px] leading-5 text-[#d7dbe2] sm:grid-cols-2">
          <p>基变换不改变向量空间，但会改变坐标表示。</p>
          <p>Basis change preserves the vector space, while coordinates change.</p>
        </div>
      </motion.div>

      <div className="absolute bottom-7 right-6 w-[58%] rounded-2xl border border-white/10 bg-[#25272c] p-4 shadow-[0_22px_48px_rgba(0,0,0,0.32)] sm:right-9">
        <div className="mb-3 flex items-center justify-between text-xs font-medium text-[#e8eaed]">
          <span className="flex items-center gap-2">
            <ListChecks size={14} className="text-[#8ab4f8]" />
            小测完成
          </span>
          <span className="text-[11px] text-[#8be79e]">4/4 正确</span>
        </div>
        <p className="truncate text-[10px] text-[#bdc1c6]">行列式的几何意义是？</p>
        <div className="mt-3 flex gap-2 text-[10px]">
          <span className="rounded-full bg-[#21382c] px-2 py-1 text-[#8be79e]">体积缩放倍率</span>
          <span className="rounded-full bg-white/10 px-2 py-1 text-[#9aa0a6]">线性相关性</span>
        </div>
      </div>

      <motion.div
        className="absolute bottom-10 right-4 rounded-xl border border-[#65d983]/50 bg-[#15311f] px-3 py-2 text-xs font-medium tabular-nums text-[#8be79e] shadow-[0_0_24px_rgba(101,217,131,0.18)]"
        animate={shouldReduceMotion ? undefined : { scale: [1, 1.04, 1] }}
        transition={{ duration: 2.6, repeat: Infinity, ease: "easeInOut" }}
      >
        03:11
      </motion.div>
    </VisualShell>
  );
}
