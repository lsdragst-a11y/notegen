import type {
  CatalogItem, Chapter, ChaptersFile, Chunk, NoteMeta, Mark
} from "./types";
import { API_BASE } from "./api";

const PUBLIC_BASE = ""; // 同源，public/ 静态文件用绝对路径 /notes/... 即可

/** 优先 fetch backend /api/notes（动态枚举，含新生成的笔记），失败退化到 static catalog.json */
export async function fetchCatalog(): Promise<CatalogItem[]> {
  try {
    const r = await fetch(`${API_BASE}/api/notes`, { cache: "no-store" });
    if (r.ok) return await r.json();
  } catch {}
  const r = await fetch(`${PUBLIC_BASE}/notes/catalog.json`, { cache: "no-store" });
  if (!r.ok) throw new Error(`catalog fetch failed: ${r.status}`);
  return r.json();
}

export interface NoteBundle {
  id: string;
  summary: Chunk[];
  chapters: Chapter[];
  meta: NoteMeta | null;
  videoUrl: string;
}

export async function fetchNote(id: string): Promise<NoteBundle> {
  const base = `${PUBLIC_BASE}/notes/${id}`;
  const [summaryR, chaptersR, metaR] = await Promise.all([
    fetch(`${base}/summary.json`, { cache: "no-store" }),
    fetch(`${base}/chapters.json`, { cache: "no-store" }),
    fetch(`${base}/meta.json`, { cache: "no-store" }).catch(() => null),
  ]);
  if (!summaryR.ok) throw new Error("summary.json missing");
  if (!chaptersR.ok) throw new Error("chapters.json missing");
  const summary: Chunk[] = await summaryR.json();
  const chaptersData: ChaptersFile = await chaptersR.json();
  let meta: NoteMeta | null = null;
  if (metaR && metaR.ok) {
    try { meta = await metaR.json(); } catch { meta = null; }
  }
  return {
    id,
    summary,
    chapters: chaptersData.chapters || [],
    meta,
    videoUrl: `${PUBLIC_BASE}/videos/${id}.mp4`,
  };
}

// === 重难点检测（同 backend src/summarize.py:chunk_marks 的 JS 端实现）===
// 让前端能复算（避免在 JSON 里冗余存标记，也方便用户调阈值）
const EMPHASIS_RE = new RegExp(
  // 定义/强调模式（与 backend 保持一致）
  "(?:就是|即(?:[^及])|所谓|意思是|定义为|定义是|表示|称为|称之为)" +
  "|(?:注意(?:[,，。!！]|$)|切记|重点(?:是|在|就是)|关键(?:是|在|就是|点)|核心(?:是|在|就是)" +
  "|强调|要点|别忘了|一定要|必须(?:要|得)|千万(?:别|不要)|记住)" +
  "|(?:很重要|非常重要|尤其重要|至关重要|特别重要)",
  "g"
);

export function chunkMarks(c: Chunk): Mark[] {
  const text = c.text || "";
  const m = text.match(EMPHASIS_RE);
  const count = m ? m.length : 0;
  const density = count / Math.max(text.length, 1) * 100;
  const marks: Mark[] = [];
  if (count >= 4 && density >= 0.7) marks.push("emphasis");
  const segs = c.segments || [];
  const low = segs.filter(s => s.confidence !== undefined && s.confidence !== null && s.confidence < 0.75).length;
  if (low >= 2) marks.push("hard");
  return marks;
}

