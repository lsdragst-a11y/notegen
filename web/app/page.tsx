import Link from "next/link";
import {
  BookOpenCheck,
  Code2,
  GraduationCap,
  MessageCircleQuestion,
  Presentation,
  Search,
  Sparkles,
  UploadCloud,
} from "lucide-react";

import { BrandMark } from "@/components/brand/BrandMark";
import { CinematicStoryboard } from "@/components/interactive/CinematicStoryboard";
import { FoldingHeroStage } from "@/components/interactive/FoldingHeroStage";
import { LandingScrollRail, RevealOnScroll } from "@/components/interactive/LandingScrollMotion";
import { AuthAwareFinalAction, AuthAwareHeroActions, AuthAwareNavAction } from "@/components/landing/AuthAwareLandingActions";
import { Card, Chip } from "@/components/ui";

const PROCESS_STEPS = [
  {
    icon: UploadCloud,
    title: "导入视频",
    desc: "上传课程、讲座或教程，NoteGen 先建立来源、时长和章节候选。",
    meta: "Video source",
  },
  {
    icon: BookOpenCheck,
    title: "折成笔记页",
    desc: "沿着时间线提取章节、重点和术语，把长视频整理成可复习结构。",
    meta: "Structured notes",
  },
  {
    icon: MessageCircleQuestion,
    title: "回到证据片段",
    desc: "围绕内容继续提问，答案保留引用，并能跳回对应的视频时间点。",
    meta: "Grounded Q&A",
  },
] as const;

const USE_CASES = [
  {
    icon: GraduationCap,
    title: "在线课程",
    desc: "整理章节、关键知识点和复习路径。",
  },
  {
    icon: Code2,
    title: "技术教程",
    desc: "记录操作步骤、代码片段和对应时间戳。",
  },
  {
    icon: Presentation,
    title: "讲座访谈",
    desc: "提取观点、人物关系和内容时间线。",
  },
  {
    icon: Search,
    title: "复习备考",
    desc: "把长视频变成可搜索、可回看的学习材料。",
  },
] as const;

function LandingNav() {
  return (
    <header className="sticky top-0 z-30 border-b border-[color-mix(in_srgb,var(--wf-border)_72%,transparent)] bg-[color-mix(in_srgb,var(--wf-canvas)_76%,transparent)] backdrop-blur-xl">
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
          <AuthAwareNavAction />
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
    <Card className="group relative h-full overflow-hidden border-[color-mix(in_srgb,var(--wf-brand-coral)_18%,var(--wf-border))] bg-[linear-gradient(180deg,color-mix(in_srgb,var(--wf-surface)_96%,transparent),color-mix(in_srgb,var(--wf-surface-muted)_32%,var(--wf-surface)))] shadow-[0_18px_52px_rgba(92,58,36,.08),0_2px_8px_rgba(92,58,36,.05)] transition-transform duration-300 ease-out hover:-translate-y-1" padding="lg">
      <div className="pointer-events-none absolute inset-x-6 top-0 h-px bg-gradient-to-r from-transparent via-[var(--wf-brand-coral)] to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-70" />
      <div className="pointer-events-none absolute -right-10 -top-10 h-28 w-28 rounded-full bg-[color-mix(in_srgb,var(--wf-brand-coral)_10%,transparent)] opacity-0 blur-2xl transition-opacity duration-300 group-hover:opacity-100" />
      <div className="flex items-center justify-between">
        <span className="flex h-11 w-11 items-center justify-center rounded-[var(--wf-radius-sm)] bg-[color-mix(in_srgb,var(--wf-brand-coral)_13%,var(--wf-surface))] text-[var(--wf-accent)]">
          <Icon size={20} aria-hidden="true" />
        </span>
        <span className="font-mono text-xs font-semibold tabular-nums text-[var(--wf-text-tertiary)]">
          0{index + 1}
        </span>
      </div>
      <h3 className="mt-6 text-xl font-semibold text-[var(--wf-text)]">{step.title}</h3>
      <p className="mt-3 text-sm leading-7 text-[var(--wf-text-secondary)]">{step.desc}</p>
      <div className="mt-7 flex items-center gap-3 text-xs text-[var(--wf-text-tertiary)]">
        <span className="h-px flex-1 origin-left scale-x-75 bg-[color-mix(in_srgb,var(--wf-brand-coral)_34%,transparent)] transition-transform duration-300 group-hover:scale-x-100" />
        <span>{step.meta}</span>
      </div>
    </Card>
  );
}

