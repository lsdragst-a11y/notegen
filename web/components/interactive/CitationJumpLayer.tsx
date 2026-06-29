"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";

import { formatTime } from "@/lib/notes";

export interface CitationJumpEvent {
  id: number;
  sourceRect: DOMRect;
  targetRect: DOMRect;
  targetTime: number;
}

function rectCenter(rect: DOMRect) {
  return {
    x: rect.left + rect.width / 2,
    y: rect.top + rect.height / 2,
  };
}

export function useCitationJump() {
  const [jump, setJump] = useState<CitationJumpEvent | null>(null);
  const timeoutRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (timeoutRef.current !== null) window.clearTimeout(timeoutRef.current);
    };
  }, []);

  const triggerJump = useCallback((source: HTMLElement | null, target: HTMLElement | null, targetTime: number) => {
    if (!target) return;

    const targetRect = target.getBoundingClientRect();
    const sourceRect = source?.getBoundingClientRect() ?? targetRect;
    const nextJump: CitationJumpEvent = {
      id: Date.now(),
      sourceRect,
      targetRect,
      targetTime,
    };

    if (timeoutRef.current !== null) window.clearTimeout(timeoutRef.current);
    setJump(nextJump);
    timeoutRef.current = window.setTimeout(() => {
      setJump(current => current?.id === nextJump.id ? null : current);
      timeoutRef.current = null;
    }, 760);
  }, []);

  return { jump, triggerJump };
}

export function CitationJumpLayer({ jump }: { jump: CitationJumpEvent | null }) {
  const shouldReduceMotion = useReducedMotion();
  if (!jump) return null;

  const source = rectCenter(jump.sourceRect);
  const target = rectCenter(jump.targetRect);
  const ringSize = 74;

  return (
    <AnimatePresence>
      <motion.div
        key={jump.id}
        className="pointer-events-none fixed inset-0 z-[80]"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: shouldReduceMotion ? 0 : 0.12 }}
        aria-hidden="true"
      >
        {!shouldReduceMotion && (
          <svg className="hidden h-full w-full md:block">
            <motion.line
              x1={source.x}
              y1={source.y}
              x2={target.x}
              y2={target.y}
              stroke="var(--wf-brand-coral)"
              strokeWidth="2"
              strokeLinecap="round"
              initial={{ pathLength: 0, opacity: 0.2 }}
              animate={{ pathLength: 1, opacity: [0.2, 0.92, 0] }}
              transition={{ duration: 0.68, ease: [0.22, 1, 0.36, 1] }}
            />
          </svg>
        )}

        <motion.div
          className="absolute rounded-full border border-[var(--wf-brand-coral)] bg-[color-mix(in_srgb,var(--wf-brand-coral)_10%,transparent)] shadow-[0_0_32px_rgba(228,123,89,.32)]"
          style={{
            left: target.x - ringSize / 2,
            top: target.y - ringSize / 2,
            width: ringSize,
            height: ringSize,
          }}
          initial={{ scale: shouldReduceMotion ? 1 : 0.72, opacity: 0 }}
          animate={{ scale: shouldReduceMotion ? 1 : [0.72, 1.05, 1], opacity: [0, 1, 0] }}
          transition={{ duration: shouldReduceMotion ? 0.2 : 0.72, ease: [0.22, 1, 0.36, 1] }}
        />

        {!shouldReduceMotion && (
          <motion.div
            className="absolute rounded-full bg-[#2a1710] px-2 py-1 text-[10px] font-semibold tabular-nums text-[#ffb28f] shadow-[0_12px_30px_rgba(0,0,0,.28)]"
            style={{ left: target.x + 30, top: target.y - 18 }}
            initial={{ y: 4, opacity: 0 }}
            animate={{ y: 0, opacity: [0, 1, 0] }}
            transition={{ duration: 0.72, ease: "easeOut" }}
          >
            {formatTime(jump.targetTime)}
          </motion.div>
        )}
      </motion.div>
    </AnimatePresence>
  );
}
