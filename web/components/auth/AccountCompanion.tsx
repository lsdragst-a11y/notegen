"use client";

import type { CSSProperties } from "react";
import { motion, useReducedMotion } from "framer-motion";

export type AccountCompanionState =
  | "idle"
  | "emailFocus"
  | "passwordFocus"
  | "passwordReveal"
  | "error"
  | "success";

interface AccountCompanionProps {
  state: AccountCompanionState;
  variant: "login" | "register";
}

interface AuthPreviewProps {
  state: AccountCompanionState;
  variant: "login" | "register";
  reduceMotion?: boolean | null;
}

type SensitiveCoverState = "open" | "locked" | "revealed";

const TIME_NODES = [
  { id: "03-11", time: "03:11", label: "章节定位", caption: "owner" },
  { id: "08-42", time: "08:42", label: "重点折叠", caption: "note" },
  { id: "12-18", time: "12:18", label: "证据问答", caption: "qa" },
] as const;

const VIDEO_FRAMES = [
  { time: "03:11", title: "概念开场" },
  { time: "08:42", title: "例题拆解" },
  { time: "12:18", title: "证据引用" },
] as const;

function stateLabel(state: AccountCompanionState) {
  if (state === "success") return "笔记已折入 notebook";
  if (state === "error") return "时间线停在 retry 00:08";
  if (state === "passwordReveal") return "书签已移开，密码可见";
  if (state === "passwordFocus") return "书签遮住了敏感内容";
  if (state === "emailFocus") return "账号归属已连接到时间线";
  return "视频、时间线、笔记和问答证据已准备好";
}

function sensitiveCoverState(state: AccountCompanionState): SensitiveCoverState {
  if (state === "passwordFocus") return "locked";
  if (state === "passwordReveal") return "revealed";
  return "open";
}

function activeTimecode(state: AccountCompanionState) {
  if (state === "emailFocus") return "03:11";
  if (state === "passwordFocus" || state === "passwordReveal") return "08:42";
  if (state === "success") return "12:18";
  return null;
}

