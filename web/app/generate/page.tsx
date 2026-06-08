"use client";
import { useEffect, useRef, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { CheckCircle2, AlertCircle, Loader2 } from "lucide-react";
import NavBar from "@/components/NavBar";
import FluidBG from "@/components/FluidBG";
import ParticleBG from "@/components/ParticleBG";
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

  return (
    <main className="relative min-h-screen">
      <FluidBG />
      <ParticleBG />
      <NavBar />

      <section className="relative z-10 max-w-2xl mx-auto px-6 pt-20 pb-20">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: "spring", stiffness: 160, damping: 22 }}
          className="apple-card p-8"
        >
          {/* 状态头 */}
          <div className="flex items-center gap-3 mb-2">
            {isError ? (
              <AlertCircle size={22} className="text-[#ff3b30]" />
            ) : isDone ? (
              <CheckCircle2 size={22} className="text-[#30d158]" />
            ) : (
              <Loader2 size={22} className="text-[var(--accent)] animate-spin" />
            )}
            <h1 className="text-xl font-semibold">
              {isError ? "生成失败" : isDone ? "生成完成" : "生成中"}
            </h1>
            <span className="ml-auto text-xs text-[var(--fg-tertiary)] tabular-nums">
              {fmtMS(elapsed)}
            </span>
          </div>
          {meta.videoTitle && (
            <p className="text-sm font-medium text-[var(--fg)] mb-1 truncate">
              {meta.videoTitle}
            </p>
          )}
          <p className="text-sm text-[var(--fg-secondary)] mb-2">
            {error ?? progress.msg}
          </p>
          {/* 预估行：视频时长 / 总耗时估算（一次性给出，不跟随） */}
          {(meta.videoDuration || meta.estTotal) && !isError && (
            <div className="text-xs text-[var(--fg-tertiary)] mb-5 flex flex-wrap gap-x-4 gap-y-1">
              {meta.videoDuration && (
                <span>视频时长 <span className="tabular-nums font-medium text-[var(--fg-secondary)]">{fmtMS(meta.videoDuration)}</span></span>
              )}
              {meta.estTotal && (
                <span>预估约 <span className="tabular-nums font-medium text-[var(--fg-secondary)]">{fmtMS(meta.estTotal)}</span></span>
              )}
            </div>
          )}

          {/* 进度条 */}
          {!isError && (
            <>
              <div className="relative h-2.5 rounded-full bg-[var(--bg-muted)] overflow-hidden mb-2">
                <motion.div
                  className="absolute inset-y-0 left-0 rounded-full
                             bg-gradient-to-r from-[var(--accent)] to-[#bf5af2]"
                  initial={{ width: 0 }}
                  animate={{ width: `${progress.percent}%` }}
                  transition={{ type: "spring", stiffness: 80, damping: 20 }}
                />
              </div>
              <div className="flex items-center justify-between text-xs text-[var(--fg-tertiary)] tabular-nums">
                <span>{progress.stage}</span>
                <span>{progress.percent}%</span>
              </div>
            </>
          )}

          {/* 阶段说明 */}
          {!isError && !isDone && (
            <div className="mt-6 grid grid-cols-4 gap-2 text-[10px]">
              {[
                { name: "下载", min: 0, max: 12 },
                { name: "ASR", min: 12, max: 60 },
                { name: "摘要", min: 60, max: 78 },
                { name: "关键帧", min: 78, max: 100 },
              ].map((s) => {
                const done = progress.percent >= s.max;
                const active = progress.percent >= s.min && progress.percent < s.max;
                return (
                  <div
                    key={s.name}
                    className={`rounded-lg p-2 text-center transition-colors
                                ${done ? "bg-[var(--accent)] text-white"
                                      : active ? "bg-[var(--bg-muted)] text-[var(--fg)] ring-1 ring-[var(--accent)]"
                                              : "bg-[var(--bg-muted)] text-[var(--fg-tertiary)]"}`}
                  >
                    {s.name}
                  </div>
                );
              })}
            </div>
          )}

          {/* 提示文案 */}
          {!isError && !isDone && (
            <p className="mt-5 text-xs text-[var(--fg-tertiary)] leading-relaxed">
              ASR (faster-whisper large-v3) 是最久的步骤。10 分钟的视频大约要 5-8 分钟。
              页面可以放着不动 — 完成会自动跳转。
            </p>
          )}

          {/* 最近事件日志（折叠） */}
          {history.length > 0 && (
            <details className="mt-6">
              <summary className="text-xs text-[var(--fg-tertiary)] cursor-pointer
                                  hover:text-[var(--fg-secondary)]">
                查看详细日志（{history.length} 条）
              </summary>
              <div className="mt-2 max-h-48 overflow-y-auto bg-[var(--bg-muted)] rounded-lg p-3
                              text-[11px] font-mono leading-relaxed">
                {history.slice(-30).map((e, i) => (
                  <div key={i} className="text-[var(--fg-secondary)]">
                    <span className="text-[var(--fg-tertiary)] tabular-nums mr-2">
                      [{e.percent.toString().padStart(3, " ")}%]
                    </span>
                    <span className="text-[var(--accent)]">{e.stage}</span>
                    <span className="text-[var(--fg-secondary)] ml-2">{e.msg}</span>
                  </div>
                ))}
              </div>
            </details>
          )}

          {(isError) && (
            <button
              onClick={() => router.push("/")}
              className="apple-button mt-5"
            >
              返回首页
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
      <main className="min-h-screen flex items-center justify-center text-sm text-[var(--fg-tertiary)]">
        加载中…
      </main>
    }>
      <GenerateInner />
    </Suspense>
  );
}
