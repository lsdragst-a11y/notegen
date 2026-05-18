// FastAPI backend base. Dev 默认 :8000，可通过 NEXT_PUBLIC_API_URL 覆盖。
export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function postGenerate(url: string): Promise<{ job_id: string }> {
  const r = await fetch(`${API_BASE}/api/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  if (!r.ok) throw new Error(`generate failed: ${r.status} ${await r.text()}`);
  return r.json();
}

export interface JobEvent {
  stage: string;
  percent: number;
  msg: string;
  note_id?: string;
  video_duration?: number;
  est_total_sec?: number;
  video_title?: string;
  t: number;
}

export async function fetchJob(jobId: string): Promise<JobEvent> {
  const r = await fetch(`${API_BASE}/api/jobs/${jobId}`);
  if (!r.ok) throw new Error("job not found");
  return r.json();
}

export async function deleteNote(id: string): Promise<void> {
  const r = await fetch(`${API_BASE}/api/notes/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!r.ok) throw new Error(`delete failed: ${r.status} ${await r.text()}`);
}

export function subscribeJob(
  jobId: string,
  onEvent: (e: JobEvent) => void,
  onError?: (err: Event) => void,
): () => void {
  const es = new EventSource(`${API_BASE}/api/jobs/${jobId}/events`);
  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data) as JobEvent;
      onEvent(data);
    } catch {}
  };
  es.onerror = (e) => { onError?.(e); };
  return () => es.close();
}