export function AuthVideoStrip({ state }: Pick<AuthPreviewProps, "state">) {
  const active = activeTimecode(state) ?? "08:42";

  return (
    <div className="wf-auth-video-strip" data-testid="auth-video-strip" data-state={state} aria-label="视频片段预览">
      <div className="wf-auth-video-strip__header">
        <span>视频片段</span>
        <span className="tabular-nums">14:06</span>
      </div>
      <div className="wf-auth-video-strip__frames" aria-hidden="true">
        {VIDEO_FRAMES.map((frame, index) => (
          <span
            key={frame.time}
            className="wf-auth-video-strip__frame"
            data-active={frame.time === active ? "true" : "false"}
            style={{ "--frame-index": index } as CSSProperties}
          >
            <span className="wf-auth-video-strip__frame-light" />
            <span className="wf-auth-video-strip__frame-title">{frame.title}</span>
            <span className="wf-auth-video-strip__frame-time">{frame.time}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

export function AuthTimelineBeam({ state }: Pick<AuthPreviewProps, "state">) {
  const active = activeTimecode(state);
  const showRetry = state === "error";

  return (
    <div
      className="wf-auth-timeline-beam"
      data-testid="auth-timeline-beam"
      data-retry={showRetry ? "true" : "false"}
      data-state={state}
      aria-label="视频时间线"
    >
      <div className="wf-auth-timeline-beam__rail" aria-hidden="true" />
      <div className="wf-auth-timeline-beam__nodes">
        {TIME_NODES.map((node) => {
          const isActive = active === node.time || (showRetry && node.time === "03:11");
          return (
            <div
              key={node.id}
              className="wf-auth-timecode"
              data-testid={`auth-timecode-${node.id}`}
              data-active={isActive ? "true" : "false"}
            >
              <span className="wf-auth-timecode__pin" aria-hidden="true" />
              <span className="wf-auth-timecode__time">{node.time}</span>
              <span className="wf-auth-timecode__label">{node.label}</span>
            </div>
          );
        })}
      </div>
      {showRetry ? <span className="wf-auth-timeline-beam__retry">retry 00:08</span> : null}
    </div>
  );
}

export function AuthNoteSheetPreview({ state, variant, reduceMotion }: AuthPreviewProps) {
  const cover = sensitiveCoverState(state);
  const isRegister = variant === "register";
  const label = stateLabel(state);
  const isFolding = state === "success";
  const ownerActive = state === "emailFocus";

  return (
    <motion.article
      className="wf-auth-note-sheet-preview"
      data-testid="auth-note-sheet-preview"
      data-state={state}
      data-sensitive-cover={cover}
      data-folding={isFolding ? "true" : "false"}
      aria-label="生成后的笔记预览"
      animate={
        reduceMotion
          ? undefined
          : {
              rotate: isFolding ? -5 : state === "error" ? -2.2 : -1.2,
              y: isFolding ? -10 : 0,
              scale: isFolding ? 0.94 : 1,
            }
      }
      transition={{ type: "spring", stiffness: 140, damping: 22 }}
    >
      <div className="wf-auth-note-sheet-preview__topline">
        <span>生成笔记</span>
      </div>
      <div
        className="wf-auth-owner-chip"
        data-testid="auth-owner-chip"
        data-active={ownerActive ? "true" : "false"}
      >
        <span className="wf-auth-owner-chip__avatar" aria-hidden="true" />
        <span>{isRegister ? "owner: new workspace" : "owner: you@example.com"}</span>
      </div>
      <h3>{isRegister ? "第一本视频笔记预览" : "继续整理的视频笔记"}</h3>
      <div className="wf-auth-note-sheet-preview__body">
        <p>章节摘要已经从视频片段生成，并保留可跳回的证据时间戳。</p>
        <ul>
          <li>
            <span>03:11</span>
            <strong>视频主题和问题背景</strong>
          </li>
          <li>
            <span>08:42</span>
            <strong>关键步骤折成笔记页</strong>
          </li>
          <li>
            <span>12:18</span>
            <strong>问答引用回到原片段</strong>
          </li>
        </ul>
      </div>
      <motion.div
        className="wf-auth-note-sheet-preview__bookmark"
        data-cover={cover}
        aria-hidden={cover === "open" ? "true" : undefined}
        animate={reduceMotion ? undefined : { x: cover === "revealed" ? 24 : 0, opacity: cover === "open" ? 0.22 : 1 }}
        transition={{ duration: 0.28, ease: "easeOut" }}
      >
        {cover === "locked" ? "书签遮住了敏感内容" : cover === "revealed" ? "书签已移开，密码可见" : "private"}
      </motion.div>
      {isFolding ? <span className="wf-auth-note-sheet-preview__saved">{label}</span> : null}
      <p className="sr-only">{label}</p>
    </motion.article>
  );
}

export function AuthEvidenceCard({ state, reduceMotion }: Pick<AuthPreviewProps, "state" | "reduceMotion">) {
  const isError = state === "error";
  const isSuccess = state === "success";

  return (
    <motion.aside
      className="wf-auth-evidence-card"
      data-testid="auth-evidence-card"
      data-state={state}
      aria-label="问答证据预览"
      animate={reduceMotion ? undefined : { y: isSuccess ? -6 : 0, x: isError ? [-2, 2, -1, 0] : 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
    >
      <div className="wf-auth-evidence-card__header">
        <span>问答证据</span>
        <span>12:18</span>
      </div>
      <p className="wf-auth-evidence-card__question">问：这一步为什么成立？</p>
      <p className="wf-auth-evidence-card__answer">答：引用 12:18 的推导片段，并跳回视频证据。</p>
      <div className="wf-auth-evidence-card__link">
        <span aria-hidden="true" />
        <span>12:18 跳回视频证据</span>
      </div>
    </motion.aside>
  );
}

export function AccountPaperMascot({ state, reduceMotion }: Pick<AuthPreviewProps, "state" | "reduceMotion">) {
  return (
    <motion.div
      className="wf-account-paper-mascot"
      data-testid="account-paper-mascot"
      data-role="supporting-mascot"
      data-state={state}
      aria-hidden="true"
      animate={reduceMotion ? undefined : { rotate: state === "error" ? -6 : state === "success" ? 4 : -2 }}
      transition={{ type: "spring", stiffness: 150, damping: 20 }}
    >
      <span className="wf-account-paper-mascot__fold" />
      <span className="wf-account-paper-mascot__eyes">
        <span />
        <span />
      </span>
    </motion.div>
  );
}

export function AuthWorkbenchPreview({ state, variant, reduceMotion }: AuthPreviewProps) {
  return (
    <div className="wf-auth-workbench-preview" data-testid="auth-workbench-preview" data-state={state}>
      <AuthVideoStrip state={state} />
      <AuthTimelineBeam state={state} />
      <div className="wf-auth-workbench-preview__workspace">
        <AuthNoteSheetPreview state={state} variant={variant} reduceMotion={reduceMotion} />
        <AuthEvidenceCard state={state} reduceMotion={reduceMotion} />
        <AccountPaperMascot state={state} reduceMotion={reduceMotion} />
      </div>
    </div>
  );
}

export function AccountCompanion({ state, variant }: AccountCompanionProps) {
  const isRegister = variant === "register";
  const reduceMotion = useReducedMotion();

  return (
    <section
      aria-label={isRegister ? "NoteGen 注册工作台预览" : "NoteGen 登录工作台预览"}
      className="wf-account-companion relative block min-h-[27rem] overflow-visible rounded-[1.25rem] p-5 lg:min-h-[34rem] lg:p-8"
      data-state={state}
      data-testid="account-companion"
    >
      <div className="relative z-10 grid h-full min-h-[24rem] content-between gap-6 lg:min-h-[30rem]">
        <div className="lg:max-w-[35rem] lg:pl-2">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--wf-accent)]">
            {isRegister ? "Workspace preview" : "Notebook resume"}
          </p>
          <h2 className="mt-4 max-w-lg text-balance font-[var(--wf-font-display)] text-3xl font-semibold leading-[1.06] tracking-[-0.04em] lg:text-5xl">
            {isRegister ? "注册前先看到笔记工作台" : "登录后回到视频证据工作台"}
          </h2>
          <p className="mt-4 max-w-md text-sm leading-7 text-[var(--wf-text-secondary)]">
            {isRegister
              ? "视频、时间线、笔记和问答证据会收进同一个私有空间。"
              : "继续从视频片段跳到笔记、章节和问答证据。"}
          </p>
        </div>

        <AuthWorkbenchPreview state={state} variant={variant} reduceMotion={reduceMotion} />
      </div>
    </section>
  );
}
