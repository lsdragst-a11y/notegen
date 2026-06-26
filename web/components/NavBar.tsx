"use client";

import Link from "next/link";
import { Bookmark, WifiOff } from "lucide-react";

import { BrandMark } from "@/components/brand/BrandMark";
import { Button, Chip } from "@/components/ui";
import { useBookmarksList } from "@/lib/bookmarks";
import { useAuth } from "./AuthContext";
import LangToggle from "./LangToggle";
import { useLang } from "./LangContext";
import ThemeToggle from "./ThemeToggle";
import UserMenu from "./UserMenu";

/**
 * Shared app navigation. Uses the Warm Fold brand mark and tokens,
 * while keeping route behavior unchanged for existing pages.
 */
export default function NavBar({
  children,
  suppressOfflineBadge = false,
}: {
  children?: React.ReactNode;
  suppressOfflineBadge?: boolean;
}) {
  const { user, loading, offline } = useAuth();
  const { lang } = useLang();
  const bmCount = useBookmarksList().length;

  return (
    <header className="sticky top-0 z-30 border-b border-[var(--wf-border)] bg-[color-mix(in_srgb,var(--wf-surface)_88%,transparent)] backdrop-blur-xl">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-6">
        <Link
          href={user ? "/notebooks" : "/"}
          className="inline-flex shrink-0 items-center gap-2 text-[var(--wf-text)] transition-opacity hover:opacity-80 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--wf-focus)]"
          aria-label="NoteGen"
        >
          <BrandMark variant="full" size="sm" />
        </Link>

        {children ? (
          <div className="min-w-0 flex-1 overflow-hidden">{children}</div>
        ) : (
          <div className="flex-1" />
        )}

        {user ? (
          <Link
            href="/bookmarks"
            className="inline-flex items-center gap-1.5 rounded-[var(--wf-radius-xs)] px-2 py-1.5 text-xs text-[var(--wf-text-secondary)] transition-colors hover:bg-[var(--wf-surface-muted)] hover:text-[var(--wf-text)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--wf-focus)]"
            title={lang === "en" ? "My bookmarks" : "我的书签"}
          >
            <Bookmark size={13} aria-hidden="true" />
            <span className="hidden sm:inline">{lang === "en" ? "Bookmarks" : "书签"}</span>
            {bmCount > 0 ? (
              <Chip variant="accent" size="sm">
                {bmCount}
              </Chip>
            ) : null}
          </Link>
        ) : null}

        <div className="hidden items-center gap-1.5 sm:flex">
          <LangToggle />
          <ThemeToggle />
        </div>

        {!loading && user ? <UserMenu /> : null}

        {!loading && !user && offline && !suppressOfflineBadge ? (
          <span
            className="hidden items-center gap-1.5 rounded-[var(--wf-radius-xs)] bg-[var(--wf-surface-muted)] px-2.5 py-1.5 text-xs text-[var(--wf-text-tertiary)] sm:inline-flex"
            title="无法连接服务器，鉴权状态未知"
          >
            <WifiOff size={13} aria-hidden="true" />
            服务离线
          </span>
        ) : null}

        {!loading && !user && !offline ? (
          <div className="hidden items-center gap-1.5 sm:flex">
            <Link href="/login">
              <Button variant="ghost" size="sm">
                登录
              </Button>
            </Link>
            <Link href="/register">
              <Button variant="primary" size="sm">
                注册
              </Button>
            </Link>
          </div>
        ) : null}
      </div>
    </header>
  );
}
