"use client";

import type { ComponentPropsWithoutRef, ReactNode } from "react";
import { motion, type MotionStyle, type MotionValue } from "framer-motion";
import clsx from "clsx";
import { FileText, Play } from "lucide-react";

export type TimelineFrame = {
  time: string;
  label: string;
};

type WorkbenchVariant = "hero" | "story" | "auth";

export function PaperWorkbenchSurface({
  children,
  className,
  variant = "hero",
  ...props
}: ComponentPropsWithoutRef<"div"> & {
  children: ReactNode;
  variant?: WorkbenchVariant;
}) {
  return (
    <div
      {...props}
      data-variant={variant}
      className={clsx("wf-paper-workbench-surface", className)}
    >
      {children}
    </div>
  );
}

export function EvidenceConnector({
  className,
  style,
}: {
  className?: string;
  style?: MotionStyle;
}) {
  return (
    <motion.div
      aria-hidden="true"
      className={clsx("wf-evidence-connector", className)}
      style={style}
    />
  );
}

export function PlayheadBeam({
  left,
  className,
  children,
  ...props
}: Omit<ComponentPropsWithoutRef<typeof motion.div>, "style"> & {
  left: MotionValue<string> | string;
  children?: ReactNode;
}) {
  return (
    <motion.div
      {...props}
      className={clsx("wf-playhead-beam", className)}
      style={{ left }}
    >
      <span className="wf-playhead-beam__handle">
        <Play size={11} fill="currentColor" aria-hidden="true" />
      </span>
      <span className="wf-playhead-beam__marker" />
      {children}
    </motion.div>
  );
}

export function TimecodeNode({
  frame,
  active,
  onClick,
  onFocus,
  onMouseEnter,
  testId,
  className,
}: {
  frame: TimelineFrame;
  active: boolean;
  onClick?: () => void;
  onFocus?: () => void;
  onMouseEnter?: () => void;
  testId?: string;
  className?: string;
}) {
  return (
    <button
      type="button"
      aria-label={`${frame.time} ${frame.label}`}
      aria-pressed={active}
      data-active={active ? "true" : "false"}
      data-testid={testId}
      className={clsx("wf-timecode-node", className)}
      onClick={onClick}
      onFocus={onFocus}
      onMouseEnter={onMouseEnter}
    >
      <span className="wf-timecode-node__time">{frame.time}</span>
      <span className="wf-timecode-node__label">{frame.label}</span>
    </button>
  );
}

export function FilmTimelineRail({
  frames,
  activeIndex,
  onFrameClick,
  onFrameFocus,
  onFrameHover,
  className,
}: {
  frames: readonly TimelineFrame[];
  activeIndex: number;
  onFrameClick?: (index: number) => void;
  onFrameFocus?: (index: number) => void;
  onFrameHover?: (index: number) => void;
  className?: string;
}) {
  return (
    <div className={clsx("wf-film-timeline-rail", className)}>
      <div className="wf-film-timeline-rail__sprockets" aria-hidden="true" />
      <div className="wf-film-timeline-rail__track">
        {frames.map((frame, index) => (
          <TimecodeNode
            key={frame.time}
            frame={frame}
            active={index === activeIndex}
            testId={`fold-frame-${frame.time}`}
            onClick={() => onFrameClick?.(index)}
            onFocus={() => onFrameFocus?.(index)}
            onMouseEnter={() => onFrameHover?.(index)}
          />
        ))}
      </div>
    </div>
  );
}

export function FoldingNoteSheet({
  time,
  title,
  children,
  active,
  testId,
  className,
  style,
  animate,
}: {
  time: string;
  title: string;
  children: ReactNode;
  active: boolean;
  testId?: string;
  className?: string;
  style?: MotionStyle;
  animate?: ComponentPropsWithoutRef<typeof motion.article>["animate"];
}) {
  return (
    <motion.article
      data-testid={testId}
      data-active={active ? "true" : "false"}
      className={clsx("wf-folding-note-sheet", className)}
      style={style}
      animate={animate}
      transition={{ duration: 0.34, ease: [0.16, 1, 0.3, 1] }}
    >
      <div className="wf-folding-note-sheet__fold" aria-hidden="true" />
      <div className="wf-folding-note-sheet__rail" aria-hidden="true" />
      <div className="wf-folding-note-sheet__header">
        <span className="wf-folding-note-sheet__time">
          <FileText size={12} aria-hidden="true" />
          {time}
        </span>
        <span className="wf-folding-note-sheet__edge" aria-hidden="true" />
      </div>
      <h3 className="wf-folding-note-sheet__title">{title}</h3>
      <p className="wf-folding-note-sheet__copy">{children}</p>
    </motion.article>
  );
}
