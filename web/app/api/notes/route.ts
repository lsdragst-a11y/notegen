import { NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

// Next 同源 API。直接 fs 枚举 web/public/notes/ 目录，跟 FastAPI 的
// /api/notes 等价但不依赖 backend 在线。前端 fetchCatalog 优先调这个，
// catalog.json 仅保留为最末兜底（防止 fs 异常时返空白）。
//
// 设计要点：
//   - 缺 summary.json 或 chapters.json 的目录直接跳过（避免半成品出现在 UI）
//   - meta.json 可选，缺失时 title 用目录名 fallback，domain 走 heuristic
//   - 按 mtime 倒序排（新生成的排在前）
//   - Cache-Control: no-store，避免 dev hot reload 后看旧列表

export const dynamic = "force-dynamic";

const NOTES_DIR = path.join(process.cwd(), "public", "notes");
const VIDEOS_DIR = path.join(process.cwd(), "public", "videos");

// category enum → 卡片上展示的中文标签
const CATEGORY_LABEL: Record<string, string> = {
  teaching: "学习",
  popsci: "科普",
  vlog: "Vlog",
  talk: "时评",
};

function guessDomain(title: string, category?: string): string {
  // 优先用 backend 写的 category（启发式 + 术语密度算的），稳过纯标题猜
  if (category && CATEGORY_LABEL[category]) {
    // teaching 再细分到「编程教学/考研专业课/工具教程」，让首页卡片有视觉区分度
    if (category === "teaching") {
      const t = (title || "").toLowerCase();
      if (t.includes("python") || t.includes("代码") || t.includes("编程") ||
          t.includes("agent") || t.includes("vibe")) return "编程教学";
      if (t.includes("考研") || t.includes("操作系统") || t.includes("计算机网络") ||
          t.includes("线代") || t.includes("线性代数")) return "考研专业课";
      if (t.includes("claude")) return "工具教程";
    }
    return CATEGORY_LABEL[category];
  }
  // 无 category 字段的旧笔记 fallback
  const t = (title || "").toLowerCase();
  if (t.includes("python") || t.includes("代码") || t.includes("编程")) return "编程教学";
  if (t.includes("考研") || t.includes("操作系统") || t.includes("计算机网络") ||
      t.includes("线代") || t.includes("线性代数")) return "考研专业课";
  if (t.includes("vlog") || t.includes("日常") || t.includes("外卖")) return "Vlog";
  if (t.includes("评测") || t.includes("iphone") || t.includes("ios")) return "数码评测";
  if (t.includes("claude")) return "工具教程";
  return "学习";
}

interface NoteEntry {
  id: string;
  title: string;
  domain: string;
  duration_sec: number;
  chunks: number;
  chapters: number;
  uploader: string;
  webpage_url: string;
  video_size_mb: number | null;
}

export async function GET() {
  let dirents: { name: string; mtimeMs: number }[];
  try {
    const ents = await fs.readdir(NOTES_DIR, { withFileTypes: true });
    dirents = await Promise.all(
      ents
        .filter(d => d.isDirectory())
        .map(async d => {
          const s = await fs.stat(path.join(NOTES_DIR, d.name));
          return { name: d.name, mtimeMs: s.mtimeMs };
        }),
    );
  } catch {
    return NextResponse.json([], { headers: { "Cache-Control": "no-store" } });
  }
  dirents.sort((a, b) => b.mtimeMs - a.mtimeMs);

  const items: NoteEntry[] = [];
  for (const d of dirents) {
    const dir = path.join(NOTES_DIR, d.name);
    let summary: { end?: number }[];
    let chapters: { chapters?: unknown[] };
    try {
      const [sRaw, cRaw] = await Promise.all([
        fs.readFile(path.join(dir, "summary.json"), "utf-8"),
        fs.readFile(path.join(dir, "chapters.json"), "utf-8"),
      ]);
      summary = JSON.parse(sRaw);
      chapters = JSON.parse(cRaw);
    } catch {
      continue;  // 缺 summary/chapters → 半成品，跳过
    }

    let meta: Record<string, string | number | undefined> = {};
    try {
      meta = JSON.parse(await fs.readFile(path.join(dir, "meta.json"), "utf-8"));
    } catch { /* meta.json optional */ }

    const lastChunk = summary[summary.length - 1];
    const durationSec = lastChunk?.end ? Math.floor(lastChunk.end) : 0;

    let videoSizeMb: number | null = null;
    try {
      const stat = await fs.stat(path.join(VIDEOS_DIR, `${d.name}.mp4`));
      videoSizeMb = +(stat.size / 1024 / 1024).toFixed(1);
    } catch { /* video missing */ }

    items.push({
      id: d.name,
      title: (meta.title as string) || d.name,
      domain: guessDomain((meta.title as string) || "", meta.category as string | undefined),
      duration_sec: durationSec,
      chunks: summary.length,
      chapters: Array.isArray(chapters.chapters) ? chapters.chapters.length : 0,
      uploader: (meta.uploader as string) || "",
      webpage_url: (meta.webpage_url as string) || "",
      video_size_mb: videoSizeMb,
    });
  }
  return NextResponse.json(items, { headers: { "Cache-Control": "no-store" } });
}
