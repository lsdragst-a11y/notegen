"use client";
import { useLang } from "./LangContext";

/**
 * 中英切换 toggle。固定 60px 宽，活跃语言高亮。
 * 切换写 localStorage，下次访问保留。
 */
export default function LangToggle() {
  const { lang, setLang } = useLang();
  return (
    <div className="inline-flex items-center rounded-md border border-[var(--border)]
                    bg-[var(--surface)] text-xs overflow-hidden">
      <button
        onClick={() => setLang("zh")}
        className={`px-2 py-1 transition-colors ${
          lang === "zh"
            ? "bg-[var(--accent)] text-white font-medium"
            : "text-[var(--text-2)] hover:bg-[var(--surface-2)]"
        }`}
        aria-pressed={lang === "zh"}
        title="切换为中文显示"
      >
        中
      </button>
      <button
        onClick={() => setLang("en")}
        className={`px-2 py-1 transition-colors ${
          lang === "en"
            ? "bg-[var(--accent)] text-white font-medium"
            : "text-[var(--text-2)] hover:bg-[var(--surface-2)]"
        }`}
        aria-pressed={lang === "en"}
        title="Switch to English"
      >
        EN
      </button>
    </div>
  );
}
