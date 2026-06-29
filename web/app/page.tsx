"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import {
  ArrowRight,
  BookOpenCheck,
  Code2,
  Film,
  GraduationCap,
  MessageCircleQuestion,
  Presentation,
  Search,
  Sparkles,
  UploadCloud,
} from "lucide-react";
import type { ReactNode } from "react";

import { BrandMark } from "@/components/brand/BrandMark";
import { FoldingHeroStage } from "@/components/interactive/FoldingHeroStage";
import { Card, Chip } from "@/components/ui";
import { useAuth } from "@/components/AuthContext";
import { CINEMATIC_BEATS } from "./landing-model";

const PROCESS_STEPS = [
  {
    icon: UploadCloud,
    title: "导入视频",
    desc: "上传课程、教程、讲座或长视频，先把分散内容放进一个学习入口。",
    meta: "Video source",
  },
  {
    icon: BookOpenCheck,
    title: "生成章节笔记",
    desc: "自动拆分章节，提炼重点，把视频整理成可以复习的学习路径。",
    meta: "Structured notes",
  },
  {
    icon: MessageCircleQuestion,
    title: "围绕内容问答",
    desc: "基于原视频片段继续追问、复习，并定位回对应时间点。",
    meta: "Grounded Q&A",
  },
] as const;

const USE_CASES = [
  {
    icon: GraduationCap,
    title: "在线课程",
    desc: "整理课程章节、关键知识点和复习路径。",
  },
  {
    icon: Code2,
    title: "技术教程",
    desc: "记录操作步骤、关键代码片段和时间点。",
  },
  {
    icon: Presentation,
    title: "讲座访谈",
    desc: "提取观点、人物关系和内容时间线。",
  },
  {
    icon: Search,
    title: "复习备考",
    desc: "把长视频变成可搜索、可回看的复习材料。",
  },
] as const;

function LandingLinkButton({
  children,
  href,
  variant = "primary",
}: {
  children: ReactNode;
  href: string;
  variant?: "primary" | "secondary" | "ghost";
}) {
  return (
    <Link className="wf-button" data-size="lg" data-variant={variant} href={href}>
      <span className="wf-button__content">{children}</span>
    </Link>
  );
}

function LandingNav({ primaryHref, primaryLabel }: { primaryHref: string; primaryLabel: string }) {
  return (
    <header className="sticky top-0 z-30 border-b border-[var(--wf-border)] bg-[color-mix(in_srgb,var(--wf-canvas)_90%,transparent)] backdrop-blur-xl">
      <nav className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-5 sm:px-6" aria-label="首页导航">
        <Link href="/" className="inline-flex items-center gap-3 text-[var(--wf-text)]">
          <BrandMark variant="full" size="sm" label="NoteGen" />
        </Link>
        <div className="hidden flex-1 items-center justify-center gap-6 text-sm text-[var(--wf-text-secondary)] md:flex">
          <a className="transition-colors hover:text-[var(--wf-text)]" href="#how-it-works">
            功能
          </a>
          <a className="transition-colors hover:text-[var(--wf-text)]" href="#preview">
            示例
          </a>
          <a className="transition-colors hover:text-[var(--wf-text)]" href="#use-cases">
            使用场景
          </a>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Link
            href="/login"
            className="hidden rounded-[var(--wf-radius-sm)] px-3 py-2 text-sm font-medium text-[var(--wf-text-secondary)] transition-colors hover:bg-[var(--wf-surface-muted)] hover:text-[var(--wf-text)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--wf-focus)] sm:inline-flex"
          >
            登录
          </Link>
          <Link className="wf-button" data-size="sm" data-variant="primary" href={primaryHref}>
            <span className="wf-button__content">{primaryLabel}</span>
          </Link>
        </div>
      </nav>
    </header>
  );
}

function ProcessCard({
  index,
  step,
}: {
  index: number;
  step: (typeof PROCESS_STEPS)[number];
}) {
  const Icon = step.icon;

  return (
    <Card className="group relative h-full" padding="lg">
      <div className="flex items-center justify-between">
        <span className="flex h-11 w-11 items-center justify-center rounded-[var(--wf-radius-sm)] bg-[color-mix(in_srgb,var(--wf-brand-coral)_13%,var(--wf-surface))] text-[var(--wf-accent)]">
          <Icon size={20} aria-hidden="true" />
        </span>
        <span className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--wf-text-tertiary)]">
          0{index + 1}
        </span>
      </div>
      <h3 className="mt-6 text-xl font-semibold text-[var(--wf-text)]">{step.title}</h3>
      <p className="mt-3 text-sm leading-7 text-[var(--wf-text-secondary)]">{step.desc}</p>
      <div className="mt-6 h-1.5 overflow-hidden rounded-full bg-[color-mix(in_srgb,var(--wf-text)_10%,transparent)]">
        <div className="h-full w-2/3 rounded-full bg-[var(--wf-brand-coral)] transition-transform duration-200 ease-out group-hover:translate-x-4" />
      </div>
      <p className="mt-3 text-xs text-[var(--wf-text-tertiary)]">{step.meta}</p>
    </Card>
  );
}

