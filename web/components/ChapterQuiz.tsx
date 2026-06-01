"use client";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check, X } from "lucide-react";
import type { Quiz, QuizQuestion } from "@/lib/types";
import { useLang } from "./LangContext";

const GREEN = "#30d158";
const RED = "#ff375f";

function Explanation({ text }: { text?: string }) {
  if (!text) return null;
  return (
    <motion.div
      key="exp"
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      exit={{ opacity: 0, height: 0 }}
      className="mt-2 overflow-hidden text-xs leading-relaxed
                 text-[var(--fg-secondary)] border-l-2 border-[var(--border)] pl-3"
    >
      {text}
    </motion.div>
  );
}

function McQuestion({ q, idx }: { q: Extract<QuizQuestion, { type: "mc" }>; idx: number }) {
  const [selected, setSelected] = useState<number | null>(null);
  const answered = selected !== null;
  return (
    <div className="rounded-xl bg-[var(--bg-muted)] p-3">
      <div className="mb-2 text-sm font-medium text-[var(--fg)]">
        <span className="mr-1.5 text-[var(--fg-tertiary)] tabular-nums">{idx + 1}.</span>
        {q.q}
      </div>
      <div className="flex flex-col gap-1.5">
        {q.options.map((opt, oi) => {
          const isCorrect = oi === q.answer_idx;
          const isChosen = oi === selected;
          let style: React.CSSProperties = {};
          let icon: React.ReactNode = null;
          if (answered && isCorrect) { style = { borderColor: GREEN, color: GREEN }; icon = <Check size={13} />; }
          else if (answered && isChosen && !isCorrect) { style = { borderColor: RED, color: RED }; icon = <X size={13} />; }
          return (
            <button
              key={oi}
              onClick={() => setSelected(oi)}
              style={style}
              className="flex items-center gap-2 rounded-lg border border-[var(--border)]
                         px-3 py-2 text-left text-sm transition-colors hover:border-[var(--accent)]"
            >
              <span className="w-4 shrink-0">{icon}</span>
              <span>{opt}</span>
            </button>
          );
        })}
      </div>
      <AnimatePresence>{answered && <Explanation text={q.explanation} />}</AnimatePresence>
    </div>
  );
}

function TfQuestion({ q, idx }: { q: Extract<QuizQuestion, { type: "tf" }>; idx: number }) {
  const { lang } = useLang();
  const [selected, setSelected] = useState<boolean | null>(null);
  const answered = selected !== null;
  const choices: { val: boolean; label: string }[] = [
    { val: true, label: lang === "en" ? "True" : "对" },
    { val: false, label: lang === "en" ? "False" : "错" },
  ];
  return (
    <div className="rounded-xl bg-[var(--bg-muted)] p-3">
      <div className="mb-2 text-sm font-medium text-[var(--fg)]">
        <span className="mr-1.5 text-[var(--fg-tertiary)] tabular-nums">{idx + 1}.</span>
        {q.q}
      </div>
      <div className="flex gap-2">
        {choices.map(c => {
          const isCorrect = c.val === q.answer;
          const isChosen = c.val === selected;
          let style: React.CSSProperties = {};
          let icon: React.ReactNode = null;
          if (answered && isCorrect) { style = { borderColor: GREEN, color: GREEN }; icon = <Check size={13} />; }
          else if (answered && isChosen && !isCorrect) { style = { borderColor: RED, color: RED }; icon = <X size={13} />; }
          return (
            <button
              key={String(c.val)}
              onClick={() => setSelected(c.val)}
              style={style}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)]
                         px-4 py-1.5 text-sm transition-colors hover:border-[var(--accent)]"
            >
              {icon}{c.label}
            </button>
          );
        })}
      </div>
      <AnimatePresence>{answered && <Explanation text={q.explanation} />}</AnimatePresence>
    </div>
  );
}

export default function ChapterQuiz({ quiz }: { quiz: Quiz }) {
  return (
    <div className="mt-3 flex flex-col gap-2">
      {quiz.questions.map((q, i) =>
        q.type === "mc"
          ? <McQuestion key={i} q={q} idx={i} />
          : <TfQuestion key={i} q={q} idx={i} />
      )}
    </div>
  );
}
