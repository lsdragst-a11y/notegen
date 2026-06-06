"use client";
import { motion } from "framer-motion";
import { FileText, Sparkles } from "lucide-react";
import type { Overview } from "@/lib/types";
import { useLang, pickByLang } from "./LangContext";

interface Props {
  overview: Overview;
}

/**
 * 文档级「全文总结」hero：散文概览 + 「你将学到」要点。
 * overview / takeaways 走 lang fallback（缺 _en 回退中文），无 overview 时不渲染。
 * 章节结构的可视化已交给左栏 ChapterNav + 知识点幻灯片画廊，本卡专注散文总结。
 */
export default function OverviewHero({ overview }: Props) {
  const { lang } = useLang();
  const summary = pickByLang(overview, "summary", lang);
  const takeaways = (() => {
    const t = (overview as unknown as Record<string, unknown>)[`takeaways_${lang}`];
    if (Array.isArray(t) && t.length) return t as string[];
    return overview.takeaways || [];
  })();
  if (!summary && takeaways.length === 0) return null;

  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 200, damping: 24, delay: 0.05 }}
      className="apple-card p-6"
    >
      <h2 className="flex items-center gap-2 text-base font-semibold text-[var(--fg)]">
        <FileText size={16} className="text-[var(--accent)]" />
        {lang === "en" ? "Overview" : "全文总结"}
      </h2>
      {summary && (
        <p className="mt-2.5 text-sm leading-relaxed text-[var(--fg-secondary)]">
          {summary}
        </p>
      )}

      {takeaways.length > 0 && (
        <div className="mt-4">
          <div className="flex items-center gap-1.5 text-sm font-medium text-[var(--fg)]">
            <Sparkles size={13} className="text-[var(--accent)]" />
            {lang === "en" ? "What you'll learn" : "你将学到"}
          </div>
          <ul className="mt-2 flex flex-col gap-1.5">
            {takeaways.map((t, i) => (
              <li key={i}
                  className="flex gap-2 text-sm text-[var(--fg-secondary)] leading-snug">
                <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--accent)]" />
                <span>{t}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </motion.section>
  );
}
