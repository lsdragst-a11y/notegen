"use client";
import { useEffect, useMemo, useState } from "react";
import NavBar from "@/components/NavBar";
import FluidBG from "@/components/FluidBG";
import { ArrowDownUp, Check, TriangleAlert, Zap } from "lucide-react";

interface ChapterSlim {
  title: string;
  start: number;
  end: number;
  indices: number[];
}

interface PathInfo {
  n_chapters: number;
  chapters: ChapterSlim[];
  attempts: number;
  pass_via: string | null;
  repair_used: string[];
  fallback: boolean;
}

interface VideoRecord {
  stem: string;
  title: string;
  lang: string;
  duration: number;
  n_chunks: number;
  txt: PathInfo;
  mm: PathInfo;
}

interface Manifest {
  videos: VideoRecord[];
  summary: {
    n_videos: number;
    boundary_diff_pct: number;
    chapter_diff_pct: number;
    n_attempts_better: number;
    n_attempts_worse: number;
    n_mm_fallback: number;
  };
}

function fmtDuration(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

function describePass(p: PathInfo): { label: string; tone: "ok" | "warn" | "bad" } {
  if (p.fallback) return { label: "fallback (TextTiling)", tone: "bad" };
  if (p.pass_via === "repair") return { label: `repair (after ${p.attempts} attempts)`, tone: "warn" };
  if (p.pass_via?.startsWith("attempt_")) {
    const n = p.pass_via.replace("attempt_", "#");
    return {
      label: `attempt ${n}`,
      tone: n === "#1" ? "ok" : "warn",
    };
  }
  return { label: p.pass_via ?? "-", tone: "warn" };
}

function ChapterTimeline({
  chapters,
  duration,
  highlight,
}: {
  chapters: ChapterSlim[];
  duration: number;
  highlight?: Set<number>;
}) {
  return (
    <div className="relative h-10 rounded-md bg-[var(--surface-2)] border border-[var(--border)] overflow-hidden">
      {chapters.map((c, i) => {
        const left = (c.start / duration) * 100;
        const w = ((c.end - c.start) / duration) * 100;
        const isHi = highlight?.has(i);
        const hue = (i * 47) % 360;
        return (
          <div
            key={i}
            className="absolute top-0 h-full text-[10px] flex items-center px-1.5
                       border-r border-black/10 dark:border-white/10 transition-all"
            style={{
              left: `${left}%`,
              width: `${w}%`,
              background: `hsl(${hue}, ${isHi ? 65 : 45}%, ${isHi ? 65 : 80}%)`,
              opacity: isHi ? 1 : 0.7,
            }}
            title={`${c.title} (${fmtDuration(c.start)}-${fmtDuration(c.end)})`}
          >
            <span className="truncate text-black/80">{c.title}</span>
          </div>
        );
      })}
    </div>
  );
}

export default function MMAblationPage() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    fetch("/mm-ablation/manifest.json", { cache: "no-store" })
      .then(r => r.json())
      .then(setManifest)
      .catch(e => setErr(String(e)));
  }, []);

  // 默认展开最具教学价值的一个 case：EH5jx5qPabU（19→32 章过度切分极端）
  useEffect(() => {
    if (manifest && !expanded) {
      const t = manifest.videos.find(v => v.stem === "EH5jx5qPabU_p0");
      if (t) setExpanded(t.stem);
    }
  }, [manifest, expanded]);

  const verdicts = useMemo(() => {
    if (!manifest) return null;
    return manifest.videos.map(v => {
      const txtBounds = new Set(v.txt.chapters.slice(1).map(c => c.start));
      const mmBounds = new Set(v.mm.chapters.slice(1).map(c => c.start));
      const boundaryDiff = [...txtBounds].filter(x => !mmBounds.has(x)).length +
                            [...mmBounds].filter(x => !txtBounds.has(x)).length;
      const dN = v.mm.n_chapters - v.txt.n_chapters;
      return {
        stem: v.stem,
        boundaryDiff,
        dN,
        mmFaster: (v.mm.attempts > 0) && !v.mm.fallback && (v.mm.attempts < v.txt.attempts),
        mmFallback: v.mm.fallback,
      };
    });
  }, [manifest]);

  if (err) return <div className="p-8 text-red-500">载入失败：{err}</div>;
  if (!manifest) {
    return (
      <>
        <FluidBG />
        <NavBar />
        <div className="p-8 text-[var(--text-2)]">加载中…</div>
      </>
    );
  }

  const s = manifest.summary;

  return (
    <>
      <FluidBG />
      <NavBar />
      <main className="relative max-w-7xl mx-auto px-6 py-10 space-y-8">
        <header className="space-y-3">
          <h1 className="text-3xl font-semibold tracking-tight">
            多模态切分 ablation
          </h1>
          <p className="text-[var(--text-2)] max-w-3xl leading-relaxed">
            对比同一视频在<strong>纯文本</strong>和 <strong>+视觉信号 (CLIP cosine 相似度)</strong>
            两种路径下的 Qwen 章节切分结果。视觉信号不再做线性加权，而是格式化成
            自然语言 cue 喂给 LLM 作 tie-breaker。
          </p>
        </header>

        {/* 汇总卡片 */}
        <section className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <SummaryCard
            label="视频数"
            value={s.n_videos}
            sub="完整跑通两路"
            icon={<ArrowDownUp size={14} />}
          />
          <SummaryCard
            label="边界差异"
            value={`${s.boundary_diff_pct}%`}
            sub="视觉信号确实影响 LLM"
            tone="hi"
          />
          <SummaryCard
            label="章数变化"
            value={`${s.chapter_diff_pct}%`}
            sub="多数视频章节数会变"
          />
          <SummaryCard
            label="mm 加速"
            value={s.n_attempts_better}
            sub={`/${s.n_videos} 视频更少 attempt`}
            tone="ok"
            icon={<Zap size={14} />}
          />
          <SummaryCard
            label="mm fallback"
            value={s.n_mm_fallback}
            sub={`/${s.n_videos} 视觉信号误导`}
            tone={s.n_mm_fallback > 0 ? "warn" : undefined}
            icon={<TriangleAlert size={14} />}
          />
        </section>

        {/* 主表 */}
        <section className="rounded-xl border border-[var(--border)] overflow-hidden">
          <div className="px-4 py-3 border-b border-[var(--border)] bg-[var(--surface-2)]
                          flex items-center justify-between">
            <h2 className="text-sm font-medium">9 视频对比 · 点击展开时间轴</h2>
            <span className="text-xs text-[var(--text-2)]">
              attempt 1 = LLM 一次过 | repair = 程序化兜底救活
            </span>
          </div>
          <div className="divide-y divide-[var(--border)]">
            {manifest.videos.map(v => {
              const vd = verdicts!.find(x => x.stem === v.stem)!;
              const txtPass = describePass(v.txt);
              const mmPass = describePass(v.mm);
              const isOpen = expanded === v.stem;
              return (
                <div key={v.stem}>
                  <button
                    onClick={() => setExpanded(isOpen ? null : v.stem)}
                    className="w-full px-4 py-3 grid grid-cols-12 items-center gap-3
                               hover:bg-[var(--surface-2)] transition-colors text-left"
                  >
                    <div className="col-span-12 md:col-span-4 min-w-0">
                      <div className="text-sm font-medium truncate">{v.title}</div>
                      <div className="text-xs text-[var(--text-2)] mt-0.5">
                        {v.lang === "en" ? "🇬🇧 " : "🇨🇳 "}
                        {fmtDuration(v.duration)} · {v.n_chunks} segments
                      </div>
                    </div>
                    <div className="col-span-6 md:col-span-3 text-xs">
                      <div className="text-[var(--text-2)] mb-0.5">纯文本</div>
                      <div className="font-medium">
                        {v.txt.n_chapters} 章 · <PassChip {...txtPass} />
                      </div>
                    </div>
                    <div className="col-span-6 md:col-span-3 text-xs">
                      <div className="text-[var(--text-2)] mb-0.5">+视觉信号</div>
                      <div className="font-medium">
                        {v.mm.n_chapters} 章{" "}
                        <span className={
                          vd.dN > 0 ? "text-amber-500" :
                          vd.dN < 0 ? "text-sky-500" : "text-[var(--text-2)]"
                        }>
                          ({vd.dN > 0 ? "+" : ""}{vd.dN})
                        </span>
                        {" · "}<PassChip {...mmPass} />
                      </div>
                    </div>
                    <div className="col-span-12 md:col-span-2 text-right text-xs">
                      <span className="text-[var(--text-2)]">边界差 </span>
                      <span className="font-medium">{vd.boundaryDiff}</span>
                      {vd.mmFaster && (
                        <span className="ml-2 inline-flex items-center gap-0.5
                                         text-emerald-500" title="mm 减少了 attempt 数">
                          <Zap size={12} />
                        </span>
                      )}
                    </div>
                  </button>
                  {isOpen && (
                    <div className="px-4 pb-5 bg-[var(--surface)] space-y-3 border-t
                                    border-[var(--border)]">
                      <div className="pt-3">
                        <div className="text-xs text-[var(--text-2)] mb-1.5">
                          纯文本路径（{v.txt.n_chapters} 章）
                        </div>
                        <ChapterTimeline
                          chapters={v.txt.chapters}
                          duration={v.duration}
                        />
                      </div>
                      <div>
                        <div className="text-xs text-[var(--text-2)] mb-1.5">
                          +视觉信号路径（{v.mm.n_chapters} 章{vd.dN !== 0 &&
                            `，相对 ${vd.dN > 0 ? "切更细" : "合并更粗"}`}）
                        </div>
                        <ChapterTimeline
                          chapters={v.mm.chapters}
                          duration={v.duration}
                        />
                      </div>
                      <Insight v={v} vd={vd} />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>

        {/* 结论 */}
        <section className="rounded-xl border border-[var(--border)] p-5 bg-[var(--surface-2)]
                            text-sm leading-relaxed space-y-2">
          <h2 className="font-semibold">论文 §5.4 结论</h2>
          <p className="text-[var(--text-2)]">
            视觉信号 <strong>确实进入 LLM 决策</strong>（9/9 边界差异）。在文本主题
            模糊的视频上，视觉 cue 能<strong>加速 retry 通过</strong>
            （计网 p44 3→2、OS 哲学家 2→1、AI Agents 英文 2→1）。
            但 PPT/教程类视频上视觉信号噪声大——英文 AI Agents 教程被 mm 路径切了 32 章
            （vs 纯文本 19 章）<strong>过度切分</strong>，
            1 个视频（Tina Huang 编程教程）mm 路径反而触发 <strong>fallback</strong>。
          </p>
          <p className="text-[var(--text-2)]">
            因此论文采纳的<strong>默认配置是纯文本 LLM 切分</strong>，
            <code className="px-1.5 py-0.5 rounded bg-[var(--surface)] text-xs">--keyframes</code>
            作为 opt-in 的 ablation 工具：实拍视频域可能受益；PPT 域风险大。
          </p>
        </section>
      </main>
    </>
  );
}

function SummaryCard({
  label, value, sub, icon, tone,
}: {
  label: string;
  value: string | number;
  sub?: string;
  icon?: React.ReactNode;
  tone?: "ok" | "warn" | "hi";
}) {
  const ring =
    tone === "ok" ? "ring-emerald-500/20 bg-emerald-500/5" :
    tone === "warn" ? "ring-amber-500/30 bg-amber-500/5" :
    tone === "hi" ? "ring-sky-500/30 bg-sky-500/5" :
    "ring-[var(--border)]";
  return (
    <div className={`rounded-xl ring-1 ${ring} p-3.5 backdrop-blur-sm`}>
      <div className="flex items-center gap-1.5 text-xs text-[var(--text-2)] mb-1">
        {icon}{label}
      </div>
      <div className="text-2xl font-semibold tracking-tight">{value}</div>
      {sub && <div className="text-[11px] text-[var(--text-2)] mt-0.5">{sub}</div>}
    </div>
  );
}

function PassChip({ label, tone }: { label: string; tone: "ok" | "warn" | "bad" }) {
  const cls =
    tone === "ok" ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400" :
    tone === "warn" ? "bg-amber-500/15 text-amber-600 dark:text-amber-400" :
    "bg-red-500/15 text-red-600 dark:text-red-400";
  return (
    <span className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] ${cls}`}>
      {tone === "ok" && <Check size={10} />}
      {label}
    </span>
  );
}

function Insight({
  v, vd,
}: {
  v: VideoRecord;
  vd: { boundaryDiff: number; dN: number; mmFaster: boolean; mmFallback: boolean };
}) {
  const bits: string[] = [];
  if (vd.mmFaster) {
    bits.push(`mm 让 LLM 一次过（${v.txt.attempts}→${v.mm.attempts} attempts）—— 视觉信号给文本切点提供了 disambiguation`);
  }
  if (vd.mmFallback) {
    bits.push(`mm 路径反而触发 fallback——视觉信号在该视频上误导 LLM 漏 chunks，最终 fallback 到 TextTiling`);
  }
  if (vd.dN > 3) {
    bits.push(`mm 章数大幅增加（+${vd.dN}）—— LLM 把 slide flip 误判为章节切点（PPT/教程类视频常见）`);
  } else if (vd.dN < -3) {
    bits.push(`mm 章数大幅减少（${vd.dN}）—— 视觉相似的相邻章被合并`);
  }
  if (v.mm.repair_used.length > 0) {
    bits.push(`mm 路径触发 repair：${v.mm.repair_used.join(" + ")}`);
  }
  if (!bits.length) {
    bits.push("两路结果接近，视觉信号微调了边界但未影响整体结构");
  }
  return (
    <div className="text-xs text-[var(--text-2)] pt-1 space-y-1">
      {bits.map((b, i) => (
        <div key={i} className="flex gap-1.5">
          <span className="text-[var(--accent)]">▸</span>
          <span>{b}</span>
        </div>
      ))}
    </div>
  );
}
