"use client";
import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { User as UserIcon, BookMarked, History, LogOut, ChevronDown } from "lucide-react";
import { useAuth } from "./AuthContext";

export default function UserMenu() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  if (!user) return null;

  async function doLogout() {
    setOpen(false);
    await logout();
    router.push("/");
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(o => !o)}
        className="inline-flex items-center gap-1.5 text-xs text-[var(--fg-secondary)]
                   hover:text-[var(--fg)] px-2 py-1.5 rounded-md hover:bg-[var(--bg-muted)] transition-colors"
      >
        <span className="w-5 h-5 rounded-full bg-[var(--bg-muted)] inline-flex items-center justify-center">
          <UserIcon size={12} />
        </span>
        <span className="max-w-[12ch] truncate">{user.display_name}</span>
        <ChevronDown size={12} />
      </button>
      {open && (
        <div className="absolute right-0 mt-1.5 w-44 glass rounded-xl border border-[var(--border)]
                        shadow-[var(--shadow-lg)] py-1.5 z-40">
          <Link href="/notebooks" onClick={() => setOpen(false)}
                className="flex items-center gap-2 px-3 py-2 text-xs text-[var(--fg-secondary)]
                           hover:bg-[var(--bg-muted)] hover:text-[var(--fg)] transition-colors">
            <BookMarked size={13} /> 我的笔记本
          </Link>
          <Link href="/history" onClick={() => setOpen(false)}
                className="flex items-center gap-2 px-3 py-2 text-xs text-[var(--fg-secondary)]
                           hover:bg-[var(--bg-muted)] hover:text-[var(--fg)] transition-colors">
            <History size={13} /> 提交历史
          </Link>
          <button onClick={doLogout}
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs text-[var(--fg-secondary)]
                             hover:bg-[var(--bg-muted)] hover:text-[var(--fg)] transition-colors">
            <LogOut size={13} /> 登出
          </button>
        </div>
      )}
    </div>
  );
}
