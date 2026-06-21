"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ChevronDown,
  Clock3,
  ExternalLink,
  History as HistoryIcon,
  Loader2,
  RotateCw,
  TerminalSquare,
} from "lucide-react";
import NavBar from "@/components/NavBar";
import RequireAuth from "@/components/RequireAuth";
import { fetchHistory, retryJob } from "@/lib/api";
import type { HistoryItem, JobStatus, JobStageMetric } from "@/lib/types";

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

function fmtMS(s: number): string {
  return `${Math.floor(s / 60).toString().padStart(2, "0")}:${(Math.floor(s) % 60).toString().padStart(2, "0")}`;
}

function sourceLabel(it: HistoryItem): string {
  if (it.is_local) return "本地上传";
  return it.source.length > 56 ? it.source.slice(0, 56) + "..." : it.source;
}

function metricTotal(metrics: JobStageMetric[]): number {
  return metrics.reduce((sum, item) => (
    sum + (typeof item.duration_sec === "number" ? item.duration_sec : 0)
  ), 0);
}

function slowestMetric(metrics: JobStageMetric[]): JobStageMetric | undefined {
  return metrics
    .filter((item) => typeof item.duration_sec === "number")
    .sort((a, b) => (b.duration_sec ?? 0) - (a.duration_sec ?? 0))[0];
}

