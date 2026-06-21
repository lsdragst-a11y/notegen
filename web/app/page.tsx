"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import {
  ArrowRight, BookOpenCheck, Captions, GraduationCap, Lightbulb,
  ListTree, UploadCloud,
} from "lucide-react";
import NavBar from "@/components/NavBar";
import { useAuth } from "@/components/AuthContext";
import {
  BilingualQuizTimelineVisual,
  ChaptersTimelineVisual,
  UploadTimelineVisual,
} from "@/components/LandingTimelineVisuals";

/**
 * 营销 landing（对标 notebooklm.google 官网首页）：纯介绍，不展示任何
 * 个人笔记/书签。登录后的应用首页在 /notebooks。
 */

const HOW_PEOPLE_USE = [
  {
    icon: GraduationCap,
    title: "高效助学",
    desc: "把网课、讲座录像交给 NoteGen，用章节和知识点速览快速建立全局，再按时间戳精读难点。",
    tagline: "加速学习进程，深化理解层次。",
  },
  {
    icon: BookOpenCheck,
    title: "考研复习",
    desc: "专业课长视频自动拆成章节卡片，配术语表和章末小测，复习时直接当提纲用。",
    tagline: "把 3 小时网课变成 10 分钟提纲。",
  },
  {
    icon: Lightbulb,
    title: "快速回顾",
    desc: "看过的教程想找某个细节？打开笔记搜关键词，点时间戳跳回原片对应位置。",
    tagline: "再也不用拖进度条找内容。",
  },
];

export default function LandingPage() {
  const { user } = useAuth();
  const primaryHref = user ? "/notebooks" : "/login?next=/notebooks";

  return (
    <main className="min-h-screen bg-[var(--bg)]">
      <NavBar />

      {/* Hero：居中大标题 + 单 CTA（NotebookLM 式） */}
      <section className="px-5 sm:px-6">
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: "spring", stiffness: 140, damping: 22 }}
          className="mx-auto max-w-3xl pb-16 pt-20 text-center md:pb-24 md:pt-28"
        >
          <h1 className="text-5xl font-medium leading-[1.08] tracking-tight text-[var(--fg)] md:text-6xl lg:text-7xl">
            看懂
            <span className="bg-gradient-to-r from-[#4285f4] via-[#9b72cb] to-[#1ea672] bg-clip-text text-transparent">
              任何视频
            </span>
          </h1>
          <p className="mx-auto mt-6 max-w-xl text-base leading-8 text-[var(--fg-secondary)] md:text-lg">
            NoteGen 把 B 站、YouTube 和本地的长视频整理成结构化笔记——
            章节、摘要、术语表、小测，每条内容都能跳回原片对应时间点。
          </p>
          <Link
            href={primaryHref}
            className="mt-9 inline-flex h-12 items-center gap-2 rounded-full bg-[var(--fg)] px-7
                       text-sm font-medium text-[var(--bg)] transition-opacity hover:opacity-85"
          >
            {user ? "进入我的笔记本" : "试用 NoteGen"} <ArrowRight size={15} />
          </Link>
        </motion.div>
      </section>

      {/* 特性区标题 */}
      <h2 className="px-6 pb-12 pt-6 text-center text-3xl font-medium text-[var(--fg)] md:text-4xl">
        AI 赋能的学习伙伴
      </h2>

      {/* 特性 1：上传来源（左文右图） */}
      <section className="px-5 sm:px-6">
        <div className="mx-auto grid max-w-6xl items-center gap-10 pb-20 md:grid-cols-[0.42fr_0.58fr] md:gap-14">
          <div>
            <UploadCloud size={22} className="text-[var(--fg)]" />
            <h3 className="mt-4 text-xl font-medium text-[var(--fg)]">上传来源</h3>
            <p className="mt-3 text-sm leading-7 text-[var(--fg-secondary)]">
              粘贴 B 站 / YouTube 链接，或直接拖入本地视频文件。NoteGen 自动完成
              语音识别、术语修正和内容理解，支持选择下载画质，长视频也能稳定处理。
            </p>
          </div>
          <UploadTimelineVisual />
        </div>
      </section>

      {/* 特性 2：章节与知识点（右文左图） */}
      <section className="px-5 sm:px-6">
        <div className="mx-auto grid max-w-6xl items-center gap-10 pb-20 md:grid-cols-[0.58fr_0.42fr] md:gap-14">
          <div className="order-2 md:order-none">
            <ChaptersTimelineVisual />
          </div>
          <div className="order-1 md:order-none">
            <ListTree size={22} className="text-[var(--fg)]" />
            <h3 className="mt-4 text-xl font-medium text-[var(--fg)]">章节与知识点</h3>
            <p className="mt-3 text-sm leading-7 text-[var(--fg-secondary)]">
              大模型按主题边界把视频拆成章节，配秒级时间戳。知识点卡片带关键帧截图、
              重难点标记和一句话摘要，点哪条就跳回视频哪一秒。
            </p>
          </div>
        </div>
      </section>

      {/* 特性 3：双语 + 小测（左文右图） */}
      <section className="px-5 sm:px-6">
        <div className="mx-auto grid max-w-6xl items-center gap-10 pb-24 md:grid-cols-[0.42fr_0.58fr] md:gap-14">
          <div>
            <Captions size={22} className="text-[var(--fg)]" />
            <h3 className="mt-4 text-xl font-medium text-[var(--fg)]">双语笔记与自测</h3>
            <p className="mt-3 text-sm leading-7 text-[var(--fg-secondary)]">
              全部笔记内容中英双语一键切换；每章末自动生成小测题和跨段术语表，
              学完即测，复习有抓手。
            </p>
          </div>
          <BilingualQuizTimelineVisual />
        </div>
      </section>

      {/* 大家这样用 */}
      <section className="border-t border-[var(--border)] bg-[var(--bg-elevated)] px-5 py-20 sm:px-6">
        <h2 className="pb-12 text-center text-3xl font-medium text-[var(--fg)] md:text-4xl">
          大家这样用 NoteGen
        </h2>
        <div className="mx-auto grid max-w-6xl gap-12 md:grid-cols-3">
          {HOW_PEOPLE_USE.map(({ icon: Icon, title, desc, tagline }) => (
            <div key={title}>
              <Icon size={24} className="text-[#7c8ce8]" />
              <h3 className="mt-5 text-lg font-medium text-[var(--fg)]">{title}</h3>
              <p className="mt-3 text-sm leading-7 text-[var(--fg-secondary)]">{desc}</p>
              <p className="mt-4 text-sm italic text-[var(--fg-tertiary)]">{tagline}</p>
            </div>
          ))}
        </div>
      </section>

      {/* 底部 CTA + footer */}
      <section className="px-6 py-20 text-center">
        <h2 className="text-2xl font-medium text-[var(--fg)] md:text-3xl">开始你的第一篇视频笔记</h2>
        <Link
          href={primaryHref}
          className="mt-7 inline-flex h-12 items-center gap-2 rounded-full bg-[var(--fg)] px-7
                     text-sm font-medium text-[var(--bg)] transition-opacity hover:opacity-85"
        >
          {user ? "进入我的笔记本" : "试用 NoteGen"} <ArrowRight size={15} />
        </Link>
      </section>
      <footer className="border-t border-[var(--border)] py-8 text-center text-xs text-[var(--fg-tertiary)]">
        <span className="font-medium text-[var(--fg-secondary)]">NoteGen</span>
        <span className="mx-1.5">·</span>
        <span>教学视频结构化笔记</span>
      </footer>
    </main>
  );
}
