import { NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

// 删除笔记：rm web/public/notes/{id}/ + web/public/videos/{id}.mp4。
// 跟 FastAPI delete_note 同义，但前端不再依赖 backend 在线即可删。
// data/raw/ 和 data/outputs/ 下的原始文件留着（节省 ASR 缓存重复计算成本）；
// 想全清需要在 backend 端手动做。

export const dynamic = "force-dynamic";

const NOTES_DIR = path.join(process.cwd(), "public", "notes");
const VIDEOS_DIR = path.join(process.cwd(), "public", "videos");

export async function DELETE(
  _req: Request,
  ctx: { params: Promise<{ id: string }> },
) {
  const { id } = await ctx.params;
  const safe = (id || "").trim();
  if (!safe || safe.includes("/") || safe.includes("\\") || safe.includes("..")) {
    return NextResponse.json({ error: "invalid note id" }, { status: 400 });
  }
  const noteDir = path.join(NOTES_DIR, safe);
  const videoFile = path.join(VIDEOS_DIR, `${safe}.mp4`);

  const removed: string[] = [];
  let dirExisted = false;
  let videoExisted = false;

  try {
    const st = await fs.stat(noteDir);
    if (st.isDirectory()) {
      dirExisted = true;
      await fs.rm(noteDir, { recursive: true, force: true });
      removed.push(noteDir);
    }
  } catch { /* missing OK */ }

  try {
    await fs.stat(videoFile);
    videoExisted = true;
    await fs.unlink(videoFile);
    removed.push(videoFile);
  } catch { /* missing OK */ }

  if (!dirExisted && !videoExisted) {
    return NextResponse.json({ error: "note not found" }, { status: 404 });
  }
  return NextResponse.json({ deleted: safe, removed });
}