function UseCaseCard({ item }: { item: (typeof USE_CASES)[number] }) {
  const Icon = item.icon;

  return (
    <div className="group relative overflow-hidden rounded-[var(--wf-radius-md)] border border-[var(--wf-border)] bg-[color-mix(in_srgb,var(--wf-surface)_94%,transparent)] p-5 shadow-[0_16px_42px_rgba(92,58,36,.07)] transition-transform duration-300 ease-out hover:-translate-y-1">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18%_0%,color-mix(in_srgb,var(--wf-brand-coral)_10%,transparent),transparent_34%)] opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
      <div className="relative">
        <Icon size={22} className="text-[var(--wf-brand-coral)]" aria-hidden="true" />
        <h3 className="mt-4 text-lg font-semibold text-[var(--wf-text)]">{item.title}</h3>
        <p className="mt-2 text-sm leading-6 text-[var(--wf-text-secondary)]">{item.desc}</p>
      </div>
    </div>
  );
}

export default function LandingPage() {
  return (
    <main className="relative isolate min-h-[100dvh] overflow-hidden bg-[var(--wf-canvas)] font-[var(--wf-font-sans)] text-[var(--wf-text)]">
      <div className="wf-paper-atmosphere" aria-hidden="true" />
      <LandingScrollRail />
      <div className="relative z-10">
        <LandingNav />

        <section className="wf-hero-workbench relative min-h-[calc(100dvh-4rem)] overflow-hidden px-5 pb-10 pt-6 sm:px-6 lg:pb-12 lg:pt-8">
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-36 bg-[linear-gradient(180deg,transparent,color-mix(in_srgb,var(--wf-canvas)_80%,#211812)_76%,color-mix(in_srgb,var(--wf-canvas)_62%,#211812)_130%)]" />

          <div className="relative mx-auto min-h-[calc(100dvh-6rem)] max-w-7xl">
            <div className="wf-hero-copy-layer relative z-30 pt-2 lg:pt-4">
              <Chip variant="accent" className="wf-hero-scene-chip gap-2 border border-[color-mix(in_srgb,var(--wf-brand-coral)_22%,transparent)] bg-[color-mix(in_srgb,var(--wf-surface)_68%,transparent)] shadow-[0_10px_26px_rgba(92,58,36,.08)] backdrop-blur">
                <Sparkles size={14} aria-hidden="true" />
                Warm Fold Learning
              </Chip>
              <h1 className="wf-hero-title mt-4 text-balance font-[var(--wf-font-display)] text-[clamp(3.35rem,9vw,8.7rem)] font-semibold leading-[0.88] tracking-[-0.055em] text-[var(--wf-text)]">
                <span className="block">把视频折叠成</span>
                <span className="block lg:translate-x-[14vw]">
                  可
                  <span className="wf-timecode-word relative inline-block px-2 text-[var(--wf-accent)]">
                    回看
                    <span className="wf-hero-title-time pointer-events-none absolute -right-10 -top-4 rounded-full border border-[color-mix(in_srgb,var(--wf-brand-coral)_28%,transparent)] bg-[color-mix(in_srgb,var(--wf-surface)_82%,transparent)] px-2 py-0.5 font-mono text-[0.18em] font-bold leading-none tracking-[0.08em] text-[var(--wf-accent)] shadow-[0_10px_24px_rgba(92,58,36,.10)]">
                      12:18
                    </span>
                  </span>
                  的学习笔记
                </span>
              </h1>
            </div>

            <div className="wf-hero-stage-layer relative z-20 -mt-10 lg:-mt-28">
              <FoldingHeroStage />
            </div>

            <div className="wf-hero-control-copy relative z-40 ml-auto max-w-[35rem] lg:absolute lg:right-0 lg:top-[20.4rem]">
              <p className="max-w-[34rem] text-base leading-8 text-[var(--wf-text-secondary)] md:text-lg">
                上传课程、讲座或教程，NoteGen 会沿着时间线提取章节、重点和问答证据。
              </p>
              <AuthAwareHeroActions />
            </div>
          </div>
        </section>

        <CinematicStoryboard />

        <section id="how-it-works" className="px-5 py-16 sm:px-6 md:py-24">
          <div className="mx-auto max-w-7xl">
            <RevealOnScroll className="mx-auto max-w-2xl text-center">
              <p className="text-sm font-semibold text-[var(--wf-accent)]">How It Works</p>
              <h2 className="mt-3 text-balance font-[var(--wf-font-display)] text-4xl font-semibold leading-tight tracking-[-0.03em] md:text-5xl">
                从一段视频，到一套可复习的笔记
              </h2>
              <p className="mt-5 text-base leading-8 text-[var(--wf-text-secondary)]">
                从章节定位到逐字证据，再从笔记跳回视频片段，NoteGen 把学习过程整理成一条能反复回看的时间线。
              </p>
            </RevealOnScroll>
            <div className="mt-12 grid gap-5 md:grid-cols-3">
              {PROCESS_STEPS.map((step, index) => (
                <RevealOnScroll key={step.title} delay={index * 0.07} variant="fold">
                  <ProcessCard index={index} step={step} />
                </RevealOnScroll>
              ))}
            </div>
          </div>
        </section>

        <section id="use-cases" className="px-5 py-16 sm:px-6 md:py-24">
          <div className="mx-auto max-w-7xl">
            <div className="grid gap-10 lg:grid-cols-[0.38fr_0.62fr] lg:items-start">
              <RevealOnScroll variant="slide">
                <p className="text-sm font-semibold text-[var(--wf-accent)]">Use Cases</p>
                <h2 className="mt-3 text-balance font-[var(--wf-font-display)] text-4xl font-semibold leading-tight tracking-[-0.03em] md:text-5xl">
                  适合所有需要看完还要记住的内容
                </h2>
                <p className="mt-5 text-base leading-8 text-[var(--wf-text-secondary)]">
                  首页负责解释价值，工作台保持安静。用户进入学习后，界面会回到高效的笔记和证据流。
                </p>
              </RevealOnScroll>
              <div className="grid gap-4 sm:grid-cols-2">
                {USE_CASES.map((item, index) => (
                  <RevealOnScroll key={item.title} delay={index * 0.06} variant="rise">
                    <UseCaseCard item={item} />
                  </RevealOnScroll>
                ))}
              </div>
            </div>

            <RevealOnScroll variant="fold" className="mt-14">
              <Card className="relative overflow-hidden border-[color-mix(in_srgb,var(--wf-brand-coral)_18%,var(--wf-border))] bg-[linear-gradient(135deg,color-mix(in_srgb,var(--wf-surface)_98%,transparent),color-mix(in_srgb,var(--wf-brand-coral)_8%,var(--wf-surface)))] text-center shadow-[0_22px_64px_rgba(92,58,36,.10)]" padding="lg">
                <div className="pointer-events-none absolute inset-x-10 top-0 h-px bg-gradient-to-r from-transparent via-[var(--wf-brand-coral)] to-transparent opacity-50" />
                <div className="mx-auto max-w-2xl">
                  <BrandMark size="lg" className="mx-auto text-[var(--wf-text)]" label="NoteGen" />
                  <h2 className="mt-6 text-balance font-[var(--wf-font-display)] text-3xl font-semibold tracking-[-0.03em] md:text-4xl">
                    准备把第一个视频变成笔记吗？
                  </h2>
                  <p className="mt-4 text-sm leading-7 text-[var(--wf-text-secondary)]">
                    从一个视频开始，把时间线、重点和证据收进同一本学习笔记。
                  </p>
                  <div className="mt-8 inline-flex">
                    <AuthAwareFinalAction />
                  </div>
                </div>
              </Card>
            </RevealOnScroll>
          </div>
        </section>

        <footer className="border-t border-[var(--wf-border)] px-6 py-8 text-center text-xs text-[var(--wf-text-tertiary)]">
          <span className="font-medium text-[var(--wf-text-secondary)]">NoteGen</span>
          <span className="mx-1.5">-</span>
          <span>视频学习笔记生成工具</span>
        </footer>
      </div>
    </main>
  );
}
