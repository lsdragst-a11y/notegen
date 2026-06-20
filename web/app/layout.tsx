import type { Metadata } from "next";
import { DM_Sans, DM_Serif_Display } from "next/font/google";
import "./globals.css";
import { LangProvider } from "@/components/LangContext";
import { AuthProvider } from "@/components/AuthContext";

const dmSans = DM_Sans({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-dm-sans",
});

const dmSerifDisplay = DM_Serif_Display({
  subsets: ["latin"],
  weight: "400",
  display: "swap",
  variable: "--font-dm-serif-display",
});

export const metadata: Metadata = {
  title: "NoteGen · 教学视频结构化笔记",
  description: "把视频拆成知识点 — 自动分章节、提术语、标重难点。",
};

// 在 hydration 前同步执行，根据 localStorage / matchMedia 设 data-theme，
// 避免 light/dark 切换瞬间的闪烁（FOUC）
const THEME_INIT_SCRIPT = `
(function() {
  try {
    var saved = localStorage.getItem('theme');
    var t = (saved === 'light' || saved === 'dark')
      ? saved
      : (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    document.documentElement.setAttribute('data-theme', t);
  } catch (e) {
    document.documentElement.setAttribute('data-theme', 'light');
  }
})();
`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className={`h-full antialiased ${dmSans.variable} ${dmSerifDisplay.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="min-h-full flex flex-col">
        <AuthProvider>
          <LangProvider>{children}</LangProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