// === 跨段 keyword 聚合（核心关键词 top-K）===
// 与 src/summarize.py 的 _GLOSSARY_STOPWORDS 保持一致（全 lowercase，匹配时大小写不敏感）
const GLOSSARY_STOPWORDS = new Set<string>([
  // 中文虚词/口语
  "我们","你们","他们","这里","那里","这个","那个","这样","那样",
  "这种","那种","这边","那边","这次","那次","可以","可能","应该",
  "需要","然后","所以","因为","如果","但是","就是","还是","或者",
  "比如","比如说","其实","确实","真的","感觉","觉得","知道","看到",
  "看看","听到","听听","做做","进行","一下","一些","一点","一直",
  "一样","一定","一般","什么","怎么","怎样","为什么","东西",
  "时候","地方","方面","方式","情况","事情","问题","现在",
  "刚才","已经","正在","继续","开始","结束","完成","目前",
  "首先","其次","最后","总之","另外","此外","当然","不过",
  "对吧","好的","好吧","okay","ok","yes","no",
  "当中","里面","里头","下面","上面","前面","后面",
  "之前","之后","之中","之内","之外",
  "这片","那片","这块","那块","这部分","那部分",
  "这点","那点","这条","那条",
  "使用","选择","输入","点击","回车","进入","退出","打开",
  "查看","保存","发送","等待","运行","执行",
  "同一个","另一个","每一个","任何一个","其中一个","下一个","上一个",
  "一些","一种","一类","一组","几个","多个","若干",
  "一个","各个","每个","各种","各类","各位","整个",
  // 英文 stopword（B 修复加，与 Python 端同步）
  "the","and","or","but","for","with","from","into","onto",
  "this","that","these","those","such","there","here",
  "is","are","was","were","be","been","being","am",
  "do","does","did","done","doing",
  "have","has","had","having",
  "will","would","shall","should","can","could","may","might","must",
  "i","you","he","she","it","we","they","me","him","her","us","them",
  "my","your","his","its","our","their","mine","yours","ours",
  "what","which","who","whom","whose","when","where","why","how",
  "if","then","else","than","as","so","because","though","although",
  "of","in","on","at","to","by","up","out","off","down",
  "all","any","some","no","not","only","very","too","just",
  "like","really","actually","basically","literally",
  "now","then","today","yesterday","tomorrow",
  "one","two","three","first","second","third","last","next",
  "go","going","get","got","make","made","take","took","say","said",
  "see","saw","use","used","want","wanted","know","knew","think","thought",
  // 撇号缩写残片
  "ll","re","ve","s","d","m","t","n","em",
  // 高频英文动词三态
  "open","close","opened","closed",
  "click","clicks","clicked","clicking",
  "build","built","building","builds",
  "add","added","adding","adds",
  "remove","removed","removing","removes",
  "delete","deleted","deleting","deletes",
  "create","created","creating","creates",
  "update","updated","updating","updates",
  "save","saved","saving","saves",
  "load","loaded","loading","loads",
  "show","shown","showed","showing",
  "tell","told","telling",
  "try","tried","trying","tries",
  "find","found","finding",
  "let","lets","letting",
  "come","came","coming",
  "look","looked","looking","looks",
  "feel","felt","feeling","feels",
  "seem","seemed","seeming","seems",
  "become","became","becoming",
  "put","puts","putting",
  "set","sets","setting",
  "mean","meant","meaning","means",
  "call","called","calling","calls",
  "work","worked","working","works",
  "run","ran","running","runs",
  "start","started","starting","starts",
  "stop","stopped","stopping","stops",
  "talk","talked","talking",
  "watch","watched","watching",
  "help","helped","helping","helps",
  "need","needs","needed","needing",
  // 高频名词性虚词
  "lot","lots","bit","kind","sort","way","ways","thing","things",
  "stuff","guy","guys","people","person","part","parts",
  // 高频形容词/副词
  "new","old","good","bad","big","small","great","nice",
  "right","left","easy","hard","different","same","similar",
  "much","many","few","more","less","most","least",
  "another","other","others","whole","single","double",
  "definitely","probably","maybe","perhaps","likely",
]);

// 纯小写 ≤2 字符英文 token（如 "ll", "is"）不可能是术语；但 AI/ML/UI/UX 全大写保留
function isShortEnglishFiller(kw: string): boolean {
  if (!kw || kw.length > 2) return false;
  if (!/^[A-Za-z]+$/.test(kw)) return false;
  return kw === kw.toLowerCase();
}

function isStopword(kw: string): boolean {
  return GLOSSARY_STOPWORDS.has(kw.toLowerCase());
}

/** 给前端 chunk-level keywords 卡片用：过滤 stopword / 撇号残片 / 短小写英文 */
export function filterStopwords(keywords: string[]): string[] {
  return keywords.filter(kw =>
    kw.length >= 2 && !isStopword(kw) && !isShortEnglishFiller(kw)
  );
}

