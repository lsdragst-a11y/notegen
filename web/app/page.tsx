"use client";
import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Video, BookOpen, Layers, Hash, Clock, Sparkles, Loader2, Trash2 } from "lucide-react";
import NavBar from "@/components/NavBar";
import FluidBG from "@/components/FluidBG";
import ParticleBG from "@/components/ParticleBG";
import { fetchCatalog, formatDuration } from "@/lib/notes";
import { postGenerate, deleteNote } from "@/lib/api";
import type { CatalogItem } from "@/lib/types";

export default function LandingPage() {
  const router = useRouter();
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [url, setUrl] = useState("");
  const [hint, setHint] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmDel, setConfirmDel] = useState<CatalogItem | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    fetchCatalog().then(setCatalog).catch(console.error).finally(() => setLoading(false));
  }, []);

  async function handleDelete() {
    if (!confirmDel) return;
    setDeleting(true);
    try {
      await deleteNote(confirmDel.id);
      setCatalog(c => c.filter(it => it.id !== confirmDel.id));
      setConfirmDel(null);
    } catch (e) {
      alert(`删除失败：${String(e)}`);
    } finally {
      setDeleting(false);
    }
  }

  async function handleSubmit() {
    const trimmed = url.trim();
    if (!trimmed) {
      setHint("先粘贴一个 B 站视频链接");
      return;
    }
    // 每次都提交 backend 真跑——pipeline 内部 ASR cache 会跳过最慢的转写步骤，
    // 同 URL 重提交只跑 Pegasus + CLIP（几分钟），保证用户预期"点击=真生成"。
    // 已有 demo 想直接看不重跑，可以从下方卡片点击。
    setHint(null);
    setSubmitting(true);
    try {
      const { job_id } = await postGenerate(trimmed);
      router.push(`/generate?job=${job_id}`);
    } catch (e) {
      setSubmitting(false);
      setHint(`提交失败：${String(e)}。后端 (python server.py) 是否启动？`);
    }
  }

  return (
    <main className="relative min-h-screen">
      <FluidBG />
      <ParticleBG />
      <NavBar />

      <section className="relative z-10 pt-20 pb-16 px-6 max-w-5xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: "spring", stiffness: 160, damping: 22 }}
          className="text-center"
        >
          <h1 className="text-4xl md:text-5xl font-semibold tracking-tight leading-[1.15] text-[var(--fg)]">
            把视频拆成知识点
          </h1>
          <p className="mt-5 text-base text-[var(--fg-secondary)] max-w-lg mx-auto leading-relaxed">
            自动分章节、提术语、标重难点。一份给自己复习用的笔记。
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.12, type: "spring", stiffness: 160, damping: 22 }}
          className="mt-10 max-w-xl mx-auto"
        >
          <div className="glass rounded-full pl-5 pr-2 py-2 flex items-center gap-2 shadow-[var(--shadow-sm)]
                          hover:shadow-[var(--shadow-md)] transition-shadow">
            <Video size={16} className="text-[var(--fg-tertiary)] shrink-0" />
            <input
              type="text"
              placeholder="粘贴 B 站视频链接"
              value={url}
              onChange={(e) => { setUrl(e.target.value); setHint(null); }}
              onKeyDown={(e) => { if (e.key === "Enter") handleSubmit(); }}
              className="flex-1 bg-transparent outline-none text-sm placeholder:text-[var(--fg-tertiary)]"
            />
            <button onClick={handleSubmit}
                    disabled={submitting}
                    className="apple-button text-sm flex items-center gap-1">
              {submitting ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  提交中
                </>
              ) : (
                <>
                  生成笔记 <ArrowRight size={14} />
                </>
              )}
            </button>
          </div>
          <AnimatePresence>
            {hint && (
              <motion.p
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                className="mt-3 text-xs text-[var(--fg-tertiary)] text-center"
              >
                {hint}
              </motion.p>
            )}
          </AnimatePresence>
        </motion.div>
      </section>

      <section className="relative z-10 px-6 max-w-6xl mx-auto pb-32">
        <motion.h2
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
          className="text-xl font-semibold mb-5 flex items-center gap-2"
        >
          <BookOpen size={18} className="text-[var(--accent)]" />
          演示笔记
        </motion.h2>
        {loading ? (
          <div className="text-sm text-[var(--fg-tertiary)]">加载中…</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {catalog.map((item, i) => (
              <Link key={item.id} href={`/notes/${item.id}`}>
                <motion.article
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.35 + i * 0.06, type: "spring", stiffness: 180, damping: 24 }}
                  whileHover={{ y: -3 }}
                  className="apple-card group p-5 h-full cursor-pointer flex flex-col relative"
                >
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setConfirmDel(item);
                    }}
                    title="删除笔记"
                    className="absolute top-3 right-3 w-7 h-7 rounded-full
                               bg-[var(--bg-muted)] text-[var(--fg-tertiary)]
                               hover:bg-[#ff3b30] hover:text-white
                               inline-flex items-center justify-center
                               opacity-0 group-hover:opacity-100 transition-all z-10"
                  >
                    <Trash2 size={13} />
                  </button>
                  <div className="flex items-start justify-between gap-3">
                    <span className="tag-chip">{item.domain}</span>
                    <span className="inline-flex items-center gap-1 text-xs text-[var(--fg-tertiary)] tabular-nums">
                      <Clock size={11} /> {formatDuration(item.duration_sec)}
                    </span>
                  </div>
                  <h3 className="mt-3 text-base font-semibold leading-snug line-clamp-2 flex-1">
                    {item.title}
                  </h3>
                  {item.uploader && (
                    <p className="mt-1 text-xs text-[var(--fg-tertiary)]">{item.uploader}</p>
                  )}
                  <div className="mt-4 pt-4 border-t border-[var(--border)] flex items-center gap-3 text-xs text-[var(--fg-secondary)]">
                    <span className="inline-flex items-center gap-1">
                      <Layers size={11} /> {item.chapters} 章
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <Hash size={11} /> {item.chunks} 段
                    </span>
                    <span className="ml-auto inline-flex items-center gap-1 text-[var(--accent)] font-medium
                                     group-hover:gap-1.5 transition-all">
                      打开 <ArrowRight size={12} />
                    </span>
                  </div>
                </motion.article>
              </Link>
            ))}
          </div>
        )}
      </section>

      <AnimatePresence>
        {confirmDel && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="fixed inset-0 z-50 flex items-center justify-center px-4"
            style={{ background: "rgba(0,0,0,0.45)", backdropFilter: "blur(8px)" }}
            onClick={() => !deleting && setConfirmDel(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.94, y: 8 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.94, y: 8 }}
              transition={{ type: "spring", stiffness: 360, damping: 28 }}
              onClick={(e) => e.stopPropagation()}
              className="glass rounded-2xl w-full max-w-sm shadow-[var(--shadow-lg)] overflow-hidden"
            >
              <div className="p-5">
                <div className="flex items-start gap-3">
                  <span className="w-9 h-9 shrink-0 rounded-full bg-[rgba(255,59,48,0.12)]
                                   inline-flex items-center justify-center text-[#ff3b30]">
                    <Trash2 size={16} />
                  </span>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-base font-semibold text-[var(--fg)]">删除笔记？</h3>
                    <p className="mt-1 text-sm text-[var(--fg-secondary)] line-clamp-2">
                      {confirmDel.title}
                    </p>
                    <p className="mt-2 text-xs text-[var(--fg-tertiary)]">
                      笔记数据、关键帧、视频文件都会被删除，不可恢复。
                    </p>
                  </div>
                </div>
              </div>
              <div className="px-4 py-3 bg-[var(--bg-muted)] flex items-center justify-end gap-2">
                <button
                  onClick={() => setConfirmDel(null)}
                  disabled={deleting}
                  className="px-4 py-1.5 rounded-full text-sm font-medium
                             bg-[var(--bg-elevated)] border border-[var(--border)]
                             hover:bg-[var(--bg)] transition-colors disabled:opacity-50"
                >
                  取消
                </button>
                <button
                  onClick={handleDelete}
                  disabled={deleting}
                  className="px-4 py-1.5 rounded-full text-sm font-medium
                             bg-[#ff3b30] text-white hover:bg-[#ff453a]
                             transition-colors disabled:opacity-60 inline-flex items-center gap-1.5"
                >
                  {deleting ? (
                    <>
                      <Loader2 size={13} className="animate-spin" />
                      删除中
                    </>
                  ) : "删除"}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <footer className="relative z-10 mt-12 pb-12 text-center text-xs text-[var(--fg-tertiary)] space-y-1.5">
        <div className="flex items-center justify-center gap-1.5">
          <Sparkles size={11} className="text-[var(--accent)]" />
          <span className="font-medium text-[var(--fg-secondary)]">NoteGen</span>
          <span>·</span>
          <span>教学视频结构化笔记</span>
        </div>
        <div className="text-[10px]">本科毕设演示 · ASR + 多模态章节切分 + 学习场景 md 渲染</div>
      </footer>
    </main>
  );
}