function UseCaseCard({ item }: { item: (typeof USE_CASES)[number] }) {
  const Icon = item.icon;

  return (
    <div className="rounded-[var(--wf-radius-md)] border border-[var(--wf-border)] bg-[var(--wf-surface)] p-5 shadow-[var(--wf-shadow-sm)]">
      <Icon size={22} className="text-[var(--wf-brand-coral)]" aria-hidden="true" />
      <h3 className="mt-4 text-lg font-semibold text-[var(--wf-text)]">{item.title}</h3>
      <p className="mt-2 text-sm leading-6 text-[var(--wf-text-secondary)]">{item.desc}</p>
    </div>
  );
}

function CinematicStory() {
  const reduceMotion = useReducedMotion();

  return (
    <section className="px-5 py-12 sm:px-6 md:py-20" aria-labelledby="cinematic-story-title">
      <div className="mx-auto max-w-7xl overflow-hidden rounded-[2rem] border border-[color-mix(in_srgb,var(--wf-brand-coral)_28%,transparent)] bg-[#17120f] text-[#fff7ed] shadow-[var(--wf-shadow-lg)]">
        <div className="grid gap-0 lg:grid-cols-[0.46fr_0.54fr]">
          <div className="relative min-h-[28rem] p-7 md:p-10">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_18%_12%,rgba(228,123,89,.26),transparent_34%),linear-gradient(180deg,rgba(255,250,243,.06),transparent)]" />
            <div className="relative z-10">
              <Chip variant="accent" className="gap-2 border border-white/10 bg-white/10 text-[#ffb28f]">
                <Film size={14} aria-hidden="true" />
                Cinematic Flow
              </Chip>
              <h2 id="cinematic-story-title" className="mt-6 font-[var(--wf-font-display)] text-4xl font-semibold leading-tight tracking-[-0.04em] md:text-6xl">
                像剪一支预告片一样，把学习过程展开
              </h2>
              <p className="mt-5 max-w-md text-sm leading-7 text-[#d8c8ba]">
                入口页负责建立记忆点：视频进入、时间线滑入、纸页展开、播放指针回到证据。工作台仍然保持安静和高效。
              </p>
            </div>
            <div className="absolute bottom-8 left-8 right-8 z-10">
              <div className="h-1.5 overflow-hidden rounded-full bg-white/12">
                <motion.div
                  className="h-full rounded-full bg-[var(--wf-brand-coral)]"
                  initial={{ width: reduceMotion ? "100%" : "18%" }}
                  whileInView={{ width: "100%" }}
                  viewport={{ once: true, amount: 0.45 }}
                  transition={{ duration: reduceMotion ? 0 : 1.4, ease: "easeOut" }}
                />
              </div>
              <div className="mt-3 flex justify-between text-[10px] uppercase tracking-[0.18em] text-white/45">
                <span>Import</span>
                <span>Replay</span>
              </div>
            </div>
          </div>

          <div className="relative border-t border-white/10 bg-[#211a16] p-5 lg:border-l lg:border-t-0 md:p-8">
            <div className="pointer-events-none absolute inset-y-8 left-9 w-px bg-white/12 md:left-12" />
            <div className="space-y-4">
              {CINEMATIC_BEATS.map((beat, index) => (
                <motion.article
                  key={beat.id}
                  initial={reduceMotion ? false : { opacity: 0, x: 18 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true, amount: 0.35 }}
                  transition={{ delay: reduceMotion ? 0 : index * 0.08, duration: 0.38, ease: "easeOut" }}
                  className="relative rounded-[1.25rem] border border-white/10 bg-white/[0.055] p-5 pl-12 shadow-[0_18px_44px_rgba(0,0,0,.18)]"
                >
                  <span className="absolute left-4 top-5 inline-flex h-5 w-5 items-center justify-center rounded-full border border-[var(--wf-brand-coral)] bg-[#211a16]">
                    <span className="h-2 w-2 rounded-full bg-[var(--wf-brand-coral)]" />
                  </span>
                  <p className="text-xs font-semibold tabular-nums tracking-[0.18em] text-[#ffb28f]">{beat.timecode}</p>
                  <h3 className="mt-2 text-lg font-semibold text-[#fff7ed]">{beat.title}</h3>
                  <p className="mt-2 text-sm leading-6 text-[#d8c8ba]">{beat.copy}</p>
                </motion.article>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export default function LandingPage() {
  const { user } = useAuth();
  const primaryHref = user ? "/notebooks" : "/login?next=/notebooks";
  const primaryLabel = user ? "进入笔记本库" : "开始使用";
  const heroCtaLabel = user ? "进入笔记本库" : "开始记录";
  const finalCtaLabel = user ? "进入笔记本库" : "开始创建笔记";

  return (
    <main className="min-h-screen bg-[var(--wf-canvas)] font-[var(--wf-font-sans)] text-[var(--wf-text)]">
      <LandingNav primaryHref={primaryHref} primaryLabel={primaryLabel} />

      <section className="relative overflow-hidden px-5 py-16 sm:px-6 md:py-24">
        <div className="pointer-events-none absolute left-1/2 top-10 h-64 w-[42rem] -translate-x-1/2 rounded-full bg-[color-mix(in_srgb,var(--wf-brand-coral)_12%,transparent)] blur-3xl" />
        <div className="relative mx-auto grid max-w-7xl items-center gap-12 lg:grid-cols-[0.45fr_0.55fr]">
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.42, ease: "easeOut" }}
          >
            <Chip variant="accent" className="gap-2">
              <Sparkles size={14} aria-hidden="true" />
              Warm Fold Learning
            </Chip>
            <h1 className="mt-6 max-w-3xl font-[var(--wf-font-display)] text-5xl font-semibold leading-[1.02] tracking-[-0.04em] text-[var(--wf-text)] sm:text-6xl lg:text-7xl">
              把视频折叠成可回看的学习笔记
            </h1>
            <p className="mt-6 max-w-xl text-base leading-8 text-[var(--wf-text-secondary)] md:text-lg">
              上传或导入视频后，NoteGen 会自动整理章节、提炼重点，并支持围绕内容继续提问。适合课程、讲座、教程和长视频学习。
            </p>
            <div className="mt-9 flex flex-col gap-3 sm:flex-row">
              <LandingLinkButton href={primaryHref}>
                {heroCtaLabel} <ArrowRight size={16} aria-hidden="true" />
              </LandingLinkButton>
              <LandingLinkButton href="/notebooks?filter=public" variant="secondary">
                查看示例
              </LandingLinkButton>
            </div>
          </motion.div>

          <FoldingHeroStage />
        </div>
      </section>

      <CinematicStory />

      <section id="how-it-works" className="px-5 py-16 sm:px-6 md:py-24">
        <div className="mx-auto max-w-7xl">
          <div className="mx-auto max-w-2xl text-center">
            <p className="text-sm font-semibold text-[var(--wf-accent)]">How It Works</p>
            <h2 className="mt-3 font-[var(--wf-font-display)] text-4xl font-semibold leading-tight tracking-[-0.03em] md:text-5xl">
              从一段视频，到一套可以复习的笔记
            </h2>
            <p className="mt-5 text-base leading-8 text-[var(--wf-text-secondary)]">
              从章节定位到逐字稿，再从笔记跳回视频片段。NoteGen 把学习过程整理成一条可以反复回看的时间线。
            </p>
          </div>
          <div className="mt-12 grid gap-5 md:grid-cols-3">
            {PROCESS_STEPS.map((step, index) => (
              <ProcessCard key={step.title} index={index} step={step} />
            ))}
          </div>
        </div>
      </section>

      <section id="use-cases" className="px-5 py-16 sm:px-6 md:py-24">
        <div className="mx-auto max-w-7xl">
          <div className="grid gap-10 lg:grid-cols-[0.38fr_0.62fr] lg:items-start">
            <div>
              <p className="text-sm font-semibold text-[var(--wf-accent)]">Use Cases</p>
              <h2 className="mt-3 font-[var(--wf-font-display)] text-4xl font-semibold leading-tight tracking-[-0.03em] md:text-5xl">
                适合所有需要“看完还要记住”的内容
              </h2>
              <p className="mt-5 text-base leading-8 text-[var(--wf-text-secondary)]">
                不把首页变成工作台，只用清晰场景帮助用户判断 NoteGen 是否适合自己的学习材料。
              </p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              {USE_CASES.map((item) => (
                <UseCaseCard key={item.title} item={item} />
              ))}
            </div>
          </div>

          <Card className="mt-14 overflow-hidden text-center" padding="lg">
            <div className="mx-auto max-w-2xl">
              <BrandMark size="lg" className="mx-auto text-[var(--wf-text)]" label="NoteGen" />
              <h2 className="mt-6 font-[var(--wf-font-display)] text-3xl font-semibold tracking-[-0.03em] md:text-4xl">
                准备把你的第一个视频变成笔记吗？
              </h2>
              <p className="mt-4 text-sm leading-7 text-[var(--wf-text-secondary)]">
                无需复杂设置，从一个视频开始。
              </p>
              <div className="mt-8 inline-flex">
                <LandingLinkButton href={primaryHref}>
                  {finalCtaLabel} <ArrowRight size={16} aria-hidden="true" />
                </LandingLinkButton>
              </div>
            </div>
          </Card>
        </div>
      </section>

      <footer className="border-t border-[var(--wf-border)] px-6 py-8 text-center text-xs text-[var(--wf-text-tertiary)]">
        <span className="font-medium text-[var(--wf-text-secondary)]">NoteGen</span>
        <span className="mx-1.5">·</span>
        <span>视频学习笔记生成工具</span>
      </footer>
    </main>
  );
}
