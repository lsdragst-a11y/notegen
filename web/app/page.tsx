"use client";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence, useDragControls, useMotionValue } from "framer-motion";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Video, BookOpen, Layers, Hash, Clock, Sparkles, Loader2, Trash2, Link2, FolderUp, X, FileVideo, Search, LockOpen, Lock, GripVertical } from "lucide-react";
import NavBar from "@/components/NavBar";
import FluidBG from "@/components/FluidBG";
import ParticleBG from "@/components/ParticleBG";
import { fetchCatalog, formatDuration } from "@/lib/notes";
import { postGenerate, postProbe, postUpload, deleteNote,
         type DownloadQuality, type ProbeResult } from "@/lib/api";
import type { CatalogItem } from "@/lib/types";
import { useAuth } from "@/components/AuthContext";

type SubmitMode = "url" | "file";
const ACCEPT_EXTS = ".mp4,.mkv,.mov,.avi,.webm,.flv,.m4v,.ts";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

// 笔记卡片排序持久化：用户拖拽后只在本浏览器记忆
const ORDER_KEY = "notegen.cardOrder.v1";

function loadSavedOrder(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(ORDER_KEY);
    const arr = raw ? JSON.parse(raw) : [];
    return Array.isArray(arr) ? arr.filter(x => typeof x === "string") : [];
  } catch { return []; }
}

function saveOrder(ids: string[]): void {
  if (typeof window === "undefined") return;
  try { localStorage.setItem(ORDER_KEY, JSON.stringify(ids)); } catch {}
}

// 把 fetched catalog 按 savedIds 排序；savedIds 里没出现的 id（新生成的笔记）追加在末尾
function applySavedOrder(items: CatalogItem[], savedIds: string[]): CatalogItem[] {
  if (!savedIds.length) return items;
  const byId = new Map(items.map(it => [it.id, it]));
  const ordered: CatalogItem[] = [];
  for (const id of savedIds) {
    const it = byId.get(id);
    if (it) { ordered.push(it); byId.delete(id); }
  }
  for (const it of byId.values()) ordered.push(it);
  return ordered;
}

