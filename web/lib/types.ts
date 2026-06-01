// 与 backend summary.json / chapters.json 结构对齐
export interface ASRSegment {
  start: number;
  end: number;
  text: string;
  confidence?: number;
  avg_logprob?: number;
}

export interface Chunk {
  start: number;
  end: number;
  text: string;
  text_zh?: string;
  text_en?: string;
  headline?: string;
  headline_zh?: string;
  headline_en?: string;
  summary?: string;
  summary_zh?: string;
  summary_en?: string;
  keywords?: string[];
  keywords_zh?: string[];
  keywords_en?: string[];
  vlm_caption?: string;
  segments?: ASRSegment[];
  keyframe?: {
    rel: string;
    time: number;
    score: number;
  };
}

export type DisplayLang = "zh" | "en";

export interface Chapter {
  title: string;
  title_zh?: string;
  title_en?: string;
  start: number;
  end: number;
  indices: number[];
  abstract?: string;
  abstract_zh?: string;
  abstract_en?: string;
  children?: Chapter[];
  quiz?: Quiz;
}

export type QuizQuestion =
  | { type: "mc"; q: string; options: string[]; answer_idx: number; explanation?: string }
  | { type: "tf"; q: string; answer: boolean; explanation?: string };

export interface Quiz {
  questions: QuizQuestion[];
}

export interface Overview {
  summary: string;
  summary_zh?: string;
  summary_en?: string;
  takeaways: string[];
  takeaways_zh?: string[];
  takeaways_en?: string[];
}

export interface ChaptersFile {
  chapters: Chapter[];
  overview?: Overview;
  ablation?: Record<string, unknown>;
}

export type Category = "teaching" | "popsci" | "vlog" | "talk";

export interface NoteMeta {
  id: string;
  title: string;
  uploader?: string;
  duration?: number;
  webpage_url?: string;
  description?: string;
  category?: Category;
  category_confidence?: "high" | "medium" | "low";
}

export interface CatalogItem {
  id: string;
  title: string;
  domain: string;
  duration_sec: number;
  chunks: number;
  chapters: number;
  uploader: string;
  webpage_url?: string;
  video_size_mb?: number | null;
}

export type Mark = "emphasis" | "hard";
