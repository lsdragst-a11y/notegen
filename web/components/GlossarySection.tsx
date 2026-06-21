"use client";
import { ChevronDown } from "lucide-react";
import type { GlossaryEntry } from "@/lib/notes";
import { useLang } from "./LangContext";
import GlossaryList from "./GlossaryList";

interface Props {
  glossary: GlossaryEntry[];
  defaultOpen: boolean;
  onSeek: (sec: number) => void;
}

/** 术语表折叠区。从 NotesContent 拆出，纯展示。 */
export default function GlossarySection({ glossary, defaultOpen, onSeek }: Props) {
  const { lang } = useLang();
  return (
    <section>
      <details open={defaultOpen} className="group">
        <summary className="text-lg font-semibold mb-3 text-[var(--fg)]
                            cursor-pointer list-none flex items-center gap-2">
          <ChevronDown size={16} className="transition-transform group-open:rotate-0 -rotate-90" />
          {lang === "en" ? "📚 Glossary" : "📚 术语表"}
          <span className="text-xs font-normal text-[var(--fg-tertiary)]">
            {glossary.length} {lang === "en" ? "terms" : "项"}
          </span>
        </summary>
        <GlossaryList glossary={glossary} onSeek={onSeek} />
      </details>
    </section>
  );
}
