"use client";
import { MessageCircle } from "lucide-react";
import { useLang } from "./LangContext";

/**
 * 「对视频提问」输入条占位（Phase 2，接口契约见 docs/frontend-redesign.md §5）。
 * 后端 /api/notes/{id}/ask 落地后替换为真实 ChatPanel 入口。
 */
export default function AskBar() {
  const { lang } = useLang();
  return (
    <div
      className="flex items-center gap-2.5 rounded-full border border-[var(--border)]
                 bg-[var(--bg-elevated)] px-4 py-3 shadow-[var(--shadow-sm)]"
      aria-disabled="true"
    >
      <MessageCircle size={15} className="shrink-0 text-[var(--fg-tertiary)]" />
      <span className="flex-1 truncate text-sm text-[var(--fg-tertiary)]">
        {lang === "en"
          ? "Ask about this video — answers will cite timestamps…"
          : "对这个视频提问，回答附时间戳引用…"}
      </span>
      <span className="shrink-0 rounded-full bg-[var(--bg-muted)] px-2 py-0.5 text-[11px] text-[var(--fg-secondary)]">
        {lang === "en" ? "Coming soon" : "规划中"}
      </span>
    </div>
  );
}
