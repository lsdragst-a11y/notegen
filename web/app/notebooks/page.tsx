"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  BookOpen,
  Clock,
  Code2,
  FileVideo,
  FlaskConical,
  GraduationCap,
  Layers,
  MessageSquareText,
  Plus,
  Search,
  Sparkles,
  Trash2,
  Video,
  Wrench,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import CreateNotePanel from "@/components/CreateNotePanel";
import NavBar from "@/components/NavBar";
import RequireAuth from "@/components/RequireAuth";
import { useAuth } from "@/components/AuthContext";
import { Button, Card, Chip, IconButton, Input } from "@/components/ui";
import { deleteNote, fetchHistory, fetchMyNotes } from "@/lib/api";
import { fetchCatalog, formatDuration } from "@/lib/notes";
import type { CatalogItem, HistoryItem, NoteView } from "@/lib/types";
import {
  canCreateNotebook,
  getPublicDemoRank,
  getVisibleNotebookFilters,
  getNotebookHeroCopy,
  isFeaturedPublicDemo,
  parseNotebookFilter,
  parsePublicDemo,
  shouldAllowPublicCatalog,
  shouldShowProgressPanel,
  type FeaturedPublicDemoId,
  type NotebookFilter as Filter,
} from "./filter";

interface CardItem {
  id: string;
  title: string;
  domain: string;
  duration_sec: number;
  chunks: number;
  chapters: number;
  uploader: string;
  mine: boolean;
  recentAt?: number;
}

const DOMAIN_STYLE: Record<string, { icon: LucideIcon }> = {
  编程教学: { icon: Code2 },
  考研专业课: { icon: GraduationCap },
  工具教程: { icon: Wrench },
  科普: { icon: FlaskConical },
  Vlog: { icon: Video },
  时评: { icon: MessageSquareText },
  数码评测: { icon: FileVideo },
};

function domainStyle(domain: string) {
  return DOMAIN_STYLE[domain] ?? { icon: BookOpen };
}

function normalizeTime(value?: number | null) {
  if (!value) return 0;
  return value > 1_000_000_000_000 ? value : value * 1000;
}

