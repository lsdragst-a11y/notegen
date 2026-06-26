import { forwardRef, type ButtonHTMLAttributes } from "react";
import { LoaderCircle } from "lucide-react";
import clsx from "clsx";

type NativeIconButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "aria-label">;

export interface IconButtonProps extends NativeIconButtonProps {
  "aria-label": string;
  variant?: "primary" | "ghost" | "secondary" | "danger";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  {
    className,
    children,
    disabled,
    loading = false,
    size = "md",
    type = "button",
    variant = "ghost",
    ...props
  },
  ref,
) {
  return (
    <button
      {...props}
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      data-loading={loading || undefined}
      data-size={size}
      data-variant={variant}
      className={clsx("wf-icon-button", className)}
    >
      <span className="wf-icon-button__content">{children}</span>
      {loading ? <LoaderCircle className="wf-icon-button__spinner" aria-hidden="true" focusable="false" /> : null}
    </button>
  );
});

export default IconButton;
