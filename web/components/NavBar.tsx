"use client";
import Link from "next/link";
import { Sparkles, Layers, WifiOff, Bookmark } from "lucide-react";
import ThemeToggle from "./ThemeToggle";
import LangToggle from "./LangToggle";
import { useAuth } from "./AuthContext";
import UserMenu from "./UserMenu";
import { useLang } from "./LangContext";
import { useBookmarksList } from "@/lib/bookmarks";

/**
 * 全站共享导航栏。粘性 glass 风格，左侧 logo + brand，右侧 ThemeToggle。
 * children 是可选的中间内容（如详情页传当前笔记标题）。
 */
export default function NavBar({ children }: { children?: React.ReactNode }) {
  const { user, loading, offline } = useAuth();
  const { lang } = useLang();
  const bmCount = useBookmarksList().length;
  return (
    <header className="sticky top-0 z-30 glass border-b border-[var(--border)]">
      <div className="max-w-7xl mx-auto px-6 h-14 flex items-center gap-4">
        <Link href="/" className="inline-flex items-center gap-2 group shrink-0">
          <span className="inline-flex w-7 h-7 rounded-lg items-center justify-center
                           bg-gradient-to-br from-[var(--accent)] to-[#bf5af2]
                           shadow-[var(--shadow-sm)] group-hover:shadow-[var(--shadow-md)]
                           transition-shadow">
            <Sparkles size={13} className="text-white" />
          </span>
          <span className="text-sm font-semibold tracking-tight">NoteGen</span>
        </Link>
        {children ? (
          <div className="flex-1 min-w-0">{children}</div>
        ) : (
          <div className="flex-1" />
        )}
        <Link
          href="/bookmarks"
          className="inline-flex items-center gap-1.5 text-xs text-[var(--fg-secondary)]
                     hover:text-[var(--fg)] transition-colors px-2.5 py-1.5 rounded-md
                     hover:bg-[var(--bg-muted)]"
          title={lang === "en" ? "My bookmarks" : "我的书签"}
        >
          <Bookmark size={13} />
          <span className="hidden sm:inline">{lang === "en" ? "Bookmarks" : "书签"}</span>
          {bmCount > 0 && (
            <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full
                             bg-[var(--accent)] px-1 text-[10px] font-medium text-white">
              {bmCount}
            </span>
          )}
        </Link>
        <Link
          href="/mm-ablation"
          className="hidden sm:inline-flex items-center gap-1.5 text-xs text-[var(--fg-secondary)]
                     hover:text-[var(--fg)] transition-colors px-2.5 py-1.5 rounded-md
                     hover:bg-[var(--bg-muted)]"
          title="多模态切分 ablation 实验对比"
        >
          <Layers size={13} />
          <span className="hidden md:inline">多模态 ablation</span>
        </Link>
        <LangToggle />
        <ThemeToggle />
        {!loading && (user ? (
          <UserMenu />
        ) : offline ? (
          <span className="inline-flex items-center gap-1.5 text-xs text-[var(--fg-tertiary)]
                           px-2.5 py-1.5 rounded-md bg-[var(--bg-muted)]"
                title="无法连接服务器，鉴权状态未知">
            <WifiOff size={13} /> 服务离线
          </span>
        ) : (
          <div className="flex items-center gap-1.5">
            <Link href="/login"
                  className="text-xs text-[var(--fg-secondary)] hover:text-[var(--fg)]
                             px-2.5 py-1.5 rounded-md hover:bg-[var(--bg-muted)] transition-colors">
              登录
            </Link>
            <Link href="/register" className="apple-button text-xs">注册</Link>
          </div>
        ))}
      </div>
    </header>
  );
}
