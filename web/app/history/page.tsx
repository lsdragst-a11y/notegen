"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { History as HistoryIcon, RotateCw, ExternalLink, Loader2 } from "lucide-react";
import NavBar from "@/components/NavBar";
import FluidBG from "@/components/FluidBG";
import RequireAuth from "@/components/RequireAuth";
import { fetchHistory, retryJob } from "@/lib/api";
import type { HistoryItem, JobStatus } from "@/lib/types";

const STATUS_LABEL: Record<JobStatus, string> = {
  queued: "排队中", running: "进行中", done: "完成", failed: "失败", interrupted: "中断",
};
const STATUS_CLASS: Record<JobStatus, string> = {
  queued: "text-[var(--fg-tertiary)] bg-[var(--bg-muted)]",
  running: "text-[var(--accent)] bg-[color-mix(in_srgb,var(--accent)_12%,transparent)]",
  done: "text-[#30d158] bg-[rgba(48,209,88,0.12)]",
  failed: "text-[#ff3b30] bg-[rgba(255,59,48,0.12)]",
  interrupted: "text-[#ff9f0a] bg-[rgba(255,159,10,0.12)]",
};

function fmtDate(ts: number): string {
  const d = new Date(ts * 1000);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getMonth() + 1}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function sourceLabel(it: HistoryItem): string {
  if (it.is_local) return "本地上传";
  return it.source.length > 48 ? it.source.slice(0, 48) + "…" : it.source;
}

function HistoryInner() {
  const router = useRouter();
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [retryId, setRetryId] = useState<string | null>(null);

  useEffect(() => {
    fetchHistory().then(setItems).catch(console.error).finally(() => setLoading(false));
  }, []);

  async function doRetry(id: string) {
    setRetryId(id);
    try {
      const { job_id } = await retryJob(id);
      router.push(`/generate?job=${job_id}`);
    } catch (e) {
      alert(`重试失败：${String(e)}`);
      setRetryId(null);
    }
  }

  return (
    <main className="relative min-h-screen">
      <FluidBG />
      <NavBar />
      <section className="relative z-10 max-w-4xl mx-auto px-6 pt-20 pb-32">
        <h1 className="text-xl font-semibold mb-5 flex items-center gap-2">
          <HistoryIcon size={18} className="text-[var(--accent)]" /> 提交历史
        </h1>
        {loading ? (
          <div className="text-sm text-[var(--fg-tertiary)]">加载中…</div>
        ) : items.length === 0 ? (
          <div className="apple-card p-8 text-center">
            <p className="text-sm text-[var(--fg-secondary)]">还没有提交记录。</p>
            <Link href="/" className="apple-button inline-flex mt-4">去生成一个</Link>
          </div>
        ) : (
          <div className="apple-card divide-y divide-[var(--border)] overflow-hidden p-0">
            {items.map(it => (
              <div key={it.id} className="flex items-center gap-3 px-4 py-3">
                <span className={`shrink-0 text-[11px] font-medium px-2 py-0.5 rounded-full ${STATUS_CLASS[it.status]}`}>
                  {STATUS_LABEL[it.status]}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm truncate">{sourceLabel(it)}</div>
                  <div className="text-[11px] text-[var(--fg-tertiary)] tabular-nums">
                    {fmtDate(it.created_at)}{it.error ? ` · ${it.error.slice(0, 40)}` : ""}
                  </div>
                </div>
                {it.status === "done" && it.note_id && (
                  <Link href={`/notes/${it.note_id}`}
                        className="shrink-0 inline-flex items-center gap-1 text-xs text-[var(--accent)] hover:underline">
                    <ExternalLink size={12} /> 看笔记
                  </Link>
                )}
                {(it.status === "failed" || it.status === "interrupted") && (
                  <button onClick={() => doRetry(it.id)} disabled={retryId === it.id}
                          className="shrink-0 inline-flex items-center gap-1 text-xs text-[var(--fg-secondary)]
                                     hover:text-[var(--fg)] disabled:opacity-60">
                    {retryId === it.id ? <Loader2 size={12} className="animate-spin" /> : <RotateCw size={12} />}
                    重试
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

export default function HistoryPage() {
  return <RequireAuth><HistoryInner /></RequireAuth>;
}