function Diagnostics({ item }: { item: HistoryItem }) {
  const runtime = item.runtime;
  const metrics = runtime?.metrics ?? [];
  const slowest = slowestMetric(metrics);
  const logs = runtime?.log_tail ?? [];

  if (!runtime && !item.error) return null;

  return (
    <div className="mt-3 border-t border-[var(--border)] pt-3">
      <div className="grid gap-2 text-xs sm:grid-cols-3">
        <div>
          <div className="text-[var(--fg-tertiary)]">最后阶段</div>
          <div className="mt-0.5 truncate text-[var(--fg-secondary)]">
            {runtime?.stage || item.status}
            {typeof runtime?.percent === "number" ? ` · ${runtime.percent}%` : ""}
          </div>
        </div>
        <div>
          <div className="text-[var(--fg-tertiary)]">总耗时</div>
          <div className="mt-0.5 tabular-nums text-[var(--fg-secondary)]">
            {metrics.length ? fmtMS(metricTotal(metrics)) : "暂无"}
          </div>
        </div>
        <div>
          <div className="text-[var(--fg-tertiary)]">最慢阶段</div>
          <div className="mt-0.5 truncate text-[var(--fg-secondary)]">
            {slowest ? `${slowest.label || slowest.stage} · ${fmtMS(slowest.duration_sec ?? 0)}` : "暂无"}
          </div>
        </div>
      </div>

      {(item.error || runtime?.msg || runtime?.returncode) && (
        <div className="mt-3 flex gap-2 text-xs text-[var(--fg-secondary)]">
          <AlertTriangle size={14} className="mt-0.5 shrink-0 text-[#ff9f0a]" />
          <div className="min-w-0">
            <div className="break-words">{item.error || runtime?.msg}</div>
            {runtime?.returncode && (
              <div className="mt-1 tabular-nums text-[var(--fg-tertiary)]">returncode {runtime.returncode}</div>
            )}
          </div>
        </div>
      )}

      {metrics.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {metrics.slice(-10).map((metric) => {
            const running = metric.status === "running";
            return (
              <div key={`${metric.i}-${metric.stage}`} className="flex items-center gap-3 text-xs">
                <span className="w-5 shrink-0 tabular-nums text-[var(--fg-tertiary)]">{metric.i}</span>
                <span className="min-w-0 flex-1 truncate text-[var(--fg-secondary)]">
                  {metric.label || metric.stage}
                </span>
                <span className={`shrink-0 tabular-nums ${running ? "text-[var(--accent)]" : "text-[var(--fg-tertiary)]"}`}>
                  {typeof metric.duration_sec === "number" ? fmtMS(metric.duration_sec) : "运行中"}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {logs.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 flex items-center gap-1.5 text-[11px] text-[var(--fg-tertiary)]">
            <TerminalSquare size={12} /> 日志尾部
          </div>
          <pre className="max-h-40 overflow-auto rounded-lg bg-[var(--bg-muted)] p-3 text-[11px] leading-relaxed text-[var(--fg-secondary)]">
            {logs.join("\n")}
          </pre>
        </div>
      )}
    </div>
  );
}

function HistoryInner() {
  const router = useRouter();
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [retryId, setRetryId] = useState<string | null>(null);

  useEffect(() => {
    fetchHistory().then(setItems).catch(console.error).finally(() => setLoading(false));
  }, []);

  const summary = useMemo(() => {
    const failed = items.filter((it) => it.status === "failed" || it.status === "interrupted").length;
    const active = items.filter((it) => it.status === "queued" || it.status === "running").length;
    const diagnosed = items.filter((it) => it.runtime?.metrics?.length || it.runtime?.log_tail?.length).length;
    return { failed, active, diagnosed };
  }, [items]);

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
      <NavBar />
      <section className="relative z-10 mx-auto max-w-5xl px-6 pt-20 pb-32">
        <h1 className="mb-5 flex items-center gap-2 text-xl font-semibold">
          <HistoryIcon size={18} className="text-[var(--accent)]" /> 提交历史
        </h1>

        {!loading && items.length > 0 && (
          <div className="mb-4 grid gap-3 sm:grid-cols-3">
            {[
              { label: "失败/中断", value: summary.failed, icon: AlertTriangle },
              { label: "进行中", value: summary.active, icon: Loader2 },
              { label: "有诊断", value: summary.diagnosed, icon: Clock3 },
            ].map(({ label, value, icon: Icon }) => (
              <div key={label} className="apple-card flex items-center gap-3 p-4">
                <Icon size={16} className="text-[var(--accent)]" />
                <div>
                  <div className="text-lg font-semibold tabular-nums">{value}</div>
                  <div className="text-xs text-[var(--fg-tertiary)]">{label}</div>
                </div>
              </div>
            ))}
          </div>
        )}

        {loading ? (
          <div className="text-sm text-[var(--fg-tertiary)]">加载中...</div>
        ) : items.length === 0 ? (
          <div className="apple-card p-8 text-center">
            <p className="text-sm text-[var(--fg-secondary)]">还没有提交记录。</p>
            <Link href="/notebooks" className="apple-button mt-4 inline-flex">去生成一个</Link>
          </div>
        ) : (
          <div className="apple-card divide-y divide-[var(--border)] overflow-hidden p-0">
            {items.map((it) => {
              const failed = it.status === "failed" || it.status === "interrupted";
              const hasRuntimePayload = !!it.runtime?.metrics?.length || !!it.runtime?.log_tail?.length;
              const hasNonZeroReturn = !!it.runtime?.returncode && it.runtime.returncode !== "0";
              const hasDiagnostics = failed || !!it.error || hasRuntimePayload ||
                hasNonZeroReturn || ((it.status === "queued" || it.status === "running") && !!it.runtime);
              return (
                <div key={it.id} className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_CLASS[it.status]}`}>
                      {STATUS_LABEL[it.status]}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm">{sourceLabel(it)}</div>
                      <div className="text-[11px] text-[var(--fg-tertiary)] tabular-nums">
                        {fmtDate(it.created_at)}{it.error ? ` · ${it.error.slice(0, 54)}` : ""}
                      </div>
                    </div>
                    {it.status === "done" && it.note_id && (
                      <Link href={`/notes/${it.note_id}`}
                            className="inline-flex shrink-0 items-center gap-1 text-xs text-[var(--accent)] hover:underline">
                        <ExternalLink size={12} /> 看笔记
                      </Link>
                    )}
                    {(it.status === "failed" || it.status === "interrupted") && (
                      <button onClick={() => doRetry(it.id)} disabled={retryId === it.id}
                              className="inline-flex shrink-0 items-center gap-1 text-xs text-[var(--fg-secondary)]
                                         hover:text-[var(--fg)] disabled:opacity-60">
                        {retryId === it.id ? <Loader2 size={12} className="animate-spin" /> : <RotateCw size={12} />}
                        重试
                      </button>
                    )}
                  </div>

                  {hasDiagnostics && (
                    <details className="group mt-2" open={failed}>
                      <summary className="inline-flex cursor-pointer list-none items-center gap-1 text-xs text-[var(--fg-tertiary)] hover:text-[var(--fg-secondary)]">
                        <ChevronDown size={13} className="transition-transform group-open:rotate-180" />
                        诊断
                      </summary>
                      <Diagnostics item={it} />
                    </details>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>
    </main>
  );
}

export default function HistoryPage() {
  return <RequireAuth><HistoryInner /></RequireAuth>;
}
