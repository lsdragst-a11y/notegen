import type { SVGAttributes } from "react";

import {
  FOLD_PATHS,
  INK_PATHS,
  LOGO_VIEWBOX,
  LOGO_WIDTH,
  POINTER_BAND,
  POINTER_TRIANGLE,
  WORDMARK_PATH,
} from "./brandPaths";

type BrandMarkVariant = "mark" | "full";
type BrandMarkSize = "sm" | "md" | "lg" | number;

export interface BrandMarkProps extends Omit<SVGAttributes<SVGSVGElement>, "aria-label"> {
  variant?: BrandMarkVariant;
  size?: BrandMarkSize;
  label?: string;
}

const MARK_SIZE = {
  sm: 16,
  md: 24,
  lg: 32,
} as const;

const LOGO_SIZE = {
  sm: 120,
  md: 148,
  lg: 176,
} as const;

function resolveSize(size: BrandMarkSize, variant: BrandMarkVariant) {
  if (typeof size === "number") return size;
  return variant === "full" ? LOGO_SIZE[size] : MARK_SIZE[size];
}

export function BrandMark({
  className,
  label,
  size = "md",
  variant = "mark",
  ...props
}: BrandMarkProps) {
  const resolvedSize = resolveSize(size, variant);
  const isFull = variant === "full";
  const aspectRatio = isFull ? LOGO_WIDTH / 64 : 1;
  const width = resolvedSize;
  const height = Math.round(resolvedSize / aspectRatio);
  const accessibilityProps = label
    ? ({ role: "img", "aria-label": label } as const)
    : ({ "aria-hidden": true } as const);

  return (
    <svg
      {...props}
      {...accessibilityProps}
      className={className}
      width={width}
      height={height}
      viewBox={isFull ? LOGO_VIEWBOX : "0 0 64 64"}
      xmlns="http://www.w3.org/2000/svg"
      data-min-size={isFull ? undefined : 16}
      data-min-width={isFull ? 120 : undefined}
    >
      <path data-part="ink" fill="currentColor" d={INK_PATHS.join(" ")} />
      <path data-part="fold" fill="var(--wf-caramel, #8B5A35)" d={FOLD_PATHS.join(" ")} />
      <path data-part="pointer" fill="var(--wf-brand-coral, #B65C3A)" d={POINTER_BAND} />
      <path data-part="pointer" fill="var(--wf-brand-coral, #B65C3A)" d={POINTER_TRIANGLE} />
      {isFull ? <path data-part="wordmark" fill="currentColor" d={WORDMARK_PATH} /> : null}
    </svg>
  );
}
