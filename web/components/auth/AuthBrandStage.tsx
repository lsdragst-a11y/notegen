"use client";

import { BrandMark } from "@/components/brand/BrandMark";

export type AuthFocus = "email" | "password" | "idle";
export type AuthStatus = "idle" | "error" | "success";

interface AuthBrandStageProps {
  focus: AuthFocus;
  passwordVisible: boolean;
  status: AuthStatus;
  variant: "login" | "register";
}

function stateLabel(focus: AuthFocus, passwordVisible: boolean, status: AuthStatus) {
  if (status === "success") return "角色轻碰书签庆祝";
  if (focus === "password" && passwordVisible) return "角色从指缝里偷看";
  if (focus === "password") return "角色遮住眼睛";
  if (focus === "email") return "角色视线跟随邮箱输入";
  return "角色安静等待输入";
}

function eyeState(focus: AuthFocus, passwordVisible: boolean) {
  if (focus !== "password") return "tracking";
  return passwordVisible ? "peek" : "covered";
}

export function AuthBrandStage({ focus, passwordVisible, status, variant }: AuthBrandStageProps) {
  const label = stateLabel(focus, passwordVisible, status);
  const eye = eyeState(focus, passwordVisible);
  const isRegister = variant === "register";

  return (
    <section
      aria-label={isRegister ? "NoteGen 注册品牌互动区" : "NoteGen 登录品牌互动区"}
      className="relative hidden min-h-[34rem] overflow-hidden rounded-[2rem] border border-[var(--wf-border)]
                 bg-[radial-gradient(circle_at_22%_18%,color-mix(in_srgb,var(--wf-brand-coral)_20%,transparent),transparent_34%),linear-gradient(135deg,color-mix(in_srgb,var(--wf-surface)_92%,transparent),color-mix(in_srgb,var(--wf-canvas)_72%,transparent))]
                 p-8 shadow-[var(--wf-shadow-lg)] lg:block"
    >
      <div
        aria-hidden="true"
        className="absolute left-[-12%] top-16 h-20 w-[124%] rotate-[-8deg] rounded-full
                   border border-[color-mix(in_srgb,var(--wf-brand-coral)_32%,transparent)]
                   bg-[linear-gradient(90deg,transparent,color-mix(in_srgb,var(--wf-brand-coral)_18%,transparent),transparent)]
                   blur-[0.2px] transition-transform duration-500 ease-out hover:translate-y-1"
      />
      <div
        aria-hidden="true"
        className="absolute bottom-12 right-[-16%] h-24 w-[112%] rotate-[10deg] rounded-full
                   border border-[color-mix(in_srgb,var(--wf-caramel)_30%,transparent)]
                   bg-[linear-gradient(90deg,transparent,color-mix(in_srgb,var(--wf-caramel)_14%,transparent),transparent)]"
      />

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
          data-testid="auth-character"
          data-eye-state={eye}
          data-status={status}
          className="relative mx-auto mt-8 h-64 w-72"
        >
          <div className="absolute left-10 top-8 h-48 w-40 rotate-[-7deg] rounded-[1.4rem] border border-[var(--wf-border-strong)] bg-[var(--wf-surface)] shadow-[var(--wf-shadow-md)]">
            <div className="absolute right-0 top-0 h-16 w-16 rounded-bl-[1.2rem] rounded-tr-[1.4rem] bg-[color-mix(in_srgb,var(--wf-caramel)_22%,var(--wf-surface))]" />
            <div className="absolute left-6 top-8 h-2 w-24 rounded-full bg-[var(--wf-surface-muted)]" />
            <div className="absolute left-6 top-14 h-2 w-20 rounded-full bg-[var(--wf-surface-muted)]" />
            <div className="absolute bottom-7 left-6 h-1.5 w-28 rounded-full bg-[color-mix(in_srgb,var(--wf-brand-coral)_40%,var(--wf-surface-muted))]" />
          </div>

          <div className="absolute left-[5.7rem] top-[6.6rem] flex gap-7">
            <span
              className={`h-3 w-3 rounded-full bg-[var(--wf-text)] transition-transform duration-300 ${
                focus === "email" ? "translate-x-1" : ""
              } ${eye === "covered" ? "scale-y-0" : eye === "peek" ? "scale-y-50" : ""}`}
            />
            <span
              className={`h-3 w-3 rounded-full bg-[var(--wf-text)] transition-transform duration-300 ${
                focus === "email" ? "translate-x-1" : ""
              } ${eye === "covered" ? "scale-y-0" : eye === "peek" ? "scale-y-50" : ""}`}
            />
          </div>

          <div
            className={`absolute left-[5.25rem] top-[6.15rem] h-8 w-28 rounded-full border border-[var(--wf-border)]
                        bg-[color-mix(in_srgb,var(--wf-brand-coral)_18%,var(--wf-surface))]
                        transition-all duration-300 ${
                          eye === "covered" ? "opacity-100 translate-y-0" : eye === "peek" ? "opacity-80 translate-y-1" : "opacity-0 translate-y-5"
                        }`}
          />

          <div
            className={`absolute right-14 top-20 h-28 w-6 rounded-full bg-[var(--wf-brand-coral)] shadow-[var(--wf-shadow-sm)]
                        transition-transform duration-300 ${
                          status === "success" ? "rotate-12 translate-y-[-0.4rem]" : status === "error" ? "rotate-[-8deg]" : ""
                        }`}
          />
          <p className="sr-only">{label}</p>
          <div className="absolute bottom-0 left-1/2 -translate-x-1/2 rounded-full border border-[var(--wf-border)] bg-[var(--wf-surface)] px-4 py-2 text-xs text-[var(--wf-text-secondary)] shadow-[var(--wf-shadow-sm)]">
            {label}
          </div>
        </div>
      </div>
    </section>
  );
}
