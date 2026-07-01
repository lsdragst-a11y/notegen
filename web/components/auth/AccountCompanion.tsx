"use client";

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

const RECENT_NOTES = [
  { time: "03:11", text: "章节自动展开" },
  { time: "08:42", text: "重点折进纸页" },
  { time: "12:18", text: "回答追溯到视频" },
] as const;

function stateLabel(state: AccountCompanionState) {
  if (state === "success") return "纸页把书签归档完成";
  if (state === "error") return "纸页停在错误时间戳旁";
  if (state === "passwordReveal") return "纸页从书签旁确认密码可见";
  if (state === "passwordFocus") return "纸页用书签遮住密码行";
  if (state === "emailFocus") return "纸页看向邮箱时间戳";
  return "纸页正在等你继续整理";
}

export function AccountCompanion({ state, variant }: AccountCompanionProps) {
  const isRegister = variant === "register";
  const label = stateLabel(state);
  const reduceMotion = useReducedMotion();
  const paperTilt = state === "success" ? -2 : state === "error" ? -7 : -4;
  const paperY = state === "emailFocus" ? -4 : state === "success" ? -8 : 0;
  const eyeX = state === "emailFocus" ? 6 : state === "error" ? -4 : state === "success" ? 3 : 0;
  const eyeY = state === "emailFocus" ? -2 : state === "passwordReveal" ? 1 : 0;
  const bookmarkTilt = state === "passwordReveal" ? 10 : state === "passwordFocus" ? -10 : state === "success" ? 8 : 0;
  const bookmarkY = state === "passwordFocus" ? 18 : state === "passwordReveal" ? 10 : state === "success" ? -10 : state === "error" ? -3 : 0;
  const shakeX = state === "error" && !reduceMotion ? [0, -4, 4, -3, 0] : 0;

  return (
    <section
      aria-label={isRegister ? "NoteGen 注册角色入口" : "NoteGen 登录角色入口"}
      className="wf-account-companion relative block min-h-[27rem] overflow-hidden rounded-[2rem] p-5 lg:min-h-[34rem] lg:p-8"
    >
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18%_12%,color-mix(in_srgb,var(--wf-brand-coral)_13%,transparent),transparent_34%),radial-gradient(circle_at_82%_74%,color-mix(in_srgb,var(--wf-caramel)_18%,transparent),transparent_30%)]" />
      <motion.div
        aria-hidden="true"
        className="pointer-events-none absolute -left-12 bottom-24 h-16 w-[34rem] origin-left rounded-full border border-[color-mix(in_srgb,var(--wf-brand-coral)_24%,transparent)] bg-[color-mix(in_srgb,var(--wf-brand-coral)_10%,transparent)]"
        animate={reduceMotion ? undefined : { rotate: state === "emailFocus" ? -4 : state === "passwordFocus" ? 4 : -1, y: state === "error" ? -4 : 0 }}
        transition={{ duration: 0.42, ease: "easeOut" }}
      />
      <div aria-hidden="true" className="pointer-events-none absolute bottom-8 left-10 right-10 h-px bg-gradient-to-r from-transparent via-[color-mix(in_srgb,var(--wf-text)_14%,transparent)] to-transparent" />

      <div className="relative z-10 flex h-full min-h-[24rem] flex-col justify-between lg:min-h-[30rem]">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--wf-accent)]">
            {isRegister ? "Create notebook" : "Back to notebook"}
          </p>
          <h2 className="mt-4 max-w-lg text-balance font-[var(--wf-font-display)] text-3xl font-semibold leading-[1.06] tracking-[-0.04em] lg:text-5xl">
            {isRegister ? "给第一本视频笔记留一个位置" : "回到你的时间线和笔记页"}
          </h2>
          <p className="mt-4 max-w-md text-sm leading-7 text-[var(--wf-text-secondary)]">
            {isRegister
              ? "创建账号后，视频、章节、提问和复习进度会收进同一个私有空间。"
              : "登录后继续从视频时间点回到笔记、书签和问答记录。"}
          </p>
        </div>

        <div className="grid gap-5 pt-8 lg:grid-cols-[0.64fr_0.36fr] lg:items-end">
          <motion.div
            data-testid="account-companion"
            data-state={state}
            className="relative mx-auto h-64 w-72"
            animate={reduceMotion ? undefined : { x: shakeX }}
            transition={{ duration: 0.34, ease: "easeOut" }}
          >
            <motion.div
              aria-hidden="true"
              className="absolute left-8 top-5 h-[13rem] w-44 rounded-[1.35rem] border border-[var(--wf-border-strong)]
                         bg-[var(--wf-surface)] shadow-[var(--wf-shadow-md)]"
              data-state={state}
              animate={reduceMotion ? undefined : { rotate: paperTilt, y: paperY }}
              transition={{ type: "spring", stiffness: 170, damping: 20 }}
            >
              <div className="absolute right-0 top-0 h-16 w-16 rounded-bl-[1.1rem] rounded-tr-[1.35rem] bg-[color-mix(in_srgb,var(--wf-caramel)_24%,var(--wf-surface))]" />
              <div className="absolute right-1 top-1 h-12 w-12 rounded-bl-[0.9rem] border-b border-l border-[rgba(45,41,37,.12)] bg-[color-mix(in_srgb,var(--wf-caramel)_12%,var(--wf-surface))]" />
              <div className="absolute left-6 top-8 h-2 w-24 rounded-full bg-[var(--wf-surface-muted)]" />
              <div className="absolute left-6 top-14 h-2 w-20 rounded-full bg-[var(--wf-surface-muted)]" />
              <div className="absolute left-6 top-[6.25rem] h-2 w-28 rounded-full bg-[color-mix(in_srgb,var(--wf-brand-coral)_18%,var(--wf-surface-muted))]" />
              <div className="absolute bottom-8 left-6 h-1.5 w-[7.5rem] rounded-full bg-[color-mix(in_srgb,var(--wf-brand-coral)_40%,var(--wf-surface-muted))]" />
            </motion.div>

            <motion.div
              aria-hidden="true"
              className="absolute right-[3.75rem] top-14 z-20 h-[8.5rem] w-7 rounded-full bg-[var(--wf-brand-coral)] shadow-[var(--wf-shadow-sm)]"
              data-state={state}
              animate={reduceMotion ? undefined : { rotate: bookmarkTilt, y: bookmarkY }}
              transition={{ type: "spring", stiffness: 190, damping: 18 }}
            />

            <div aria-hidden="true" className="absolute left-[5.4rem] top-[6.8rem] z-30 flex w-28 items-center justify-center gap-6">
              <motion.span
                className="h-3 w-3 rounded-full bg-[var(--wf-text)]"
                animate={reduceMotion ? undefined : { x: eyeX, y: eyeY, scaleY: state === "passwordFocus" ? 0.18 : 1 }}
                transition={{ type: "spring", stiffness: 260, damping: 22 }}
              />
              <motion.span
                className="h-3 w-3 rounded-full bg-[var(--wf-text)]"
                animate={reduceMotion ? undefined : { x: eyeX, y: eyeY, scaleY: state === "passwordFocus" ? 0.18 : 1 }}
                transition={{ type: "spring", stiffness: 260, damping: 22 }}
              />
            </div>

            <motion.div
              aria-hidden="true"
              className="absolute left-[5.35rem] top-[8.25rem] z-30 h-1.5 w-20 rounded-full bg-[var(--wf-text-secondary)]"
              animate={reduceMotion ? undefined : { rotate: state === "error" ? 180 : 0, scaleX: state === "success" ? 0.62 : 1 }}
              transition={{ duration: 0.26, ease: "easeOut" }}
            />

            {state === "success" ? (
              <motion.div
                aria-hidden="true"
                className="absolute right-7 top-10 z-40 rounded-full border border-[var(--wf-border)] bg-[var(--wf-surface)] px-2 py-1 text-[10px] font-semibold text-[var(--wf-accent)] shadow-[var(--wf-shadow-sm)]"
                initial={reduceMotion ? false : { opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
              >
                saved
              </motion.div>
            ) : null}

            <div
              aria-hidden="true"
              className="absolute bottom-6 left-16 rounded-full border border-[var(--wf-border)] bg-[var(--wf-surface)] px-3 py-1 text-[11px] tabular-nums text-[var(--wf-text-tertiary)] shadow-[var(--wf-shadow-sm)]"
            >
              {state === "success" ? "00:00 saved" : state === "error" ? "retry 00:08" : "note 01:24"}
            </div>
            <p className="sr-only">{label}</p>
            <div className="absolute bottom-0 left-1/2 -translate-x-1/2 rounded-full border border-[var(--wf-border)] bg-[var(--wf-surface)] px-4 py-2 text-xs text-[var(--wf-text-secondary)] shadow-[var(--wf-shadow-sm)]">
              {label}
            </div>
          </motion.div>

          <div className="rounded-[1.35rem] border border-[var(--wf-border)] bg-[color-mix(in_srgb,var(--wf-surface)_82%,transparent)] p-4 shadow-[var(--wf-shadow-sm)]">
            <p className="text-xs font-semibold text-[var(--wf-text)]">最近笔记</p>
            <div className="mt-3 space-y-3">
              {RECENT_NOTES.map((note) => (
                <div key={note.time} className="flex items-start gap-3 text-xs">
                  <span className="font-mono tabular-nums text-[var(--wf-accent)]">{note.time}</span>
                  <span className="leading-5 text-[var(--wf-text-secondary)]">{note.text}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
