"""视频笔记问答（QA with 时间戳引用）。

检索：纯 Python BM25（jieba 分词，中英混排可用），单视频几十个 chunk 规模下
与向量检索差距很小，零新依赖；检索层独立成 retrieve()，以后换 bge-m3 只动它。
生成：复用 segment_llm 的 Qwen2.5-7B-Instruct-AWQ 加载与 JSON 抽取。
执行：worker 进程内直接调 answer_question（模型常驻，首问冷加载后秒级响应；
与 pipeline 的 VRAM 互斥见 worker_tasks.unload_qa_model）。

CLI 保留作手动调试用（独立进程跑一问，打 [QA_RESULT] 行）：
  python src/qa.py --summary data/.../summary.json --question "..." [--lang zh|en]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from typing import Optional

RESULT_MARKER = "[QA_RESULT]"

# ============ 检索层（可替换：以后换 bge-m3 只改 retrieve） ============

_ASCII_WORD = re.compile(r"[a-zA-Z0-9_]+")


def _tokenize(text: str) -> list[str]:
    """jieba 分词 + 小写。jieba 对混排文本会保留英文单词，数字/符号噪声过滤掉。"""
    import jieba
    out = []
    for tok in jieba.cut(text or ""):
        tok = tok.strip().lower()
        if len(tok) < 1:
            continue
        if len(tok) == 1 and not ("一" <= tok <= "鿿"):
            continue  # 单字符仅保留汉字
        out.append(tok)
    return out


def _chunk_doc(chunk: dict) -> list[str]:
    """chunk → 检索文档 tokens。headline/keywords 是蒸馏过的主题词，×2 加权。"""
    toks = _tokenize(chunk.get("text") or "")
    boost = _tokenize(chunk.get("headline") or "")
    for kw in chunk.get("keywords") or []:
        boost.extend(_tokenize(str(kw)))
    return toks + boost * 2


def retrieve(chunks: list[dict], question: str, top_k: int = 6) -> list[tuple[int, float]]:
    """BM25 (k1=1.5, b=0.75)。返回 [(chunk_idx, score)] 按分降序，超过 top_k 截断。
    问题与全部 chunk 零词项重叠时返回空列表（让上层直说「视频里没讲」）。"""
    q_toks = _tokenize(question)
    if not q_toks or not chunks:
        return []
    docs = [_chunk_doc(c) for c in chunks]
    n = len(docs)
    avgdl = sum(len(d) for d in docs) / max(n, 1) or 1.0
    # df
    df: dict[str, int] = {}
    for d in docs:
        for t in set(d):
            df[t] = df.get(t, 0) + 1
    k1, b = 1.5, 0.75
    scores: list[tuple[int, float]] = []
    for i, d in enumerate(docs):
        tf: dict[str, int] = {}
        for t in d:
            tf[t] = tf.get(t, 0) + 1
        s = 0.0
        for qt in q_toks:
            f = tf.get(qt, 0)
            if f == 0:
                continue
            idf = math.log(1 + (n - df[qt] + 0.5) / (df[qt] + 0.5))
            s += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * len(d) / avgdl))
        if s > 0:
            scores.append((i, s))
    scores.sort(key=lambda x: -x[1])
    return scores[:top_k]


def _cos(a, b) -> float:
    """归一化向量点积（纯 python，几十个 chunk 规模无需 numpy）。"""
    return float(sum(x * y for x, y in zip(a, b)))


# dense 检索召回门槛：BM25 零命中时 dense top-1 至少要这个相似度才算"视频里讲了"
_DENSE_MIN_COS = 0.40


def retrieve_hybrid(chunks: list[dict], question: str,
                    doc_vecs=None, q_vec=None,
                    top_k: int = 6, rrf_k: int = 60) -> list[tuple[int, float]]:
    """BM25 + dense 余弦的 RRF 融合（score = Σ 1/(rrf_k+rank)，rank 从 1 起）。
    - 无向量（doc_vecs/q_vec 为 None 或长度不匹配）→ 退化为纯 BM25；
    - BM25 零命中时 dense 救场（同义改写问题），但 top-1 cos < _DENSE_MIN_COS
      仍返回空，保住「视频里没讲」的诚实回答。
    返回 [(chunk_idx, fused_score)] 降序。"""
    bm25 = retrieve(chunks, question, top_k=len(chunks) or 1)
    has_vec = (doc_vecs is not None and q_vec is not None
               and len(doc_vecs) == len(chunks) and len(chunks) > 0)
    if not has_vec:
        return bm25[:top_k]

    dense = sorted(((i, _cos(doc_vecs[i], q_vec)) for i in range(len(chunks))),
                   key=lambda x: -x[1])
    if not bm25 and (not dense or dense[0][1] < _DENSE_MIN_COS):
        return []

    fused: dict[int, float] = {}
    for rank, (i, _s) in enumerate(bm25, start=1):
        fused[i] = fused.get(i, 0.0) + 1.0 / (rrf_k + rank)
    for rank, (i, s) in enumerate(dense, start=1):
        if s < _DENSE_MIN_COS and i not in fused:
            continue   # 纯凑数的低相似 dense 候选不进池
        fused[i] = fused.get(i, 0.0) + 1.0 / (rrf_k + rank)
    out = sorted(fused.items(), key=lambda x: -x[1])
    return out[:top_k]


# ============ 生成层 ============

def _fmt_time(s: float) -> str:
    s = int(s)
    return f"{s // 60:02d}:{s % 60:02d}"


def _retrieval_query(question: str, history: Optional[list[dict]]) -> str:
    """追问常含指代（"那第二种方法呢"），单独检索召回会塌；
    把上一轮问题拼进检索词。只拼最近一轮，避免话题漂移后旧词干扰。"""
    if history:
        last_q = str(history[-1].get("question") or "").strip()
        if last_q:
            return f"{last_q} {question}"
    return question


def _build_messages(chunks: list[dict], hits: list[tuple[int, float]],
                    question: str, lang: str,
                    history: Optional[list[dict]] = None) -> list[dict]:
    excerpts = []
    for idx, _score in hits:
        c = chunks[idx]
        head = (c.get("headline") or "").strip()
        text = (c.get("text") or "").strip().replace("\n", " ")[:320]
        excerpts.append(
            f"[chunk {idx} | {_fmt_time(c.get('start', 0))} - {_fmt_time(c.get('end', 0))}]"
            f"{(' ' + head) if head else ''}\n{text}"
        )
    ans_lang = "English" if lang == "en" else "中文"
    system = (
        "你是视频学习笔记的问答助手。只能依据下面给出的视频片段回答，"
        "不得编造片段之外的内容。如果片段不足以回答，明确说视频中没有讲到。\n"
        "若用户在追问（指代之前的回答），结合之前的问答理解指代后再作答。\n"
        f"用{ans_lang}回答。\n"
        "输出严格 JSON（不要 markdown 代码块外的文字）：\n"
        '{"answer": "完整回答", "citations": [{"chunk_idx": 0, "quote": "支撑该回答的原文短句"}]}\n'
        "规则：answer 里的每个事实都应有对应 citation；citations 的 chunk_idx 必须来自"
        "给出的片段编号；quote 必须是该片段原文的连续子串（≤40 字）。"
    )
    msgs: list[dict] = [{"role": "system", "content": system}]
    # 最近 2 轮历史作为对话上下文（answer 截断防 prompt 膨胀）
    for h in (history or [])[-2:]:
        hq = str(h.get("question") or "").strip()
        ha = str(h.get("answer") or "").strip()
        if hq and ha:
            msgs.append({"role": "user", "content": hq})
            msgs.append({"role": "assistant", "content": ha[:400]})
    user = "视频片段：\n\n" + "\n\n".join(excerpts) + f"\n\n问题：{question}"
    msgs.append({"role": "user", "content": user})
    return msgs


def _validate_citations(parsed: dict, chunks: list[dict],
                        allowed: set[int]) -> list[dict]:
    """过滤幻觉引用：chunk_idx 必须在检索集合内；quote 不是原文子串则置空。
    返回 [{chunk_idx, start, quote}]，按时间升序去重。"""
    out: dict[int, dict] = {}
    for c in parsed.get("citations") or []:
        try:
            idx = int(c.get("chunk_idx"))
        except (TypeError, ValueError):
            continue
        if idx not in allowed:
            continue
        quote = str(c.get("quote") or "").strip()
        if quote and quote not in (chunks[idx].get("text") or ""):
            quote = ""
        if idx not in out:
            out[idx] = {"chunk_idx": idx,
                        "start": float(chunks[idx].get("start", 0)),
                        "quote": quote[:80]}
        elif quote and not out[idx]["quote"]:
            out[idx]["quote"] = quote[:80]
    return sorted(out.values(), key=lambda x: x["start"])


def answer_question(chunks: list[dict], question: str, lang: str = "zh",
                    top_k: int = 6, max_new_tokens: int = 600,
                    history: Optional[list[dict]] = None,
                    doc_vecs=None, embed_fn=None) -> dict:
    """检索 + 生成 + 引用校验。返回 {answer, citations, retrieved}。
    history: [{question, answer}]，最近 2 轮作为追问上下文。
    doc_vecs/embed_fn: chunk 向量 + 查询编码回调（worker 传入）→ hybrid 检索；
    任一缺失回落纯 BM25。需要 GPU（加载 Qwen）；检索/校验逻辑可无 GPU 单测。"""
    rq = _retrieval_query(question, history)
    q_vec = None
    if doc_vecs is not None and embed_fn is not None:
        try:
            q_vec = embed_fn(rq)
        except Exception as e:
            print(f"      [qa] 查询编码失败（{e}），回落 BM25", flush=True)
    hits = retrieve_hybrid(chunks, rq, doc_vecs=doc_vecs, q_vec=q_vec,
                           top_k=top_k)
    if not hits:
        miss = ("This video does not seem to cover that topic."
                if lang == "en" else "视频内容里没有找到与这个问题相关的片段。")
        return {"answer": miss, "citations": [], "retrieved": []}

    import segment_llm
    import torch
    model, tok = segment_llm.load_model()
    messages = _build_messages(chunks, hits, question, lang, history=history)
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tok(text, return_tensors="pt").to(model.device)
    # 同 segment_llm 的 C2 思路：确定性种子，同问题可复现
    seed = int(hashlib.md5(question.encode("utf-8")).hexdigest()[:8], 16)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    print(f"      [qa] generate (input {inputs['input_ids'].shape[1]} tokens, "
          f"top_k={len(hits)} chunks) ...", flush=True)
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=0.05,
            top_p=0.85,
            pad_token_id=tok.eos_token_id,
        )
    raw = tok.decode(out[0][inputs["input_ids"].shape[1]:],
                     skip_special_tokens=True).strip()
    parsed = segment_llm._extract_json(raw)
    allowed = {i for i, _ in hits}
    if parsed is None or not str(parsed.get("answer") or "").strip():
        # JSON 解析失败兜底：原文当 answer，引用给检索 top-1
        top = hits[0][0]
        return {
            "answer": raw[:1000] or ("(empty output)" if lang == "en" else "（模型未返回内容）"),
            "citations": [{"chunk_idx": top,
                           "start": float(chunks[top].get("start", 0)), "quote": ""}],
            "retrieved": [i for i, _ in hits],
            "degraded": "json_parse_fail",
        }
    return {
        "answer": str(parsed["answer"]).strip()[:2000],
        "citations": _validate_citations(parsed, chunks, allowed),
        "retrieved": [i for i, _ in hits],
    }


# ============ worker 解析（无 GPU，可单测） ============

def parse_qa_output(stdout: str) -> Optional[dict]:
    """从子进程混合日志里取最后一条 [QA_RESULT] 行并解析。"""
    result = None
    for line in (stdout or "").splitlines():
        line = line.strip()
        if line.startswith(RESULT_MARKER):
            try:
                result = json.loads(line[len(RESULT_MARKER):].strip())
            except ValueError:
                continue
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="NoteGen 视频问答 CLI（worker 子进程用）")
    ap.add_argument("--summary", required=True, help="summary.json 路径")
    ap.add_argument("--question", required=True)
    ap.add_argument("--lang", default="zh", choices=["zh", "en"])
    ap.add_argument("--top-k", type=int, default=6)
    args = ap.parse_args()

    with open(args.summary, encoding="utf-8") as f:
        chunks = json.load(f)
    if not isinstance(chunks, list) or not chunks:
        print(f"{RESULT_MARKER} " + json.dumps(
            {"error": "summary.json 为空或格式不对"}, ensure_ascii=False), flush=True)
        return 1
    result = answer_question(chunks, args.question, lang=args.lang, top_k=args.top_k)
    print(f"{RESULT_MARKER} " + json.dumps(result, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
