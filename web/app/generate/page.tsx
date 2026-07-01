"use client";
import { useEffect, useRef, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { CheckCircle2, AlertCircle, Loader2 } from "lucide-react";
import NavBar from "@/components/NavBar";
import { GenerationCompanion } from "@/components/interactive/GenerationCompanion";
import { subscribeJob, type JobEvent } from "@/lib/api";

function GenerateInner() {
  const router = useRouter();
  const search = useSearchParams();
  const jobId = search.get("job") || "";
  const [progress, setProgress] = useState<JobEvent>({
    stage: "连接中", percent: 0, msg: "等待 backend 响应...", t: 0,
  });
  const [history, setHistory] = useState<JobEvent[]>([]);
  const [error, setError] = useState<string | null>(jobId ? null : "缺少 job id");
  const [elapsed, setElapsed] = useState(0);
  const [meta, setMeta] = useState<{ videoDuration?: number; estTotal?: number; videoTitle?: string }>({});
  const redirectedRef = useRef(false);
  const terminalRef = useRef(false);

  // 计时器：进页面起每秒走一格，到终态（done/失败）停（Date.now 留在 effect 里，不进 render）
  useEffect(() => {
    if (!jobId) return;
    const started = Date.now();
    const id = setInterval(() => {
      if (!terminalRef.current) setElapsed(Math.floor((Date.now() - started) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, [jobId]);

  useEffect(() => {
    if (!jobId) return;
    const unsub = subscribeJob(jobId, (e) => {
      setProgress(e);
      setHistory(h => [...h, e]);
      // 探测阶段会携带 video_duration / est_total_sec / video_title
      if (e.video_duration || e.est_total_sec || e.video_title) {
        setMeta(prev => ({
          videoDuration: e.video_duration ?? prev.videoDuration,
          estTotal: e.est_total_sec ?? prev.estTotal,
          videoTitle: e.video_title ?? prev.videoTitle,
        }));
      }
      if (e.stage === "done" && e.note_id && !redirectedRef.current) {
        terminalRef.current = true;
        redirectedRef.current = true;
        // 给用户看一下 100% 状态再跳
        setTimeout(() => router.push(`/notes/${e.note_id}`), 800);
      }
      // 后端真失败发的是 failed/interrupted（不是 error）；纳入错误态并展示后端原因，
      // 否则会被随后的 SSE 流关闭误判成"连接中断"或卡在"生成中"。
      if (e.stage === "failed" || e.stage === "interrupted" || e.stage === "error") {
        terminalRef.current = true;
        setError(e.msg || (e.stage === "interrupted" ? "任务被中断" : "生成失败"));
      }
    }, () => {
      // 终态后流会正常关闭并触发 onerror，别用"连接中断"覆盖真实失败原因
      if (!terminalRef.current) setError("和 backend 的连接中断了。可能 server.py 退出？");
    });
    return unsub;
  }, [jobId, router]);

  const isError = !!error || ["error", "failed", "interrupted"].includes(progress.stage);
  const isDone = progress.stage === "done";
  const fmtMS = (s: number) => `${Math.floor(s / 60).toString().padStart(2, "0")}:${(Math.floor(s) % 60).toString().padStart(2, "0")}`;
  const metrics = progress.metrics?.length
    ? progress.metrics
    : [...history].reverse().find((e) => e.metrics?.length)?.metrics ?? [];
  const visibleMetrics = metrics.slice(-12);
  const totalMetricSec = metrics.reduce((sum, item) => (
    sum + (typeof item.duration_sec === "number" ? item.duration_sec : 0)
  ), 0);

  return (
    <main className="relative isolate min-h-[100dvh] overflow-hidden bg-[var(--wf-canvas)] text-[var(--wf-text)]">
      <div className="wf-paper-atmosphere" aria-hidden="true" />
      <NavBar />

      <section className="relative z-10 mx-auto max-w-3xl px-5 pb-20 pt-20 sm:px-6">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: "spring", stiffness: 160, damping: 22 }}
          className="relative overflow-hidden rounded-[2rem] border border-[var(--wf-border)] bg-[linear-gradient(145deg,color-mix(in_srgb,var(--wf-surface)_96%,transparent),color-mix(in_srgb,var(--wf-surface-muted)_30%,var(--wf-surface)))] p-6 shadow-[var(--wf-shadow-lg)] md:p-8"
        >
          {/* 状态头 */}
          <div className="flex items-center gap-3 mb-2">
            {isError ? (
              <AlertCircle size={22} className="text-[var(--wf-danger)]" />
            ) : isDone ? (
              <CheckCircle2 size={22} className="text-[var(--wf-accent)]" />
            ) : (
              <Loader2 size={22} className="animate-spin text-[var(--wf-accent)]" />
            )}
            <h1 className="text-xl font-semibold">
              {isError ? "生成失败" : isDone ? "生成完成" : "生成中"}
            </h1>
            <span className="ml-auto text-xs tabular-nums text-[var(--wf-text-tertiary)]">
              {fmtMS(elapsed)}
            </span>
          </div>
          {meta.videoTitle && (
            <p className="mb-1 truncate text-sm font-medium text-[var(--wf-text)]">
              {meta.videoTitle}
            </p>
          )}
          <p className="mb-2 text-sm text-[var(--wf-text-secondary)]">
            {error ?? progress.msg}
          </p>
          {/* 预估行：视频时长 / 总耗时估算（一次性给出，不跟随） */}
          {(meta.videoDuration || meta.estTotal) && !isError && (
            <div className="mb-5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--wf-text-tertiary)]">
              {meta.videoDuration && (
                <span>视频时长 <span className="font-medium tabular-nums text-[var(--wf-text-secondary)]">{fmtMS(meta.videoDuration)}</span></span>
              )}
              {meta.estTotal && (
                <span>预估约 <span className="font-medium tabular-nums text-[var(--wf-text-secondary)]">{fmtMS(meta.estTotal)}</span></span>
              )}
            </div>
          )}

          <GenerationCompanion
            stage={progress.stage}
            percent={progress.percent}
            error={error}
            message={error ?? progress.msg}
            title={meta.videoTitle}
            elapsed={elapsed}
          />

          {/* 提示文案 */}
          {!isError && !isDone && (
            <p className="mt-5 text-xs leading-relaxed text-[var(--wf-text-tertiary)]">
              ASR (faster-whisper large-v3) 是最久的步骤。10 分钟的视频大约要 5-8 分钟。
              页面可以放着不动 - 完成会自动跳转。
            </p>
          )}

          {/* 阶段耗时 */}
          {visibleMetrics.length > 0 && (
            <div className="mt-6 border-t border-[var(--wf-border)] pt-4">
              <div className="flex items-center justify-between gap-3 text-xs">
                <span className="font-medium text-[var(--wf-text-secondary)]">阶段耗时</span>
                <span className="tabular-nums text-[var(--wf-text-tertiary)]">
                  {fmtMS(totalMetricSec)}
                </span>
              </div>
              <div className="mt-3 space-y-1.5">
                {visibleMetrics.map((item) => {
                  const isRunning = item.status === "running";
                  const duration = typeof item.duration_sec === "number"
                    ? fmtMS(item.duration_sec)
                    : "运行中";
                  return (
                    <div
                      key={`${item.i}-${item.stage}`}
                      className="flex items-center gap-3 text-xs text-[var(--wf-text-secondary)]"
                    >
                      <span className="w-5 shrink-0 tabular-nums text-[var(--wf-text-tertiary)]">
                        {item.i}
                      </span>
                      <span className="min-w-0 flex-1 truncate">
                        {item.label || item.stage}
                      </span>
                      <span className={`shrink-0 tabular-nums ${isRunning ? "text-[var(--wf-accent)]" : "text-[var(--wf-text-tertiary)]"}`}>
                        {duration}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* 最近事件日志（折叠） */}
          {history.length > 0 && (
            <details className="mt-6">
              <summary className="cursor-pointer text-xs text-[var(--wf-text-tertiary)]
                                  hover:text-[var(--wf-text-secondary)]">
                查看详细日志（{history.length} 条）
              </summary>
              <div className="mt-2 max-h-48 overflow-y-auto rounded-lg bg-[var(--wf-surface-muted)] p-3
                              text-[11px] font-mono leading-relaxed">
                {history.slice(-30).map((e, i) => (
                  <div key={i} className="text-[var(--wf-text-secondary)]">
                    <span className="mr-2 tabular-nums text-[var(--wf-text-tertiary)]">
                      [{e.percent.toString().padStart(3, " ")}%]
                    </span>
                    <span className="text-[var(--wf-accent)]">{e.stage}</span>
                    <span className="ml-2 text-[var(--wf-text-secondary)]">{e.msg}</span>
                  </div>
                ))}
              </div>
            </details>
          )}

          {(isError) && (
            <button
              onClick={() => router.push("/")}
              className="wf-button mt-5"
              data-size="md"
              data-variant="primary"
            >
              <span className="wf-button__content">返回首页</span>
            </button>
          )}
        </motion.div>
      </section>
    </main>
  );
}

export default function GeneratePage() {
  return (
    <Suspense fallback={
      <main className="flex min-h-[100dvh] items-center justify-center bg-[var(--wf-canvas)] text-sm text-[var(--wf-text-tertiary)]">
        加载中…
      </main>
    }>
      <GenerateInner />
    </Suspense>
  );
}
