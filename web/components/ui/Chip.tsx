import { forwardRef, type HTMLAttributes } from "react";
import clsx from "clsx";

export interface ChipProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: "neutral" | "accent" | "danger";
  size?: "sm" | "md";
}

export const Chip = forwardRef<HTMLSpanElement, ChipProps>(function Chip(
  { className, variant = "neutral", size = "md", ...props },
  ref,
) {
  return <span {...props} ref={ref} data-size={size} data-variant={variant} className={clsx("wf-chip", className)} />;
});

export default Chip;
