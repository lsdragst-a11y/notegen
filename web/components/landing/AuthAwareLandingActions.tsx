"use client";

import Link from "next/link";
import { ArrowRight, UploadCloud } from "lucide-react";
import type { ReactNode } from "react";

import { useAuth } from "@/components/AuthContext";

type ButtonVariant = "primary" | "secondary" | "ghost";

function LandingLinkButton({
  children,
  href,
  variant = "primary",
  size = "lg",
  className,
}: {
  children: ReactNode;
  href: string;
  variant?: ButtonVariant;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  return (
    <Link className={`wf-button wf-brand-button ${className ?? ""}`} data-size={size} data-variant={variant} href={href}>
      <span className="wf-button__content">{children}</span>
    </Link>
  );
}

function useLandingCta() {
  const { user } = useAuth();

  return {
    href: user ? "/notebooks" : "/login?next=/notebooks",
    navLabel: user ? "进入笔记库" : "开始使用",
    heroLabel: user ? "进入笔记库" : "上传视频生成笔记",
    finalLabel: user ? "进入笔记库" : "创建第一本视频笔记",
  };
}

export function AuthAwareNavAction() {
  const cta = useLandingCta();

  return (
    <LandingLinkButton href={cta.href} size="sm">
      {cta.navLabel}
    </LandingLinkButton>
  );
}

export function AuthAwareHeroActions() {
  const cta = useLandingCta();

  return (
    <div className="wf-hero-cta-row mt-8 flex flex-col gap-3 sm:flex-row">
      <LandingLinkButton href={cta.href} className="wf-timeline-cta">
        <UploadCloud size={16} aria-hidden="true" />
        {cta.heroLabel}
      </LandingLinkButton>
      <LandingLinkButton href="/notebooks?filter=public" variant="secondary" className="wf-secondary-cta">
        观看 30 秒演示
      </LandingLinkButton>
    </div>
  );
}

export function AuthAwareFinalAction() {
  const cta = useLandingCta();

  return (
    <LandingLinkButton href={cta.href}>
      {cta.finalLabel} <ArrowRight size={16} aria-hidden="true" />
    </LandingLinkButton>
  );
}
