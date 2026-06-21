import type { Chapter, Chunk, DisplayLang, NoteMeta, Overview } from "./types";
import { formatTime } from "./notes";
import { API_BASE, ApiError, parseError } from "./api";

/** lib 层的双语字段选择（不依赖组件层 LangContext 的 pickByLang，避免反向 import）。 */
function pick(obj: Record<string, unknown>, field: string, lang: DisplayLang): string {
  const v = obj[`${field}_${lang}`];
  if (typeof v === "string" && v) return v;
  const base = obj[field];
  return typeof base === "string" ? base : "";
}

export interface ExportInput {
  title: string;
  meta: NoteMeta | null;
  overview: Overview | null;
  chapters: Chapter[];
  summary: Chunk[];
  lang: DisplayLang;
}

/**
 * 把笔记 bundle 拼成可下载的 Markdown（右栏「导出 Markdown」用）。
 * 结构与 backend to_markdown 的学习场景版对齐：标题 → 来源 → 概览 → 章节（含小节与知识点时间戳）。
 */
export function buildMarkdown({ title, meta, overview, chapters, summary, lang }: ExportInput): string {
  const en = lang === "en";
  const lines: string[] = [`# ${title}`, ""];

  if (meta?.webpage_url) {
    lines.push(`> ${en ? "Source" : "来源"}: ${meta.webpage_url}`);
  }
  if (meta?.uploader) {
    lines.push(`> ${en ? "Uploader" : "UP 主"}: ${meta.uploader}`);
  }
  lines.push("");

  if (overview) {
    const sum = pick(overview as unknown as Record<string, unknown>, "summary", lang);
    if (sum) {
      lines.push(`## ${en ? "Overview" : "本视频讲了什么"}`, "", sum, "");
    }
    const tk = (en ? overview.takeaways_en : overview.takeaways_zh) ?? overview.takeaways;
    if (tk?.length) {
      lines.push(`**${en ? "You will learn" : "你将学到"}**`, "");
      tk.forEach(t => lines.push(`- ${t}`));
      lines.push("");
    }
  }

  const renderChunkLine = (idx: number) => {
    const c = summary[idx];
    if (!c) return;
    const headline = pick(c as unknown as Record<string, unknown>, "headline", lang)
      || (c.text || "").slice(0, 30);
    lines.push(`- [${formatTime(c.start)}] ${headline}`);
  };

  chapters.forEach((ch, ci) => {
    const chTitle = pick(ch as unknown as Record<string, unknown>, "title", lang);
    lines.push(`## ${ci + 1}. ${chTitle}（${formatTime(ch.start)} - ${formatTime(ch.end)}）`, "");
    const ab = pick(ch as unknown as Record<string, unknown>, "abstract", lang);
    if (ab) lines.push(ab, "");
    if (ch.children?.length) {
      ch.children.forEach((sub, si) => {
        const subTitle = pick(sub as unknown as Record<string, unknown>, "title", lang);
        lines.push(`### ${ci + 1}.${si + 1} ${subTitle}（${formatTime(sub.start)}）`, "");
        const sab = pick(sub as unknown as Record<string, unknown>, "abstract", lang);
        if (sab) lines.push(sab, "");
        sub.indices.forEach(renderChunkLine);
        lines.push("");
      });
    } else {
      ch.indices.forEach(renderChunkLine);
      lines.push("");
    }
  });

  return lines.join("\n");
}

/** 触发浏览器下载（client-only）。 */
function downloadBlob(filename: string, blob: Blob): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function downloadMarkdown(filename: string, content: string): void {
  downloadBlob(
    filename.endsWith(".md") ? filename : `${filename}.md`,
    new Blob([content], { type: "text/markdown;charset=utf-8" }),
  );
}

/**
 * 导出 Word：把 buildMarkdown 的产物 POST 给后端转 .docx（POST /api/export/docx）。
 * 免登录（分享只读页同样可用）；失败抛 ApiError 由调用方提示。
 */
export async function downloadDocx(filename: string, markdown: string): Promise<void> {
  const r = await fetch(`${API_BASE}/api/export/docx`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ markdown, filename }),
  });
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
  downloadBlob(
    filename.endsWith(".docx") ? filename : `${filename}.docx`,
    await r.blob(),
  );
}
