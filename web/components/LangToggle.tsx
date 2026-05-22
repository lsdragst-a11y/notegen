"use client";
import { useLang } from "./LangContext";
import type { DisplayLang } from "@/lib/types";

/**
 * 中英切换 toggle。pill 风格 segmented control，与 ThemeToggle 视觉对齐。
 * 切换写 localStorage，下次访问保留。
 */
const OPTS: { v: DisplayLang; label: string; title: string }[] = [
  { v: "zh", label: "中", title: "切换为中文显示" },
  { v: "en", label: "EN", title: "Switch to English" },
];

export default function LangToggle() {
  const { lang, setLang } = useLang();
  return (
    <div
      className="inline-flex items-center rounded-full bg-[var(--bg-muted)] p-0.5 gap-0.5"
      role="radiogroup"
      aria-label="显示语言"
    >
      {OPTS.map(o => {
        const active = lang === o.v;
        return (
          <button
            key={o.v}
            onClick={() => setLang(o.v)}
            role="radio"
            aria-checked={active}
            title={o.title}
            className={`min-w-[28px] h-7 px-2 rounded-full text-[11px] font-medium tabular-nums
                        inline-flex items-center justify-center transition-colors
                        ${active
                          ? "bg-[var(--bg-elevated)] text-[var(--fg)] shadow-[var(--shadow-sm)]"
                          : "text-[var(--fg-tertiary)] hover:text-[var(--fg-secondary)]"}`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
