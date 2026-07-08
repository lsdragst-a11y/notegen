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
    heroLabel: user ? "进入笔记库" : "把视频放入时间线",
    heroHint: user ? "打开已生成的学习笔记" : "上传课程、讲座或教程",
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
    <div className="wf-hero-upload-row mt-7">
      <Link href={cta.href} className="wf-upload-timeline-control" aria-label={cta.heroLabel}>
        <span className="wf-upload-timeline-control__icon">
          <UploadCloud size={18} aria-hidden="true" />
        </span>
        <span className="wf-upload-timeline-control__copy">
          <span>{cta.heroLabel}</span>
          <small>{cta.heroHint}</small>
        </span>
        <span className="wf-upload-timeline-control__playhead" aria-hidden="true">
          <ArrowRight size={16} />
        </span>
      </Link>
      <Link href="/notebooks?filter=public" className="wf-upload-demo-link">
        观看 30 秒演示
      </Link>
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
