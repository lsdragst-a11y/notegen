// FastAPI backend base. Dev 默认 :8000，可通过 NEXT_PUBLIC_API_URL 覆盖。
import type { NoteView, HistoryItem, JobStageMetric } from "./types";
export type { JobStageMetric } from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

/** 从 FastAPI 错误响应里抽 detail 文案，失败回落到状态码。 */
export async function parseError(r: Response): Promise<string> {
  try {
    const j = await r.json();
    if (j && typeof j.detail === "string") return j.detail;
  } catch { /* 非 JSON */ }
  return `${r.status}`;
}

/**
 * 画质字符串：'best' 或 'NNNp'（任意整 NNN），后端 _normalize_quality 校验。
 * 实际可选 list 由 /api/probe 返回的 heights 决定。
 */
export type DownloadQuality = string;

export async function postGenerate(
  url: string,
  quality: DownloadQuality = "best",
): Promise<{ job_id: string }> {
  const r = await fetch(`${API_BASE}/api/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ url, quality }),
  });
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
  return r.json();
}

export interface ProbeResult {
  ok: boolean;
  error?: string;
  title: string;
  uploader: string;
  duration: number;
  heights: number[];           // 降序，可能为空
  cookie_status: "ok" | "missing";
}

export async function postProbe(url: string): Promise<ProbeResult> {
  const r = await fetch(`${API_BASE}/api/probe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ url }),
  });
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
  return r.json();
}

/**
 * 上传本地视频文件触发 pipeline。XHR 而非 fetch，因为 fetch 不暴露上传进度事件。
 * onProgress(0..1) 实时回调上传字节数比例；成功 resolve { job_id }。
 */
export function postUpload(
  file: File,
  opts: { title?: string; uploader?: string; onProgress?: (frac: number) => void } = {},
): Promise<{ job_id: string }> {
  return new Promise((resolve, reject) => {
    const fd = new FormData();
    fd.append("file", file);
    if (opts.title) fd.append("title", opts.title);
    if (opts.uploader) fd.append("uploader", opts.uploader);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/api/upload`);
    xhr.withCredentials = true;
    if (opts.onProgress) {
      xhr.upload.addEventListener("progress", e => {
        if (e.lengthComputable) opts.onProgress!(e.loaded / e.total);
      });
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try { resolve(JSON.parse(xhr.responseText)); }
        catch (e) { reject(new Error(`bad response: ${e}`)); }
      } else {
        reject(new Error(`upload failed: ${xhr.status} ${xhr.responseText}`));
      }
    };
    xhr.onerror = () => reject(new Error("upload network error"));
    xhr.send(fd);
  });
}

export interface JobEvent {
  stage: string;
  percent: number;
  msg: string;
  note_id?: string;
  video_duration?: number;
  est_total_sec?: number;
  video_title?: string;
  metrics?: JobStageMetric[];
  t: number;
}

export async function fetchJob(jobId: string): Promise<JobEvent> {
  const r = await fetch(`${API_BASE}/api/jobs/${jobId}`, { credentials: "include" });
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
  return r.json();
}

export async function deleteNote(id: string): Promise<void> {
  const r = await fetch(`${API_BASE}/api/notes/${encodeURIComponent(id)}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
}

export function subscribeJob(
  jobId: string,
  onEvent: (e: JobEvent) => void,
  onError?: (err: Event) => void,
): () => void {
  const es = new EventSource(`${API_BASE}/api/jobs/${jobId}/events`, { withCredentials: true });
  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data) as JobEvent;
      onEvent(data);
    } catch {}
  };
  es.onerror = (e) => { onError?.(e); };
  return () => es.close();
}

export async function fetchMyNotes(): Promise<NoteView[]> {
  const r = await fetch(`${API_BASE}/api/notes/mine`, { credentials: "include" });
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
  return r.json();
}

export async function fetchHistory(): Promise<HistoryItem[]> {
  const r = await fetch(`${API_BASE}/api/history`, { credentials: "include" });
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
  return r.json();
}

// ============ 视频问答 ============
export interface QaCitation {
  chunk_idx: number;
  start: number;
  quote: string;
}

export interface QaResult {
  answer: string;
  citations: QaCitation[];
}

export interface QaState {
  id: string;
  status: "queued" | "running" | "done" | "failed";
  result?: QaResult | null;
  error?: string;
  queue_ahead?: number | null;
}

export interface QaHistoryItem {
  question: string;
  answer: string;
}

export async function postAsk(
  noteId: string, question: string, lang: "zh" | "en",
  history?: QaHistoryItem[],
): Promise<{ qa_id: string }> {
  const r = await fetch(`${API_BASE}/api/notes/${encodeURIComponent(noteId)}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ question, lang, history: history?.length ? history : undefined }),
  });
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
  return r.json();
}

export async function fetchQa(qaId: string): Promise<QaState> {
  const r = await fetch(`${API_BASE}/api/qa/${encodeURIComponent(qaId)}`, {
    credentials: "include",
  });
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
  return r.json();
}

// ============ 分享链接 ============
export async function postShare(noteId: string): Promise<{ token: string }> {
  const r = await fetch(`${API_BASE}/api/notes/${encodeURIComponent(noteId)}/share`, {
    method: "POST", credentials: "include",
  });
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
  return r.json();
}

export async function getShare(noteId: string): Promise<{ token: string } | null> {
  const r = await fetch(`${API_BASE}/api/notes/${encodeURIComponent(noteId)}/share`, {
    credentials: "include",
  });
  if (r.status === 404 || r.status === 401) return null;   // 未分享 / 非 owner / 未登录
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
  return r.json();
}

export async function revokeShare(noteId: string): Promise<void> {
  const r = await fetch(`${API_BASE}/api/notes/${encodeURIComponent(noteId)}/share`, {
    method: "DELETE", credentials: "include",
  });
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
}

export async function fetchSharedMeta(token: string): Promise<{ id: string; title: string }> {
  const r = await fetch(`${API_BASE}/api/shared/${encodeURIComponent(token)}`);
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
  return r.json();
}

export async function retryJob(jobId: string): Promise<{ job_id: string }> {
  const r = await fetch(`${API_BASE}/api/jobs/${jobId}/retry`, {
    method: "POST",
    credentials: "include",
  });
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
  return r.json();
}