export default function LandingPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [url, setUrl] = useState("");
  const [hint, setHint] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmDel, setConfirmDel] = useState<CatalogItem | null>(null);
  const [deleting, setDeleting] = useState(false);
  // 拖拽态：被拖 id + 它在最终序里的目标位置；松手前不动 catalog
  const [dragState, setDragState] = useState<{ id: string; previewIdx: number } | null>(null);
  const anyDragging = dragState !== null;
  const [mode, setMode] = useState<SubmitMode>("url");
  const [file, setFile] = useState<File | null>(null);
  const [fileTitle, setFileTitle] = useState("");
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [dragging, setDragging] = useState(false);
  const [probing, setProbing] = useState(false);
  const [probed, setProbed] = useState<ProbeResult | null>(null);
  const [quality, setQuality] = useState<DownloadQuality>("best");
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchCatalog()
      .then(items => setCatalog(applySavedOrder(items, loadSavedOrder())))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  // 每张卡的 DOM ref，用于拖拽时根据光标位置实时查 hover 目标（iOS 桌面图标式）
  const cardRefs = useRef<Map<string, HTMLElement>>(new Map());
  const registerCardRef = (id: string, el: HTMLElement | null) => {
    if (el) cardRefs.current.set(id, el);
    else cardRefs.current.delete(id);
  };

  // 读卡的"静态布局位置"（offsetLeft/Top，忽略 transform，与 layout 动画无关）。
  // 用 getBoundingClientRect 会读到 layout 动画中间帧 → 命中检测乱跳。
  function getStaticRect(el: HTMLElement): { left: number; right: number; top: number; bottom: number } {
    const op = (el.offsetParent as HTMLElement | null) ?? document.body;
    const pr = op.getBoundingClientRect();
    return {
      left: pr.left + el.offsetLeft,
      right: pr.left + el.offsetLeft + el.offsetWidth,
      top: pr.top + el.offsetTop,
      bottom: pr.top + el.offsetTop + el.offsetHeight,
    };
  }

  // catalog 不动，根据 dragState 派生"视觉顺序"——driver 用 CSS `order` 而非 DOM 重排，
  // 避免 React reconciliation 搬动 DOM 节点导致的一帧空白。
  const visualCatalog = useMemo<CatalogItem[]>(() => {
    if (!dragState) return catalog;
    const oldIdx = catalog.findIndex(it => it.id === dragState.id);
    if (oldIdx < 0 || oldIdx === dragState.previewIdx) return catalog;
    const next = [...catalog];
    const [it] = next.splice(oldIdx, 1);
    next.splice(dragState.previewIdx, 0, it);
    return next;
  }, [catalog, dragState]);

  const visualOrderMap = useMemo(() => {
    const m = new Map<string, number>();
    visualCatalog.forEach((it, i) => m.set(it.id, i));
    return m;
  }, [visualCatalog]);

  // 拖拽中由 onDrag 触发：用 dragged 卡的视觉中心作探针，命中目标卡静态格子就更新 previewIdx。
  function reorderByPointer(draggedId: string) {
    const draggedEl = cardRefs.current.get(draggedId);
    if (!draggedEl) return;
    const dr = draggedEl.getBoundingClientRect();
    const probeX = dr.left + dr.width / 2;
    const probeY = dr.top + dr.height / 2;

    let overId: string | null = null;
    for (const [id, el] of cardRefs.current) {
      if (id === draggedId) continue;
      const r = getStaticRect(el);
      if (probeX >= r.left && probeX <= r.right && probeY >= r.top && probeY <= r.bottom) {
        overId = id;
        break;
      }
    }
    if (!overId) return;
    const newIdx = visualOrderMap.get(overId);
    if (newIdx === undefined) return;
    setDragState(prev => {
      if (!prev || prev.id !== draggedId) return prev;
      if (prev.previewIdx === newIdx) return prev;
      return { id: draggedId, previewIdx: newIdx };
    });
  }

  function handleDragStart(id: string) {
    const oldIdx = catalog.findIndex(it => it.id === id);
    if (oldIdx < 0) return;
    setDragState({ id, previewIdx: oldIdx });
  }

  function handleDragEnd() {
    setDragState(prev => {
      if (prev) {
        // 提交：把 visualCatalog 落到 catalog
        const oldIdx = catalog.findIndex(it => it.id === prev.id);
        if (oldIdx >= 0 && oldIdx !== prev.previewIdx) {
          const next = [...catalog];
          const [it] = next.splice(oldIdx, 1);
          next.splice(prev.previewIdx, 0, it);
          setCatalog(next);
          saveOrder(next.map(x => x.id));
        }
      }
      return null;
    });
  }

  // 探测完成后：1 个可选 → 自动选；>1 个可选 → 默认最高
  function pickDefaultQuality(p: ProbeResult) {
    if (!p.heights || p.heights.length === 0) return "best";
    return `${p.heights[0]}p`;
  }

  async function handleProbe() {
    const trimmed = url.trim();
    if (!trimmed) { setHint("先粘贴一个视频链接"); return; }
    setHint(null);
    setProbing(true);
    setProbed(null);
    try {
      const r = await postProbe(trimmed);
      if (!r.ok) {
        setHint(`查询失败：${r.error || "未知"}`);
      } else {
        setProbed(r);
        setQuality(pickDefaultQuality(r));
      }
    } catch (e) {
      setHint(`查询失败：${String(e)}。后端 (python server.py) 是否启动？`);
    } finally {
      setProbing(false);
    }
  }

  async function handleDelete() {
    if (!confirmDel) return;
    setDeleting(true);
    try {
      await deleteNote(confirmDel.id);
      setCatalog(c => {
        const next = c.filter(it => it.id !== confirmDel.id);
        saveOrder(next.map(it => it.id));
        return next;
      });
      setConfirmDel(null);
    } catch (e) {
      alert(`删除失败：${String(e)}`);
    } finally {
      setDeleting(false);
    }
  }

  async function handleSubmit() {
    const trimmed = url.trim();
    if (!trimmed) { setHint("先粘贴一个视频链接"); return; }
    if (!probed) { setHint("先点查询看可用画质"); return; }
    if (!user) { router.push("/login?next=/"); return; }
    setHint(null);
    setSubmitting(true);
    try {
      const { job_id } = await postGenerate(trimmed, quality);
      router.push(`/generate?job=${job_id}`);
    } catch (e) {
      setSubmitting(false);
      setHint(`提交失败：${String(e)}。后端 (python server.py) 是否启动？`);
    }
  }

  function pickFile(f: File | null | undefined) {
    if (!f) return;
    const ext = "." + f.name.split(".").pop()?.toLowerCase();
    if (!ACCEPT_EXTS.split(",").includes(ext)) {
      setHint(`不支持的格式 ${ext}。允许：${ACCEPT_EXTS}`);
      return;
    }
    setFile(f);
    setFileTitle(f.name.replace(/\.[^.]+$/, ""));
    setHint(null);
  }

  async function handleSubmitFile() {
    if (!file) { setHint("先选一个视频文件"); return; }
    if (!user) { router.push("/login?next=/"); return; }
    setHint(null);
    setSubmitting(true);
    setUploadPct(0);
    try {
      const { job_id } = await postUpload(file, {
        title: fileTitle.trim() || undefined,
        onProgress: f => setUploadPct(f),
      });
      router.push(`/generate?job=${job_id}`);
    } catch (e) {
      setSubmitting(false);
      setUploadPct(null);
      setHint(`上传失败：${String(e)}。后端 (python server.py) 是否启动？`);
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
          {/* segmented control: URL vs 本地 */}
          <div className="flex justify-center mb-3">
            <div className="inline-flex p-1 rounded-full bg-[var(--bg-muted)] border border-[var(--border)] relative">
              {(["url", "file"] as const).map(m => {
                const active = mode === m;
                return (
                  <button
                    key={m}
                    onClick={() => { setMode(m); setHint(null); }}
                    className={`relative z-10 px-3.5 py-1.5 rounded-full text-xs font-medium
                                inline-flex items-center gap-1.5 transition-colors
                                ${active ? "text-[var(--fg)]" : "text-[var(--fg-tertiary)] hover:text-[var(--fg-secondary)]"}`}
                  >
                    {active && (
                      <motion.span
                        layoutId="mode-pill"
                        className="absolute inset-0 -z-10 rounded-full bg-[var(--bg-elevated)] shadow-[var(--shadow-sm)] border border-[var(--border)]"
                        transition={{ type: "spring", stiffness: 380, damping: 32 }}
                      />
                    )}
                    {m === "url"
                      ? <><Link2 size={12} /> 粘贴链接</>
                      : <><FolderUp size={12} /> 本地文件</>}
                  </button>
                );
              })}
            </div>
          </div>

          <AnimatePresence mode="wait" initial={false}>
            {mode === "url" ? (
              <motion.div
                key="url"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.18 }}
                className="glass rounded-full pl-5 pr-2 py-2 flex items-center gap-2 shadow-[var(--shadow-sm)]
                            hover:shadow-[var(--shadow-md)] transition-shadow"
              >
                <Video size={16} className="text-[var(--fg-tertiary)] shrink-0" />
                <input
                  type="text"
                  placeholder="粘贴 B 站 / YouTube 视频链接"
                  value={url}
                  onChange={(e) => {
                    setUrl(e.target.value);
                    setHint(null);
                    setProbed(null);  // URL 变了，旧 probe 失效
                  }}
                  onKeyDown={(e) => {
                    if (e.key !== "Enter") return;
                    if (probed) handleSubmit(); else handleProbe();
                  }}
                  className="flex-1 bg-transparent outline-none text-sm placeholder:text-[var(--fg-tertiary)] min-w-0"
                />
                {!probed ? (
                  <button onClick={handleProbe}
                          disabled={probing}
                          className="apple-button text-sm flex items-center gap-1 shrink-0">
                    {probing ? (
                      <><Loader2 size={14} className="animate-spin" />查询中</>
                    ) : (
                      <><Search size={14} /> 查询</>
                    )}
                  </button>
                ) : (
                  <button onClick={handleSubmit}
                          disabled={submitting}
                          className="apple-button text-sm flex items-center gap-1 shrink-0">
                    {submitting ? (
                      <><Loader2 size={14} className="animate-spin" />提交中</>
                    ) : (
                      <>生成笔记 <ArrowRight size={14} /></>
                    )}
                  </button>
                )}
              </motion.div>
            ) : (
              <motion.div
                key="file"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.18 }}
                className="space-y-3"
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={ACCEPT_EXTS}
                  className="hidden"
                  onChange={e => pickFile(e.target.files?.[0])}
                />
                {!file ? (
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    onDragOver={e => { e.preventDefault(); setDragging(true); }}
                    onDragLeave={() => setDragging(false)}
                    onDrop={e => {
                      e.preventDefault();
                      setDragging(false);
                      pickFile(e.dataTransfer.files?.[0]);
                    }}
                    className={`w-full rounded-2xl px-6 py-9 flex flex-col items-center justify-center gap-2
                                border-2 border-dashed transition-all
                                ${dragging
                                  ? "border-[var(--accent)] bg-[color-mix(in_srgb,var(--accent)_8%,transparent)]"
                                  : "border-[var(--border)] bg-[var(--bg-elevated)] hover:border-[var(--fg-tertiary)] hover:bg-[var(--bg-muted)]"}`}
                  >
                    <FolderUp size={22} className={dragging ? "text-[var(--accent)]" : "text-[var(--fg-tertiary)]"} />
                    <div className="text-sm font-medium text-[var(--fg)]">
                      {dragging ? "松开以放入" : "点击选择或拖入视频文件"}
                    </div>
                    <div className="text-[11px] text-[var(--fg-tertiary)]">
                      支持 mp4 / mkv / mov / avi / webm / flv / m4v / ts
                    </div>
                  </button>
                ) : (
                  <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)]
                                  shadow-[var(--shadow-sm)] p-4 space-y-3">
                    <div className="flex items-center gap-3">
                      <span className="w-9 h-9 rounded-xl bg-[var(--bg-muted)] inline-flex items-center
                                       justify-center text-[var(--accent)] shrink-0">
                        <FileVideo size={16} />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-medium truncate">{file.name}</div>
                        <div className="text-[11px] text-[var(--fg-tertiary)] tabular-nums">
                          {formatBytes(file.size)}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => { setFile(null); setFileTitle(""); setUploadPct(null); if (fileInputRef.current) fileInputRef.current.value = ""; }}
                        disabled={submitting}
                        className="w-7 h-7 rounded-full bg-[var(--bg-muted)] text-[var(--fg-tertiary)]
                                   hover:bg-[var(--border)] hover:text-[var(--fg)] inline-flex items-center
                                   justify-center transition-colors disabled:opacity-40"
                        title="移除"
                      >
                        <X size={13} />
                      </button>
                    </div>
                    <input
                      type="text"
                      placeholder="视频标题（可选，留空用文件名）"
                      value={fileTitle}
                      onChange={e => setFileTitle(e.target.value)}
                      className="w-full bg-[var(--bg-muted)] border border-[var(--border)] rounded-xl
                                 px-3 py-2 text-sm outline-none placeholder:text-[var(--fg-tertiary)]
                                 focus:border-[var(--accent)] transition-colors"
                    />
                    {uploadPct !== null && uploadPct < 1 && (
                      <div className="space-y-1">
                        <div className="flex justify-between text-[10.5px] text-[var(--fg-tertiary)] tabular-nums">
                          <span>上传中</span>
                          <span>{Math.round(uploadPct * 100)}%</span>
                        </div>
                        <div className="h-1 rounded-full bg-[var(--bg-muted)] overflow-hidden">
                          <div className="h-full bg-[var(--accent)] transition-[width] duration-150"
                               style={{ width: `${uploadPct * 100}%` }} />
                        </div>
                      </div>
                    )}
                    <button
                      onClick={handleSubmitFile}
                      disabled={submitting}
                      className="apple-button w-full text-sm inline-flex items-center justify-center gap-1.5"
                    >
                      {submitting ? (
                        uploadPct !== null && uploadPct < 1
                          ? <><Loader2 size={14} className="animate-spin" />上传 {Math.round(uploadPct * 100)}%</>
                          : <><Loader2 size={14} className="animate-spin" />处理中</>
                      ) : (
                        <>生成笔记 <ArrowRight size={14} /></>
                      )}
                    </button>
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>

          <AnimatePresence>
            {mode === "url" && probed && probed.ok && (
              <motion.div
                key="probed"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.2 }}
                className="mt-4 rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)]
                           shadow-[var(--shadow-sm)] p-4 space-y-3"
              >
                <div className="flex items-start gap-3">
                  <span className="w-9 h-9 rounded-xl bg-[var(--bg-muted)] inline-flex items-center
                                   justify-center text-[var(--accent)] shrink-0">
                    <Video size={16} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium truncate">
                      {probed.title || "（无标题）"}
                    </div>
                    <div className="text-[11px] text-[var(--fg-tertiary)] flex items-center gap-2 flex-wrap mt-0.5">
                      {probed.uploader && <span className="truncate max-w-[20ch]">{probed.uploader}</span>}
                      {probed.uploader && probed.duration > 0 && <span>·</span>}
                      {probed.duration > 0 && (
                        <span className="tabular-nums inline-flex items-center gap-0.5">
                          <Clock size={10} /> {formatDuration(probed.duration)}
                        </span>
                      )}
                      <span>·</span>
                      {probed.cookie_status === "ok" ? (
                        <span className="inline-flex items-center gap-0.5 text-emerald-600 dark:text-emerald-400">
                          <LockOpen size={10} /> 已登录
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-0.5 text-amber-600 dark:text-amber-400"
                              title="未登录 cookie，画质受限。Firefox 登录或导 cookies.txt 到 data/.cookies/">
                          <Lock size={10} /> 未登录
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                {probed.heights.length > 1 ? (
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[11px] text-[var(--fg-tertiary)] shrink-0">下载画质</span>
                    <div
                      className="inline-flex items-center rounded-full bg-[var(--bg-muted)] p-0.5 gap-0.5"
                      role="radiogroup"
                      aria-label="下载画质"
                    >
                      {probed.heights.map(h => {
                        const v = `${h}p`;
                        const active = quality === v;
                        return (
                          <button
                            key={h}
                            type="button"
                            onClick={() => setQuality(v)}
                            role="radio"
                            aria-checked={active}
                            className={`px-3 h-7 rounded-full text-[11px] font-medium tabular-nums
                                        inline-flex items-center justify-center transition-colors
                                        ${active
                                          ? "bg-[var(--bg-elevated)] text-[var(--fg)] shadow-[var(--shadow-sm)] border border-[var(--border)]"
                                          : "text-[var(--fg-tertiary)] hover:text-[var(--fg-secondary)]"}`}
                          >
                            {v}
                          </button>
                        );
                      })}
                    </div>
                    {probed.cookie_status === "missing" && (
                      <span className="text-[10.5px] text-[var(--fg-tertiary)]">
                        登录后会有更高画质
                      </span>
                    )}
                  </div>
                ) : probed.heights.length === 1 ? (
                  <div className="text-[11px] text-[var(--fg-tertiary)]">
                    只有 1 种画质可下：<span className="text-[var(--fg)] font-medium">{probed.heights[0]}p</span>
                    {probed.cookie_status === "missing" && "（未登录，更高画质需 cookie）"}
                  </div>
                ) : (
                  <div className="text-[11px] text-amber-600 dark:text-amber-400">
                    没探到可下视频流，可能 URL 错或视频已下架
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>

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
              <NoteCard
                key={item.id}
                item={item}
                index={i}
                cssOrder={visualOrderMap.get(item.id) ?? i}
                isDragged={dragState?.id === item.id}
                anyDragging={anyDragging}
                registerRef={el => registerCardRef(item.id, el)}
                onDragStart={() => handleDragStart(item.id)}
                onDragMove={() => reorderByPointer(item.id)}
                onDragEnd={() => handleDragEnd()}
                onDelete={() => setConfirmDel(item)}
                canDelete={user?.role === "admin"}
              />
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

function NoteCard({ item, index, cssOrder, isDragged, anyDragging, registerRef, onDragStart, onDragMove, onDragEnd, onDelete, canDelete }: {
  item: CatalogItem;
  index: number;
  cssOrder: number;
  isDragged: boolean;
  anyDragging: boolean;
  registerRef: (el: HTMLElement | null) => void;
  onDragStart: () => void;
  onDragMove: () => void;
  onDragEnd: () => void;
  onDelete: () => void;
  canDelete: boolean;
}) {
  const dragControls = useDragControls();
  const ref = useRef<HTMLDivElement>(null);
  // 自己 own x/y motion value，方便在 CSS slot 变化时手动补偿，保证拖拽中的卡视觉位置不动
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const lastBase = useRef<{ left: number; top: number } | null>(null);

  useEffect(() => {
    registerRef(ref.current);
    return () => registerRef(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 当 cssOrder 变化（被 swap 进新格子）时，offsetLeft/Top 反映新的静态位置。
  // 如果这张卡正在被拖，给 motion value 减掉 base 的 delta，视觉位置保持不变（仍在光标下）。
  useLayoutEffect(() => {
    if (!ref.current) return;
    const el = ref.current;
    const op = (el.offsetParent as HTMLElement | null) ?? document.body;
    const opRect = op.getBoundingClientRect();
    const base = { left: opRect.left + el.offsetLeft, top: opRect.top + el.offsetTop };
    if (isDragged && lastBase.current) {
      const dx = base.left - lastBase.current.left;
      const dy = base.top - lastBase.current.top;
      if (Math.abs(dx) > 0.5 || Math.abs(dy) > 0.5) {
        x.set(x.get() - dx);
        y.set(y.get() - dy);
      }
    }
    lastBase.current = base;
  }, [cssOrder, isDragged, x, y]);

  return (
    <motion.div
      ref={ref}
      // 被拖的那张关掉 layout：FLIP 会让它从老位置滑到新位置 → 抢走 drag 对 x/y 的控制；
      // 不被拖的卡保留 layout，让 CSS order 改变时它们能丝滑 FLIP 让位
      layout={!isDragged}
      drag
      dragListener={false}
      dragControls={dragControls}
      dragMomentum={false}
      dragElastic={0}
      dragSnapToOrigin
      onDragStart={onDragStart}
      onDrag={onDragMove}
      onDragEnd={onDragEnd}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{
        layout: { type: "spring", stiffness: 320, damping: 28, mass: 1 },
        default: { delay: 0.35 + index * 0.06, duration: 0.25 },
      }}
      // hover 用 scale 不用 y——避免和 drag 共用 y 通道
      whileHover={anyDragging ? undefined : { scale: 1.015 }}
      whileDrag={{ scale: 1.06, zIndex: 50, boxShadow: "var(--shadow-lg)" }}
      className="draggable-tile"
      style={{ x, y, order: cssOrder, touchAction: "none" }}
    >
      <Link href={`/notes/${item.id}`} draggable={false}
            onClick={(e) => { if (isDragged) e.preventDefault(); }}>
        <article className="apple-card group p-5 h-full cursor-pointer flex flex-col relative">
          <button
            type="button"
            onPointerDown={(e) => { e.preventDefault(); dragControls.start(e); }}
            onClick={(e) => { e.preventDefault(); e.stopPropagation(); }}
            title="拖动排序"
            className="absolute top-3 left-3 w-7 h-7 rounded-full
                       bg-[var(--bg-muted)] text-[var(--fg-tertiary)]
                       hover:bg-[var(--bg-elevated)] hover:text-[var(--fg)]
                       inline-flex items-center justify-center
                       opacity-0 group-hover:opacity-100 transition-all z-10
                       cursor-grab active:cursor-grabbing touch-none"
          >
            <GripVertical size={13} />
          </button>
          {canDelete && (
            <button
              type="button"
              onClick={(e) => { e.preventDefault(); e.stopPropagation(); onDelete(); }}
              title="删除笔记"
              className="absolute top-3 right-3 w-7 h-7 rounded-full
                         bg-[var(--bg-muted)] text-[var(--fg-tertiary)]
                         hover:bg-[#ff3b30] hover:text-white
                         inline-flex items-center justify-center
                         opacity-0 group-hover:opacity-100 transition-all z-10"
            >
              <Trash2 size={13} />
            </button>
          )}
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
        </article>
      </Link>
    </motion.div>
  );
}
