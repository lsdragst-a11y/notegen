"use client";

import { BrandMark } from "@/components/brand/BrandMark";

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

function stateLabel(state: AccountCompanionState) {
  if (state === "success") return "纸页角色把书签归档完成";
  if (state === "error") return "纸页角色停在错误时间戳旁";
  if (state === "passwordReveal") return "纸页角色从书签旁确认密码可见";
  if (state === "passwordFocus") return "纸页角色用书签遮住密码行";
  if (state === "emailFocus") return "纸页角色看向邮箱时间戳";
  return "纸页角色安静等待输入";
}

export function AccountCompanion({ state, variant }: AccountCompanionProps) {
  const isRegister = variant === "register";
  const label = stateLabel(state);

  return (
    <section
      aria-label={isRegister ? "NoteGen 注册角色入口" : "NoteGen 登录角色入口"}
      className="relative hidden min-h-[34rem] overflow-hidden rounded-[2rem] border border-[var(--wf-border)]
                 bg-[linear-gradient(135deg,color-mix(in_srgb,var(--wf-surface)_96%,transparent),color-mix(in_srgb,var(--wf-canvas)_78%,transparent))]
                 p-8 shadow-[var(--wf-shadow-lg)] lg:block"
    >
      <div className="relative z-10 flex h-full flex-col justify-between">
        <div>
          <BrandMark variant="full" size="sm" label="NoteGen" />
          <p className="mt-8 text-xs font-semibold uppercase tracking-[0.22em] text-[var(--wf-accent)]">
            {isRegister ? "Create first notebook" : "Back to your notebook"}
          </p>
          <h1 className="mt-4 max-w-lg font-[var(--wf-font-display)] text-5xl font-semibold leading-[1.02] tracking-[-0.04em]">
            {isRegister ? "给第一本视频笔记留一个位置" : "回到你的时间线和笔记页"}
          </h1>
          <p className="mt-5 max-w-md text-sm leading-7 text-[var(--wf-text-secondary)]">
            {isRegister
              ? "创建账号后，视频、章节、提问和复习进度会收进同一个私有空间。"
              : "登录后继续从视频时间点回到笔记、书签和问答记录。"}
          </p>
        </div>

        <div
          data-testid="account-companion"
          data-state={state}
          className="relative mx-auto mt-8 h-64 w-72"
        >
          <div
            aria-hidden="true"
            className="absolute left-8 top-6 h-[12.5rem] w-44 rotate-[-6deg] rounded-[1.35rem] border border-[var(--wf-border-strong)]
                       bg-[var(--wf-surface)] shadow-[var(--wf-shadow-md)] transition-transform duration-300 ease-out
                       data-[state=success]:rotate-[-3deg] motion-reduce:transition-none"
            data-state={state}
          >
            <div className="absolute right-0 top-0 h-16 w-16 rounded-bl-[1.1rem] rounded-tr-[1.35rem] bg-[color-mix(in_srgb,var(--wf-caramel)_24%,var(--wf-surface))]" />
            <div className="absolute left-6 top-8 h-2 w-24 rounded-full bg-[var(--wf-surface-muted)]" />
            <div className="absolute left-6 top-14 h-2 w-20 rounded-full bg-[var(--wf-surface-muted)]" />
            <div className="absolute left-6 top-24 h-2 w-28 rounded-full bg-[color-mix(in_srgb,var(--wf-brand-coral)_18%,var(--wf-surface-muted))]" />
            <div className="absolute bottom-8 left-6 h-1.5 w-[7.5rem] rounded-full bg-[color-mix(in_srgb,var(--wf-brand-coral)_40%,var(--wf-surface-muted))]" />
          </div>

          <div
            aria-hidden="true"
            className="absolute right-[3.75rem] top-16 h-32 w-7 rounded-full bg-[var(--wf-brand-coral)] shadow-[var(--wf-shadow-sm)]
                       transition-transform duration-300 ease-out data-[state=passwordFocus]:-rotate-12
                       data-[state=passwordReveal]:rotate-12 data-[state=error]:-translate-y-1
                       data-[state=success]:-translate-y-3 data-[state=success]:rotate-12 motion-reduce:translate-y-0 motion-reduce:rotate-0 motion-reduce:transition-none"
            data-state={state}
          />

          <svg
            aria-hidden="true"
            viewBox="0 0 160 120"
            className="absolute left-14 top-20 h-32 w-44 overflow-visible"
          >
            <g className="transition-transform duration-300 ease-out motion-reduce:transition-none" data-state={state}>
              <circle cx="54" cy="42" r="6" fill="var(--wf-text)" />
              <circle cx="94" cy="42" r="6" fill="var(--wf-text)" />
              <path
                d={state === "error" ? "M58 70 Q74 62 92 70" : "M58 66 Q74 76 92 66"}
                fill="none"
                stroke="var(--wf-text-secondary)"
                strokeWidth="5"
                strokeLinecap="round"
              />
              {(state === "passwordFocus" || state === "passwordReveal") && (
                <rect
                  x="40"
                  y={state === "passwordReveal" ? 38 : 32}
                  width="70"
                  height="16"
                  rx="8"
                  fill="color-mix(in_srgb,var(--wf-brand-coral)_24%,var(--wf-surface))"
                  stroke="var(--wf-border)"
                />
              )}
              {state === "emailFocus" && (
                <path
                  d="M112 34 h18 m-9 -9 v18"
                  stroke="var(--wf-accent)"
                  strokeWidth="5"
                  strokeLinecap="round"
                />
              )}
              {state === "success" && (
                <path
                  d="M110 34 l8 8 l18 -22"
                  fill="none"
                  stroke="var(--wf-accent)"
                  strokeWidth="6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              )}
            </g>
          </svg>

          <div
            aria-hidden="true"
            className="absolute bottom-5 left-16 rounded-full border border-[var(--wf-border)] bg-[var(--wf-surface)] px-3 py-1 text-[11px] tabular-nums text-[var(--wf-text-tertiary)] shadow-[var(--wf-shadow-sm)]"
          >
            {state === "success" ? "00:00 saved" : state === "error" ? "retry 00:08" : "note 01:24"}
          </div>
          <p className="sr-only">{label}</p>
          <div className="absolute bottom-0 left-1/2 -translate-x-1/2 rounded-full border border-[var(--wf-border)] bg-[var(--wf-surface)] px-4 py-2 text-xs text-[var(--wf-text-secondary)] shadow-[var(--wf-shadow-sm)]">
            {label}
          </div>
        </div>
      </div>
    </section>
  );
}
