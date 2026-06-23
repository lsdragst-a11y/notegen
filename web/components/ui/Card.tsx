import { forwardRef, type HTMLAttributes } from "react";
import clsx from "clsx";

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: "surface" | "muted" | "outlined";
  padding?: "none" | "sm" | "md" | "lg";
}

export const Card = forwardRef<HTMLDivElement, CardProps>(function Card(
  { className, variant = "surface", padding = "md", ...props },
  ref,
) {
  return (
    <div
      {...props}
      ref={ref}
      data-padding={padding}
      data-variant={variant}
      className={clsx("wf-card", className)}
    />
  );
});

export default Card;