import type { DisplayLang } from "./types";

/** 优先用 lang 对应的 keywords_{lang}，缺则 fallback 原 keywords 字段。 */
function pickKeywords(c: Chunk, lang: DisplayLang): string[] {
  const k = (c as unknown as Record<string, unknown>)[`keywords_${lang}`];
  if (Array.isArray(k) && k.length) return k as string[];
  return c.keywords || [];
}

/** 同上，文本字段选 text_{lang} or text。 */
function pickByLangText(c: Chunk, lang: DisplayLang): string {
  const k = (c as unknown as Record<string, unknown>)[`text_${lang}`];
  if (typeof k === "string" && k) return k;
  return c.text || "";
}

export function overviewKeywords(summary: Chunk[], topK = 8,
                                  lang: DisplayLang = "zh"): string[] {
  // 同词大小写聚合（Agent / agent / agents 不再各占一席）
  const df: Record<string, number> = {};         // key = lowercase
  const display: Record<string, string> = {};    // lower -> 首次出现的原形
  const firstPos: Record<string, number> = {};
  for (let i = 0; i < summary.length; i++) {
    const seen = new Set<string>();
    for (const kw of pickKeywords(summary[i], lang)) {
      if (kw.length < 2 || isStopword(kw)) continue;
      if (isShortEnglishFiller(kw)) continue;
      const key = kw.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      df[key] = (df[key] || 0) + 1;
      if (!(key in display)) display[key] = kw;
      if (!(key in firstPos)) firstPos[key] = i;
    }
  }
  const ordered = Object.keys(df).sort((a, b) => {
    if (df[b] !== df[a]) return df[b] - df[a];
    return (firstPos[a] ?? 0) - (firstPos[b] ?? 0);
  });
  return ordered.slice(0, topK).map(k => display[k]);
}

export interface GlossaryEntry {
  term: string;
  df: number;
  firstIdx: number;
  firstStart: number;
  snippet: string;
}

export function buildGlossary(summary: Chunk[], topK = 15,
                                lang: DisplayLang = "zh"): GlossaryEntry[] {
  const minDf = summary.length >= 8 ? 2 : 1;
  // 同词大小写聚合，与 overviewKeywords 一致
  const df: Record<string, number> = {};
  const firstIdx: Record<string, number> = {};
  const display: Record<string, string> = {};
  for (let i = 0; i < summary.length; i++) {
    const uniq = new Set(pickKeywords(summary[i], lang));
    for (const kw of uniq) {
      if (kw.length < 2 || isStopword(kw)) continue;
      if (isShortEnglishFiller(kw)) continue;
      const key = kw.toLowerCase();
      df[key] = (df[key] || 0) + 1;
      if (!(key in firstIdx)) firstIdx[key] = i;
      if (!(key in display)) display[key] = kw;
    }
  }
  const candidates = Object.entries(df)
    .filter(([_, d]) => d >= minDf)
    .sort((a, b) => {
      if (b[1] !== a[1]) return b[1] - a[1];
      return (firstIdx[a[0]] ?? 0) - (firstIdx[b[0]] ?? 0);
    })
    .slice(0, topK);
  return candidates.map(([key, d]) => {
    const idx = firstIdx[key] ?? 0;
    const ref = summary[idx];
    const term = display[key];
    return {
      term,
      df: d,
      firstIdx: idx,
      firstStart: ref.start,
      snippet: findSnippet(term, pickByLangText(ref, lang), 80),
    };
  });
}

function findSnippet(term: string, text: string, maxChars = 80): string {
  if (!text) return "";
  // 按标点切句，找首个含 term 的
  const sents = text.split(/(?<=[。!?！？])|\n+/).map(s => s.trim()).filter(Boolean);
  for (const s of sents) {
    if (s.includes(term)) {
      return s.length > maxChars ? s.slice(0, maxChars) + "…" : s;
    }
  }
  return "";
}

export function formatTime(s: number): string {
  s = Math.floor(s);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h ? `${pad(h)}:${pad(m)}:${pad(sec)}` : `${pad(m)}:${pad(sec)}`;
}

export function formatDuration(s: number): string {
  return formatTime(s);
}
