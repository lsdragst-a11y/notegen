"use client";
import { useEffect, useState } from "react";
import { Sun, Moon, Monitor } from "lucide-react";

type Theme = "light" | "dark" | "system";

function resolve(t: Theme): "light" | "dark" {
  if (t === "system") {
    return typeof window !== "undefined" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return t;
}

function applyTheme(t: Theme) {
  if (typeof document === "undefined") return;
  document.documentElement.setAttribute("data-theme", resolve(t));
  if (t === "system") localStorage.removeItem("theme");
  else localStorage.setItem("theme", t);
}

/**
 * Light / System / Dark 三态切换。
 * - 持久化到 localStorage（system 模式不写入，依赖 matchMedia）
 * - layout.tsx inline script 已在 hydration 前设好初始 data-theme（避免闪烁）
 * - system 模式下监听系统色变更
 */
export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("system");

  useEffect(() => {
    const saved = (localStorage.getItem("theme") as Theme | null) || "system";
    setTheme(saved);
  }, []);

  useEffect(() => {
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => applyTheme("system");
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [theme]);

  function pick(t: Theme) {
    setTheme(t);
    applyTheme(t);
  }

  const opts: { v: Theme; Icon: typeof Sun; label: string }[] = [
    { v: "light", Icon: Sun, label: "浅色" },
    { v: "system", Icon: Monitor, label: "跟随系统" },
    { v: "dark", Icon: Moon, label: "深色" },
  ];

  return (
    <div className="inline-flex items-center rounded-full bg-[var(--bg-muted)] p-0.5 gap-0.5"
         role="radiogroup" aria-label="主题">
      {opts.map(o => (
        <button
          key={o.v}
          onClick={() => pick(o.v)}
          aria-label={o.label}
          aria-checked={theme === o.v}
          role="radio"
          title={o.label}
          className={`grid place-items-center w-7 h-7 rounded-full transition-colors
                      ${theme === o.v
                        ? "bg-[var(--bg-elevated)] text-[var(--fg)] shadow-[var(--shadow-sm)]"
                        : "text-[var(--fg-tertiary)] hover:text-[var(--fg-secondary)]"}`}
        >
          <o.Icon size={13} />
        </button>
      ))}
    </div>
  );
}
