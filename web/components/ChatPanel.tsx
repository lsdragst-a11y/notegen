"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Loader2, MessageCircle, Send, Sparkles } from "lucide-react";
import type { Chapter } from "@/lib/types";
import { useLang, pickByLang } from "./LangContext";
import { useAuth } from "./AuthContext";
import { postAsk, fetchQa, ApiError, type QaCitation, type QaHistoryItem } from "@/lib/api";
import { formatTime } from "@/lib/notes";

interface ChatMsg {
  role: "user" | "assistant";
  text: string;
  citations?: QaCitation[];
  failed?: boolean;
}

interface Props {
  noteId: string;
  onSeek: (sec: number) => void;
  /** 用于生成推荐问题，可不传 */
  chapters?: Chapter[];
}

const POLL_MS = 1500;
const POLL_MAX_MS = 10 * 60 * 1000;   // 与后端 QA_TIMEOUT 对齐

/**
 * 「对视频提问」面板（docs/frontend-redesign.md §5 落地）。
 * 提交 → /api/notes/{id}/ask 入队 → 轮询 /api/qa/{id} → 答案 + 时间戳引用 chip。
 * 会话历史只存本地 state（单轮问答，每问独立检索）。
 */
export default function ChatPanel({ noteId, onSeek, chapters }: Props) {
  const { lang } = useLang();
  const { user } = useAuth();
  const [msgs, setMsgs] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [statusText, setStatusText] = useState("");
  const listRef = useRef<HTMLDivElement>(null);
  const aliveRef = useRef(true);

  // 空会话时的推荐问题：前两章标题各一条 + 一条通用
  const suggestions = useMemo(() => {
    const out: string[] = [];
    for (const ch of (chapters ?? []).slice(0, 2)) {
      const t = pickByLang(ch, "title", lang);
      if (t) out.push(lang === "en" ? `What does "${t}" cover?` : `「${t}」讲了什么？`);
    }
    out.push(lang === "en" ? "What are the key takeaways of this video?" : "这个视频最核心的结论是什么？");
    return out.slice(0, 3);
  }, [chapters, lang]);

  useEffect(() => {
    aliveRef.current = true;
    return () => { aliveRef.current = false; };
  }, []);

  // 新消息滚到底
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [msgs, busy]);

  const t = (zh: string, en: string) => (lang === "en" ? en : zh);

  async function submit(preset?: string) {
    const q = (preset ?? input).trim();
    if (!q || busy) return;
    setInput("");
    // 追问上下文：从历史消息提取最近 2 组成功的问答对
    const history: QaHistoryItem[] = [];
    for (let i = 1; i < msgs.length; i++) {
      const m = msgs[i];
      if (m.role === "assistant" && !m.failed && msgs[i - 1].role === "user") {
        history.push({ question: msgs[i - 1].text, answer: m.text });
      }
    }
    setMsgs(m => [...m, { role: "user", text: q }]);
    setBusy(true);
    setStatusText(t("提交中…", "Submitting…"));
    try {
      const { qa_id } = await postAsk(noteId, q, lang, history.slice(-2));
      const started = Date.now();
      while (aliveRef.current && Date.now() - started < POLL_MAX_MS) {
        await new Promise(r => setTimeout(r, POLL_MS));
        if (!aliveRef.current) return;
        const st = await fetchQa(qa_id);
        if (st.status === "done" && st.result) {
          setMsgs(m => [...m, {
            role: "assistant",
            text: st.result!.answer,
            citations: st.result!.citations ?? [],
          }]);
          setBusy(false);
          return;
        }
        if (st.status === "failed") {
          setMsgs(m => [...m, {
            role: "assistant", failed: true,
            text: t(`回答失败：${st.error || "未知错误"}`, `Failed: ${st.error || "unknown error"}`),
          }]);
          setBusy(false);
          return;
        }
        if (st.status === "queued") {
          const ahead = st.queue_ahead;
          setStatusText(
            typeof ahead === "number" && ahead > 0
              ? t(`排队中（前面还有 ${ahead} 个）…`, `Queued (${ahead} ahead)…`)
              : t("排队中（GPU 可能在处理其它任务）…", "Queued (GPU may be busy)…"));
        } else {
          setStatusText(t("正在阅读视频内容并组织回答…", "Reading the video and composing an answer…"));
        }
      }
      if (aliveRef.current) {
        setMsgs(m => [...m, { role: "assistant", failed: true,
                              text: t("等待超时，请稍后重试。", "Timed out, please retry later.") }]);
        setBusy(false);
      }
    } catch (e) {
      if (!aliveRef.current) return;
      const msg = e instanceof ApiError && e.status === 409
        ? t("你已有一个问题在处理中，请稍候。", "You already have a question in progress.")
        : t(`提问失败：${String(e instanceof Error ? e.message : e)}`,
            `Ask failed: ${String(e instanceof Error ? e.message : e)}`);
      setMsgs(m => [...m, { role: "assistant", failed: true, text: msg }]);
      setBusy(false);
    }
  }

  // 未登录（公开笔记游客）：提示登录后可提问
  if (!user) {
    return (
      <div className="flex items-center gap-2.5 rounded-full border border-[var(--border)]
                      bg-[var(--bg-elevated)] px-4 py-3 shadow-[var(--shadow-sm)]">
        <MessageCircle size={15} className="shrink-0 text-[var(--fg-tertiary)]" />
        <span className="flex-1 truncate text-sm text-[var(--fg-tertiary)]">
          {t("登录后可对这个视频提问，回答附时间戳引用", "Sign in to ask about this video")}
        </span>
        <Link href={`/login?next=/notes/${noteId}`}
              className="shrink-0 text-xs font-medium text-[var(--accent)] hover:underline">
          {t("去登录", "Sign in")}
        </Link>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] shadow-[var(--shadow-sm)]">
      {/* 历史消息 */}
      {msgs.length > 0 && (
        <div ref={listRef} className="max-h-72 space-y-3 overflow-y-auto px-4 pt-4">
          {msgs.map((m, i) => m.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-br-md bg-[color-mix(in_srgb,var(--accent)_12%,transparent)]
                              px-3.5 py-2 text-sm leading-relaxed text-[var(--fg)]">
                {m.text}
              </div>
            </div>
          ) : (
            <div key={i} className="flex justify-start">
              <div className={`max-w-[92%] rounded-2xl rounded-bl-md px-3.5 py-2 text-sm leading-relaxed
                               ${m.failed
                                 ? "bg-[rgba(217,48,37,0.08)] text-[#c5221f] dark:text-[#f28b82]"
                                 : "bg-[var(--bg-muted)] text-[var(--fg)]"}`}>
                <p className="whitespace-pre-wrap">{m.text}</p>
                {!!m.citations?.length && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {m.citations.map(c => (
                      <button
                        key={c.chunk_idx}
                        type="button"
                        onClick={() => onSeek(c.start)}
                        title={c.quote || undefined}
                        className="inline-flex items-center gap-1 rounded-full bg-[var(--bg-elevated)]
                                   px-2 py-0.5 text-[11px] tabular-nums text-[var(--accent)]
                                   border border-[var(--border)] transition-colors
                                   hover:bg-[var(--accent)] hover:text-[var(--on-accent)]"
                      >
                        ▶ {formatTime(c.start)}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          {busy && (
            <div className="flex items-center gap-2 pb-1 text-xs text-[var(--fg-tertiary)]">
              <Loader2 size={12} className="animate-spin" /> {statusText}
            </div>
          )}
        </div>
      )}

      {/* 空会话引导：推荐问题 chips */}
      {msgs.length === 0 && !busy && suggestions.length > 0 && (
        <div className="flex flex-wrap gap-1.5 px-4 pt-3">
          {suggestions.map(s => (
            <button
              key={s}
              type="button"
              onClick={() => submit(s)}
              className="inline-flex max-w-full items-center gap-1 rounded-full border border-[var(--border)]
                         bg-[var(--bg-muted)] px-3 py-1.5 text-xs text-[var(--fg-secondary)]
                         transition-colors hover:border-[var(--accent)] hover:text-[var(--accent)]"
            >
              <Sparkles size={11} className="shrink-0" />
              <span className="truncate">{s}</span>
            </button>
          ))}
        </div>
      )}

      {/* 输入行 */}
      <div className="flex items-center gap-2.5 px-4 py-3">
        <MessageCircle size={15} className="shrink-0 text-[var(--fg-tertiary)]" />
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter") submit(); e.stopPropagation(); }}
          maxLength={500}
          disabled={busy}
          placeholder={busy
            ? statusText
            : t("对这个视频提问，回答附时间戳引用…", "Ask about this video — answers cite timestamps…")}
          className="min-w-0 flex-1 bg-transparent text-sm outline-none
                     placeholder:text-[var(--fg-tertiary)] disabled:opacity-60"
        />
        <button
          type="button"
          onClick={() => submit()}
          disabled={busy || !input.trim()}
          aria-label={t("发送", "Send")}
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full
                     bg-[var(--accent)] text-[var(--on-accent)] transition-opacity
                     hover:opacity-90 disabled:opacity-40"
        >
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
        </button>
      </div>
    </div>
  );
}
