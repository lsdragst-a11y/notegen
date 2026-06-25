"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Clock,
  FileVideo,
  FolderUp,
  Link2,
  Loader2,
  Lock,
  LockOpen,
  Search,
  Video,
  X,
} from "lucide-react";
import { useAuth } from "@/components/AuthContext";
import { formatDuration } from "@/lib/notes";
import {
  postGenerate,
  postProbe,
  postUpload,
  type DownloadQuality,
  type ProbeResult,
} from "@/lib/api";

type SubmitMode = "url" | "file";

const ACCEPT_EXTS = ".mp4,.mkv,.mov,.avi,.webm,.flv,.m4v,.ts";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function pickDefaultQuality(p: ProbeResult) {
  if (!p.heights || p.heights.length === 0) return "best";
  return `${p.heights[0]}p`;
}

export default function CreateNotePanel({ next = "/notebooks" }: { next?: string }) {
  const router = useRouter();
  const { user } = useAuth();
  const [mode, setMode] = useState<SubmitMode>("url");
  const [url, setUrl] = useState("");
  const [hint, setHint] = useState<string | null>(null);
  const [probing, setProbing] = useState(false);
  const [probed, setProbed] = useState<ProbeResult | null>(null);
  const [quality, setQuality] = useState<DownloadQuality>("best");
  const [submitting, setSubmitting] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [fileTitle, setFileTitle] = useState("");
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function requireUser(): boolean {
    if (user) return true;
    router.push(`/login?next=${encodeURIComponent(next)}`);
    return false;
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

  async function handleSubmitUrl() {
    const trimmed = url.trim();
    if (!trimmed) { setHint("先粘贴一个视频链接"); return; }
    if (!probed) { setHint("先点查询看可用画质"); return; }
    if (!requireUser()) return;
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
    if (!requireUser()) return;
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
    <div className="rounded-2xl border border-[var(--wf-border)] bg-[var(--wf-surface)] shadow-[var(--wf-shadow-lg)]">
      <div className="p-4 sm:p-5">
        <div className="mb-3 inline-flex rounded-[8px] border border-[var(--wf-border)] bg-[var(--wf-surface-muted)] p-1">
          {(["url", "file"] as const).map(m => {
            const active = mode === m;
            return (
              <button
                key={m}
                onClick={() => { setMode(m); setHint(null); }}
                className={`relative z-10 inline-flex h-8 items-center gap-1.5 rounded-[6px] px-3 text-xs font-medium transition-colors
                            ${active ? "text-[var(--wf-text)]" : "text-[var(--wf-text-tertiary)] hover:text-[var(--wf-text-secondary)]"}`}
              >
                {active && (
                  <motion.span
                    layoutId="create-note-mode-pill"
                    className="absolute inset-0 -z-10 rounded-[6px] border border-[var(--wf-border)] bg-[var(--wf-surface)] shadow-[var(--wf-shadow-sm)]"
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

        <AnimatePresence mode="wait" initial={false}>
          {mode === "url" ? (
            <motion.div
              key="url"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.18 }}
              className="flex flex-col gap-2 rounded-[8px] border border-[var(--wf-border)] bg-[var(--wf-canvas)] p-2 sm:flex-row sm:items-center"
            >
              <div className="flex min-h-10 flex-1 items-center gap-2 px-2">
                <Video size={16} className="shrink-0 text-[var(--wf-text-tertiary)]" />
                <input
                  type="text"
                  placeholder="粘贴 B 站 / YouTube 视频链接"
                  value={url}
                  onChange={(e) => {
                    setUrl(e.target.value);
                    setHint(null);
                    setProbed(null);
                  }}
                  onKeyDown={(e) => {
                    if (e.key !== "Enter") return;
                    if (probed) handleSubmitUrl(); else handleProbe();
                  }}
                  className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-[var(--wf-text-tertiary)]"
                />
              </div>
              {!probed ? (
                <button onClick={handleProbe}
                        disabled={probing}
                        className="rounded-[var(--wf-radius-sm)] bg-[var(--wf-accent)] px-4 py-2 font-semibold text-[var(--wf-on-accent)] transition-colors hover:bg-[var(--wf-accent-hover)] disabled:bg-[var(--wf-disabled-bg)] disabled:text-[var(--wf-disabled-fg)] disabled:cursor-not-allowed inline-flex items-center justify-center gap-1 text-sm sm:shrink-0">
                  {probing ? (
                    <><Loader2 size={14} className="animate-spin" />查询中</>
                  ) : (
                    <><Search size={14} /> 查询</>
                  )}
                </button>
              ) : (
                <button onClick={handleSubmitUrl}
                        disabled={submitting}
                        className="rounded-[var(--wf-radius-sm)] bg-[var(--wf-accent)] px-4 py-2 font-semibold text-[var(--wf-on-accent)] transition-colors hover:bg-[var(--wf-accent-hover)] disabled:bg-[var(--wf-disabled-bg)] disabled:text-[var(--wf-disabled-fg)] disabled:cursor-not-allowed inline-flex items-center justify-center gap-1 text-sm sm:shrink-0">
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
                  className={`flex w-full flex-col items-center justify-center gap-2 rounded-[8px] border-2 border-dashed px-6 py-8 transition-all
                              ${dragging
                                ? "border-[var(--wf-accent)] bg-[color-mix(in_srgb,var(--wf-accent)_8%,transparent)]"
                                : "border-[var(--wf-border)] bg-[var(--wf-canvas)] hover:border-[var(--wf-text-tertiary)] hover:bg-[var(--wf-surface-muted)]"}`}
                >
                  <FolderUp size={22} className={dragging ? "text-[var(--wf-accent)]" : "text-[var(--wf-text-tertiary)]"} />
                  <div className="text-sm font-medium text-[var(--wf-text)]">
                    {dragging ? "松开以放入" : "点击选择或拖入视频文件"}
                  </div>
                  <div className="text-[11px] text-[var(--wf-text-tertiary)]">
                    支持 mp4 / mkv / mov / avi / webm / flv / m4v / ts
                  </div>
                </button>
              ) : (
                <div className="space-y-3 rounded-[8px] border border-[var(--wf-border)] bg-[var(--wf-canvas)] p-4">
                  <div className="flex items-center gap-3">
                    <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[8px] bg-[var(--wf-surface-muted)] text-[var(--wf-accent)]">
                      <FileVideo size={16} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">{file.name}</div>
                      <div className="text-[11px] tabular-nums text-[var(--wf-text-tertiary)]">
                        {formatBytes(file.size)}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => { setFile(null); setFileTitle(""); setUploadPct(null); if (fileInputRef.current) fileInputRef.current.value = ""; }}
                      disabled={submitting}
                      className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-[var(--wf-surface-muted)] text-[var(--wf-text-tertiary)] transition-colors hover:bg-[var(--wf-border)] hover:text-[var(--wf-text)] disabled:opacity-40"
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
                    className="w-full rounded-[8px] border border-[var(--wf-border)] bg-[var(--wf-surface-muted)] px-3 py-2 text-sm outline-none transition-colors placeholder:text-[var(--wf-text-tertiary)] focus:border-[var(--wf-accent)]"
                  />
                  {uploadPct !== null && uploadPct < 1 && (
                    <div className="space-y-1">
                      <div className="flex justify-between text-[10.5px] tabular-nums text-[var(--wf-text-tertiary)]">
                        <span>上传中</span>
                        <span>{Math.round(uploadPct * 100)}%</span>
                      </div>
                      <div className="h-1 overflow-hidden rounded-full bg-[var(--wf-surface-muted)]">
                        <div className="h-full bg-[var(--wf-accent)] transition-[width] duration-150"
                             style={{ width: `${uploadPct * 100}%` }} />
                      </div>
                    </div>
                  )}
                  <button
                    onClick={handleSubmitFile}
                    disabled={submitting}
                    className="rounded-[var(--wf-radius-sm)] bg-[var(--wf-accent)] px-4 py-2 font-semibold text-[var(--wf-on-accent)] transition-colors hover:bg-[var(--wf-accent-hover)] disabled:bg-[var(--wf-disabled-bg)] disabled:text-[var(--wf-disabled-fg)] disabled:cursor-not-allowed inline-flex w-full items-center justify-center gap-1.5 text-sm"
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
              className="mt-3 space-y-3 rounded-[8px] border border-[var(--wf-border)] bg-[var(--wf-canvas)] p-4"
            >
              <div className="flex items-start gap-3">
                <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[8px] bg-[var(--wf-surface-muted)] text-[var(--wf-accent)]">
                  <Video size={16} />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">
                    {probed.title || "（无标题）"}
                  </div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-2 text-[11px] text-[var(--wf-text-tertiary)]">
                    {probed.uploader && <span className="max-w-[20ch] truncate">{probed.uploader}</span>}
                    {probed.uploader && probed.duration > 0 && <span>·</span>}
                    {probed.duration > 0 && (
                      <span className="inline-flex items-center gap-0.5 tabular-nums">
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
                <div className="flex flex-wrap items-center gap-2">
                  <span className="shrink-0 text-[11px] text-[var(--wf-text-tertiary)]">下载画质</span>
                  <div
                    className="inline-flex items-center gap-0.5 rounded-full bg-[var(--wf-surface-muted)] p-0.5"
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
                          className={`inline-flex h-7 items-center justify-center rounded-full px-3 text-[11px] font-medium tabular-nums transition-colors
                                      ${active
                                        ? "border border-[var(--wf-border)] bg-[var(--wf-surface)] text-[var(--wf-text)] shadow-[var(--wf-shadow-sm)]"
                                        : "text-[var(--wf-text-tertiary)] hover:text-[var(--wf-text-secondary)]"}`}
                        >
                          {v}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ) : probed.heights.length === 1 ? (
                <div className="text-[11px] text-[var(--wf-text-tertiary)]">
                  只有 1 种画质可下：<span className="font-medium text-[var(--wf-text)]">{probed.heights[0]}p</span>
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
              className="mt-3 text-center text-xs text-[var(--wf-text-tertiary)]"
            >
              {hint}
            </motion.p>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