function formatRelativeTime(value?: number) {
  if (!value) return "暂无进度";
  const diff = Date.now() - normalizeTime(value);
  const minutes = Math.max(1, Math.floor(diff / 60_000));
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} 天前`;
  return new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric" }).format(new Date(normalizeTime(value)));
}

function jobStatusLabel(status: HistoryItem["status"]) {
  if (status === "queued") return "排队中";
  if (status === "running") return "生成中";
  if (status === "done") return "已完成";
  if (status === "failed") return "失败";
  if (status === "interrupted") return "已中断";
  return status;
}

function matchesSearch(item: CardItem, query: string) {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return [item.title, item.domain, item.uploader].some((value) => value.toLowerCase().includes(q));
}

function NoteCard({
  deleting,
  item,
  onDelete,
}: {
  deleting: boolean;
  item: CardItem;
  onDelete: (item: CardItem) => void;
}) {
  const reduceMotion = useReducedMotion();
  const { icon: Icon } = domainStyle(item.domain);

  return (
    <motion.article
      initial={reduceMotion ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.24, ease: "easeOut" }}
      className="group relative"
    >
      <Card className="flex min-h-56 flex-col overflow-hidden" padding="none">
        {item.mine ? (
          <div className="absolute right-3 top-3 z-10 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100">
            <IconButton
              aria-label={`删除 ${item.title}`}
              disabled={deleting}
              loading={deleting}
              onClick={() => onDelete(item)}
              size="sm"
              variant="danger"
            >
              <Trash2 size={14} aria-hidden="true" />
            </IconButton>
          </div>
        ) : null}

        <Link href={`/notes/${item.id}`} className="flex flex-1 flex-col p-5 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--wf-focus)]">
          <div className="flex items-start justify-between gap-3">
            <span className="inline-flex h-11 w-11 items-center justify-center rounded-[var(--wf-radius-sm)] bg-[color-mix(in_srgb,var(--wf-brand-coral)_13%,var(--wf-surface))] text-[var(--wf-accent)]">
              <Icon size={20} aria-hidden="true" />
            </span>
            <Chip variant={item.mine ? "accent" : "neutral"} size="sm">
              {item.mine ? "我的" : "示例"}
            </Chip>
          </div>
          <h3 className="mt-5 min-h-12 text-[15px] font-semibold leading-6 text-[var(--wf-text)]">
            {item.title}
          </h3>
          <p className="mt-2 text-xs text-[var(--wf-text-tertiary)]">{item.uploader || "未知来源"}</p>
          <div className="mt-auto flex flex-wrap gap-2 pt-5 text-xs text-[var(--wf-text-tertiary)]">
            <span className="inline-flex items-center gap-1 tabular-nums">
              <Clock size={12} aria-hidden="true" />
              {formatDuration(item.duration_sec)}
            </span>
            <span className="inline-flex items-center gap-1">
              <Layers size={12} aria-hidden="true" />
              {item.chapters} 章
            </span>
            <span>{item.chunks} 段</span>
          </div>
          <div className="mt-4 flex items-center justify-between border-t border-[var(--wf-border)] pt-3">
            <span className="rounded-full bg-[var(--wf-surface-muted)] px-2.5 py-1 text-xs text-[var(--wf-text-secondary)]">
              {item.domain}
            </span>
            <span className="text-xs text-[var(--wf-text-tertiary)]">{formatRelativeTime(item.recentAt)}</span>
          </div>
        </Link>
      </Card>
    </motion.article>
  );
}

function FeaturedDemoCard({
  item,
  selected,
  userCanAsk,
}: {
  item: CardItem;
  selected: boolean;
  userCanAsk: boolean;
}) {
  const { icon: Icon } = domainStyle(item.domain);

  return (
    <article
      data-selected-demo={selected ? "true" : undefined}
      className={`rounded-[var(--wf-radius-md)] border bg-[var(--wf-surface)] shadow-[var(--wf-shadow-sm)] transition-colors ${
        selected ? "border-[var(--wf-accent)] ring-2 ring-[color-mix(in_srgb,var(--wf-brand-coral)_18%,transparent)]" : "border-[var(--wf-border)]"
      }`}
    >
      <Link href={`/notes/${item.id}`} className="flex h-full flex-col p-5 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--wf-focus)]">
        <div className="flex items-start justify-between gap-3">
          <span className="inline-flex h-11 w-11 items-center justify-center rounded-[var(--wf-radius-sm)] bg-[color-mix(in_srgb,var(--wf-brand-coral)_12%,var(--wf-surface))] text-[var(--wf-accent)]">
            <Icon size={20} aria-hidden="true" />
          </span>
          <Chip variant={selected ? "accent" : "neutral"} size="sm">
            {selected ? "30 秒演示" : "精选示例"}
          </Chip>
        </div>
        <h3 className="mt-5 text-base font-semibold leading-6 text-[var(--wf-text)]">{item.title}</h3>
        <p className="mt-2 line-clamp-2 text-sm leading-6 text-[var(--wf-text-secondary)]">
          {item.uploader || item.domain}
        </p>
        <div className="mt-5 grid grid-cols-2 gap-2 text-xs text-[var(--wf-text-secondary)]">
          <span className="rounded-[var(--wf-radius-sm)] bg-[var(--wf-surface-muted)] px-2.5 py-2">
            <Layers size={13} className="mb-1 text-[var(--wf-accent)]" aria-hidden="true" />
            {item.chapters} 章
          </span>
          <span className="rounded-[var(--wf-radius-sm)] bg-[var(--wf-surface-muted)] px-2.5 py-2">
            <Sparkles size={13} className="mb-1 text-[var(--wf-accent)]" aria-hidden="true" />
            {item.chunks} 个重点
          </span>
          <span className="rounded-[var(--wf-radius-sm)] bg-[var(--wf-surface-muted)] px-2.5 py-2">
            <MessageSquareText size={13} className="mb-1 text-[var(--wf-accent)]" aria-hidden="true" />
            {userCanAsk ? "可问答" : "登录后可问答"}
          </span>
          <span className="rounded-[var(--wf-radius-sm)] bg-[var(--wf-surface-muted)] px-2.5 py-2">
            <Video size={13} className="mb-1 text-[var(--wf-accent)]" aria-hidden="true" />
            可跳回视频证据
          </span>
        </div>
        <div className="mt-5 flex items-center justify-between border-t border-[var(--wf-border)] pt-3 text-xs">
          <span className="text-[var(--wf-text-tertiary)]">{formatDuration(item.duration_sec)}</span>
          <span className="font-semibold text-[var(--wf-accent)]">打开示例</span>
        </div>
      </Link>
    </article>
  );
}

function EmptyState({
  filter,
  onCreate,
  query,
}: {
  filter: Filter;
  onCreate: () => void;
  query: string;
}) {
  const hasQuery = query.trim().length > 0;
  const title = hasQuery ? "没有找到匹配的笔记" : filter === "mine" ? "还没有自己的笔记" : "暂无可显示的笔记";
  const desc = hasQuery
    ? "换一个关键词，或清空搜索后再看全部内容。"
    : filter === "mine"
      ? "从一个课程、讲座或教程视频开始，生成第一本可复习的笔记。"
      : "当前筛选下没有内容。";

  return (
    <Card className="col-span-full text-center" padding="lg" variant="outlined">
      <BookOpen size={28} className="mx-auto text-[var(--wf-accent)]" aria-hidden="true" />
      <h2 className="mt-4 text-lg font-semibold text-[var(--wf-text)]">{title}</h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-[var(--wf-text-secondary)]">{desc}</p>
      {!hasQuery && filter === "mine" ? (
        <Button className="mt-6" onClick={onCreate}>
          <Plus size={15} aria-hidden="true" />
          新建笔记本
        </Button>
      ) : null}
    </Card>
  );
}

function NotebooksInner({
  initialDemoId,
  initialFilter,
}: {
  initialDemoId: FeaturedPublicDemoId;
  initialFilter: Filter;
}) {
  const { loading: authLoading, user } = useAuth();
  const [pub, setPub] = useState<CatalogItem[] | null>(null);
  const [mine, setMine] = useState<NoteView[] | null>(null);
  const [history, setHistory] = useState<HistoryItem[] | null>(null);
  const [filter, setFilter] = useState<Filter>(initialFilter);
  const [query, setQuery] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<CardItem | null>(null);
  const [delId, setDelId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const canCreate = canCreateNotebook(user);
  const activeFilter = !authLoading && !user ? "public" : filter;
  const visibleFilters = getVisibleNotebookFilters(user);
  const guestPublicCatalog = !authLoading && shouldAllowPublicCatalog(activeFilter) && !user;
  const heroCopy = getNotebookHeroCopy(activeFilter, user);
  const showProgressPanel = shouldShowProgressPanel(activeFilter, user);

  useEffect(() => {
    if (authLoading) return;
    let alive = true;
    fetchCatalog()
      .then((d) => { if (alive) setPub(d); })
      .catch(() => { if (alive) setPub([]); });
    if (!guestPublicCatalog) {
      fetchMyNotes()
        .then((d) => { if (alive) setMine(d); })
        .catch(() => { if (alive) setMine([]); });
      fetchHistory()
        .then((d) => { if (alive) setHistory(d); })
        .catch(() => { if (alive) setHistory([]); });
    }
    return () => { alive = false; };
  }, [authLoading, guestPublicCatalog]);

  useEffect(() => {
    if (!createOpen && !confirmDelete) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setCreateOpen(false);
        setConfirmDelete(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [createOpen, confirmDelete]);

  const loading = authLoading || (guestPublicCatalog ? pub === null : pub === null || mine === null || history === null);

  const recentByNote = useMemo(() => {
    const map = new Map<string, number>();
    for (const item of history ?? []) {
      if (!item.note_id) continue;
      const current = map.get(item.note_id) ?? 0;
      map.set(item.note_id, Math.max(current, item.updated_at, item.finished_at ?? 0, item.created_at));
    }
    return map;
  }, [history]);

  const mineCards: CardItem[] = useMemo(() => (user ? (mine ?? []) : []).map((n) => ({
    id: n.id,
    title: n.title,
    domain: n.domain,
    duration_sec: n.duration_sec,
    chunks: n.chunks,
    chapters: n.chapters,
    uploader: n.uploader,
    mine: true,
    recentAt: recentByNote.get(n.id),
  })), [mine, recentByNote, user]);

  const publicCards: CardItem[] = useMemo(() => {
    const mineIds = new Set(mineCards.map((c) => c.id));
    return (pub ?? [])
      .filter((p) => !mineIds.has(p.id))
      .map((p) => ({
        id: p.id,
        title: p.title,
        domain: p.domain,
        duration_sec: p.duration_sec,
        chunks: p.chunks,
        chapters: p.chapters,
        uploader: p.uploader,
        mine: false,
      }));
  }, [mineCards, pub]);

  const featuredPublicItems = useMemo(() => {
    return publicCards
      .filter((item) => isFeaturedPublicDemo(item.id))
      .sort((a, b) => {
        if (a.id === initialDemoId) return -1;
        if (b.id === initialDemoId) return 1;
        return getPublicDemoRank(a.id) - getPublicDemoRank(b.id);
      });
  }, [initialDemoId, publicCards]);

  const items: CardItem[] = useMemo(() => {
    const source = activeFilter === "mine" ? mineCards : activeFilter === "public" ? publicCards : [...mineCards, ...publicCards];
    return source
      .filter((item) => matchesSearch(item, query))
      .sort((a, b) => {
        if (a.mine !== b.mine) return a.mine ? -1 : 1;
        if (!a.mine && !b.mine) {
          const aRank = getPublicDemoRank(a.id);
          const bRank = getPublicDemoRank(b.id);
          if (aRank !== bRank) {
            if (!Number.isFinite(aRank)) return 1;
            if (!Number.isFinite(bRank)) return -1;
            return aRank - bRank;
          }
        }
        return (b.recentAt ?? 0) - (a.recentAt ?? 0);
      });
  }, [activeFilter, mineCards, publicCards, query]);

  const latestJob = useMemo(() => {
    return [...(history ?? [])].sort((a, b) => b.updated_at - a.updated_at)[0] ?? null;
  }, [history]);

  async function remove(item: CardItem) {
    setDelId(item.id);
    setDeleteError(null);
    try {
      await deleteNote(item.id);
      setMine((value) => (value ?? []).filter((x) => x.id !== item.id));
      setConfirmDelete(null);
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : String(e));
    } finally {
      setDelId(null);
    }
  }

  return (
    <main className="min-h-screen bg-[var(--wf-canvas)] text-[var(--wf-text)]">
      <NavBar suppressOfflineBadge={guestPublicCatalog} />

      <section className="mx-auto max-w-7xl px-5 pb-24 pt-8 sm:px-6">
        <div className={`grid gap-5 ${showProgressPanel ? "lg:grid-cols-[1fr_22rem]" : ""}`}>
          <Card padding="lg" className="overflow-hidden">
            <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
              <div>
                <Chip variant="accent" className="gap-2">
                  <Sparkles size={14} aria-hidden="true" />
                  {heroCopy.eyebrow}
                </Chip>
                <h1 className="mt-5 font-[var(--wf-font-display)] text-4xl font-semibold tracking-[-0.04em] md:text-5xl">
                  {heroCopy.title}
                </h1>
                <p className="mt-4 max-w-2xl text-sm leading-7 text-[var(--wf-text-secondary)]">
                  {heroCopy.description}
                </p>
              </div>
              {canCreate ? (
                <Button onClick={() => setCreateOpen(true)} size="lg">
                  <Plus size={16} aria-hidden="true" />
                  {heroCopy.cta}
                </Button>
              ) : (
                <Link href="/login?next=/notebooks" className="wf-button" data-size="lg" data-variant="primary">
                  <span className="wf-button__content">{heroCopy.cta}</span>
                </Link>
              )}
            </div>
          </Card>

          {showProgressPanel ? (
            <Card padding="lg">
              <p className="text-sm font-semibold text-[var(--wf-text)]">最近进度</p>
              {loading ? (
                <div className="mt-4 space-y-3">
                  <div className="h-4 w-2/3 animate-pulse rounded bg-[var(--wf-surface-muted)]" />
                  <div className="h-3 w-full animate-pulse rounded bg-[var(--wf-surface-muted)]" />
                </div>
              ) : latestJob ? (
                <div className="mt-4">
                  <div className="flex items-center justify-between gap-3">
                    <Chip variant={latestJob.status === "failed" ? "danger" : "accent"} size="sm">
                      {jobStatusLabel(latestJob.status)}
                    </Chip>
                    <span className="text-xs text-[var(--wf-text-tertiary)]">
                      {formatRelativeTime(latestJob.updated_at)}
                    </span>
                  </div>
                  <p className="mt-3 truncate text-sm font-medium text-[var(--wf-text)]">{latestJob.source}</p>
                  <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-[color-mix(in_srgb,var(--wf-text)_10%,transparent)]">
                    <div
                      className="h-full rounded-full bg-[var(--wf-brand-coral)]"
                      style={{ width: `${Math.max(8, Math.min(100, latestJob.runtime?.percent ?? (latestJob.status === "done" ? 100 : 12)))}%` }}
                    />
                  </div>
                  <Link href="/history" className="mt-4 inline-flex text-xs font-medium text-[var(--wf-accent)] hover:underline">
                    查看任务历史
                  </Link>
                </div>
              ) : (
                <p className="mt-4 text-sm leading-6 text-[var(--wf-text-secondary)]">
                  还没有生成任务。创建一本笔记后，这里会显示最近处理进度。
                </p>
              )}
            </Card>
          ) : null}
        </div>

        {activeFilter === "public" && !loading && featuredPublicItems.length > 0 ? (
          <section className="mt-6">
            <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
              <div>
                <h2 className="text-lg font-semibold text-[var(--wf-text)]">精选公开示例</h2>
                <p className="mt-1 max-w-2xl text-sm leading-6 text-[var(--wf-text-secondary)]">
                  从完整视频笔记开始看产品能力：章节、重点、问答和可回放证据都在同一个工作台里。
                </p>
              </div>
              <span className="text-xs text-[var(--wf-text-tertiary)]">
                首页演示会优先打开第一张示例
              </span>
            </div>
            <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
              {featuredPublicItems.map((item) => (
                <FeaturedDemoCard
                  key={item.id}
                  item={item}
                  selected={item.id === initialDemoId}
                  userCanAsk={Boolean(user)}
                />
              ))}
            </div>
          </section>
        ) : null}

        <div className="mt-6 flex flex-col gap-4 rounded-[var(--wf-radius-md)] border border-[var(--wf-border)] bg-[var(--wf-surface)] p-4 shadow-[var(--wf-shadow-sm)] md:flex-row md:items-center">
          <div className="flex flex-wrap gap-2">
            {visibleFilters.map((f) => (
              <button
                key={f.key}
                type="button"
                onClick={() => setFilter(f.key)}
                className="rounded-full px-3 py-1.5 text-xs font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--wf-focus)]"
                style={{
                  background: activeFilter === f.key ? "color-mix(in srgb, var(--wf-brand-coral) 14%, var(--wf-surface))" : "transparent",
                  color: activeFilter === f.key ? "var(--wf-accent)" : "var(--wf-text-secondary)",
                }}
              >
                {f.label}
              </button>
            ))}
          </div>
          <label className="relative md:ml-auto md:w-80">
            <span className="sr-only">搜索笔记</span>
            <Search
              size={15}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--wf-text-tertiary)]"
              aria-hidden="true"
            />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索标题、领域或来源"
              className="pl-9"
            />
          </label>
          <span className="text-xs text-[var(--wf-text-tertiary)]">
            {loading ? "加载中" : `${items.length} 个笔记本`}
          </span>
        </div>

        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {canCreate ? (
            <button
              type="button"
              onClick={() => setCreateOpen(true)}
              className="flex min-h-56 flex-col items-center justify-center gap-3 rounded-[var(--wf-radius-md)] border-2 border-dashed border-[var(--wf-border-strong)] bg-[color-mix(in_srgb,var(--wf-surface)_60%,transparent)] p-5 text-[var(--wf-text-secondary)] transition-colors hover:border-[var(--wf-accent)] hover:text-[var(--wf-accent)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--wf-focus)]"
            >
              <span className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-[var(--wf-surface-muted)]">
                <Plus size={20} aria-hidden="true" />
              </span>
              <span className="text-sm font-semibold">新建笔记本</span>
              <span className="text-xs text-[var(--wf-text-tertiary)]">链接 / 本地视频</span>
            </button>
          ) : null}

          {loading
            ? Array.from({ length: 7 }).map((_, i) => (
                <Card key={i} className="min-h-56 animate-pulse" padding="lg">
                  <div className="h-11 w-11 rounded-[var(--wf-radius-sm)] bg-[var(--wf-surface-muted)]" />
                  <div className="mt-5 h-4 w-3/4 rounded bg-[var(--wf-surface-muted)]" />
                  <div className="mt-2 h-4 w-1/2 rounded bg-[var(--wf-surface-muted)]" />
                  <div className="mt-12 h-3 w-2/3 rounded bg-[var(--wf-surface-muted)]" />
                </Card>
              ))
            : items.map((item) => (
                <NoteCard
                  key={item.id}
                  deleting={delId === item.id}
                  item={item}
                  onDelete={(value) => {
                    setDeleteError(null);
                    setConfirmDelete(value);
                  }}
                />
              ))}

          {!loading && items.length === 0 ? (
            <EmptyState filter={activeFilter} onCreate={() => setCreateOpen(true)} query={query} />
          ) : null}
        </div>
      </section>

      <AnimatePresence>
        {createOpen ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 px-4 py-16 backdrop-blur-sm"
            onClick={() => setCreateOpen(false)}
            role="dialog"
            aria-modal="true"
            aria-label="新建笔记本"
          >
            <motion.div
              initial={{ opacity: 0, y: 16, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 16, scale: 0.98 }}
              transition={{ type: "spring", stiffness: 300, damping: 30 }}
              className="w-full max-w-xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="mb-2 flex items-center justify-between px-1">
                <span className="text-sm font-medium text-white drop-shadow">新建笔记本</span>
                <IconButton
                  aria-label="关闭新建笔记本"
                  className="bg-white/20 text-white hover:bg-white/30"
                  onClick={() => setCreateOpen(false)}
                  size="sm"
                >
                  <X size={14} aria-hidden="true" />
                </IconButton>
              </div>
              <CreateNotePanel next="/notebooks" />
            </motion.div>
          </motion.div>
        ) : null}

        {confirmDelete ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4 backdrop-blur-sm"
            onClick={() => setConfirmDelete(null)}
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-note-title"
          >
            <Card className="w-full max-w-md" padding="lg" onClick={(e) => e.stopPropagation()}>
              <h2 id="delete-note-title" className="text-xl font-semibold text-[var(--wf-text)]">
                删除这本笔记？
              </h2>
              <p className="mt-3 text-sm leading-6 text-[var(--wf-text-secondary)]">
                “{confirmDelete.title}” 会从你的笔记库中移除，相关产物文件也会被清理。此操作不可撤销。
              </p>
              {deleteError ? (
                <p className="mt-4 rounded-[var(--wf-radius-sm)] bg-[var(--wf-danger-surface)] px-3 py-2 text-sm text-[var(--wf-danger)]">
                  删除失败：{deleteError}
                </p>
              ) : null}
              <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
                <Button variant="secondary" onClick={() => setConfirmDelete(null)}>
                  取消
                </Button>
                <Button variant="danger" loading={delId === confirmDelete.id} onClick={() => remove(confirmDelete)}>
                  <Trash2 size={15} aria-hidden="true" />
                  确认删除
                </Button>
              </div>
            </Card>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </main>
  );
}

function NotebooksRouteFallback() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-3 px-6 text-center text-[var(--wf-text-secondary)]">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-[var(--wf-border-strong)] border-t-[var(--wf-accent)]" />
      <p className="text-sm">加载笔记库…</p>
    </main>
  );
}

function NotebooksPageContent() {
  const searchParams = useSearchParams();
  const initialFilter = parseNotebookFilter(searchParams.get("filter"));
  const initialDemoId = parsePublicDemo(searchParams.get("demo"));

  return (
    <RequireAuth allowUnauthenticated>
      <NotebooksInner
        key={`${initialFilter}:${initialDemoId}`}
        initialDemoId={initialDemoId}
        initialFilter={initialFilter}
      />
    </RequireAuth>
  );
}

export default function NotebooksPage() {
  return (
    <Suspense fallback={<NotebooksRouteFallback />}>
      <NotebooksPageContent />
    </Suspense>
  );
}
