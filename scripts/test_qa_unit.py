"""QA 模块无 GPU 部分断言：BM25 检索排序、引用校验、CLI 输出解析、
QA 队列状态机（fakeredis）+ 每用户单飞限制。
Run: .venv/Scripts/python.exe scripts/test_qa_unit.py"""
import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import fakeredis  # noqa: E402
import jobqueue as JQ  # noqa: E402
import qa  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)


# ============ (a) BM25 检索 ============
CHUNKS = [
    {"start": 0.0, "end": 60.0,
     "text": "今天我们讲行列式的定义，行列式按行展开是核心计算方法。",
     "headline": "行列式定义与展开", "keywords": ["行列式", "按行展开"]},
    {"start": 60.0, "end": 120.0,
     "text": "接下来是特征值与特征向量，相似对角化需要 n 个线性无关的特征向量。",
     "headline": "特征值与对角化", "keywords": ["特征值", "对角化"]},
    {"start": 120.0, "end": 180.0,
     "text": "最后说真题策略，先做基础题再攻压轴，时间分配很重要。",
     "headline": "真题与时间策略", "keywords": ["真题", "策略"]},
]

hits = qa.retrieve(CHUNKS, "什么是相似对角化的条件？", top_k=3)
check(len(hits) >= 1, "(a) 有相关片段时检索非空")
check(hits[0][0] == 1, f"(a) 对角化问题 top-1 应是 chunk 1（实际 {hits[0][0] if hits else None}）")

hits2 = qa.retrieve(CHUNKS, "行列式怎么按行展开", top_k=3)
check(hits2 and hits2[0][0] == 0, "(a) 行列式问题 top-1 应是 chunk 0")

hits3 = qa.retrieve(CHUNKS, "quantum entanglement blockchain", top_k=3)
check(hits3 == [], "(a) 零词项重叠 → 空列表（上层答「视频没讲」）")

check(qa.retrieve([], "随便问", top_k=3) == [], "(a) 空 chunks 不崩")

# top_k 截断
hits4 = qa.retrieve(CHUNKS, "行列式 特征值 真题", top_k=2)
check(len(hits4) <= 2, "(a) top_k 截断生效")

# ============ (b) 引用校验 ============
allowed = {0, 1}
parsed = {"citations": [
    {"chunk_idx": 1, "quote": "相似对角化需要 n 个线性无关的特征向量"},  # 合法 + 原文子串
    {"chunk_idx": 2, "quote": "随便"},          # 不在检索集合 → 丢
    {"chunk_idx": 0, "quote": "这句不是原文"},   # quote 非子串 → 置空保留
    {"chunk_idx": "x", "quote": ""},            # 非法 idx → 丢
]}
cits = qa._validate_citations(parsed, CHUNKS, allowed)
check(len(cits) == 2, f"(b) 过滤后剩 2 条（实际 {len(cits)}）")
check(cits[0]["chunk_idx"] == 0 and cits[0]["quote"] == "", "(b) 非子串 quote 置空且按时间排序")
check(cits[1]["chunk_idx"] == 1 and cits[1]["start"] == 60.0, "(b) start 映射自 chunk")
check(all(c["chunk_idx"] != 2 for c in cits), "(b) 检索集合外的引用被丢弃")

# 同 chunk 重复引用去重
parsed2 = {"citations": [
    {"chunk_idx": 1, "quote": ""},
    {"chunk_idx": 1, "quote": "特征值与特征向量"},
]}
cits2 = qa._validate_citations(parsed2, CHUNKS, allowed)
check(len(cits2) == 1 and cits2[0]["quote"] == "特征值与特征向量",
      "(b) 同 chunk 去重且补上有效 quote")

# ============ (b2) 多轮：检索词合并 + 对话消息构造 ============
HIST = [{"question": "行列式怎么算", "answer": "按行展开。"}]
check(qa._retrieval_query("那特征值呢", HIST) == "行列式怎么算 那特征值呢",
      "(b2) 追问检索词拼上一轮问题")
check(qa._retrieval_query("行列式怎么算", None) == "行列式怎么算",
      "(b2) 无历史时检索词不变")

msgs = qa._build_messages(CHUNKS, [(0, 1.0)], "那特征值呢", "zh", history=HIST)
roles = [m["role"] for m in msgs]
check(roles == ["system", "user", "assistant", "user"],
      f"(b2) 消息序列含历史轮（实际 {roles}）")
check(msgs[1]["content"] == "行列式怎么算" and msgs[2]["content"] == "按行展开。",
      "(b2) 历史问答进入对话上下文")
long_hist = [{"question": "q", "answer": "a" * 1000}]
msgs2 = qa._build_messages(CHUNKS, [(0, 1.0)], "再问", "zh", history=long_hist)
check(len(msgs2[2]["content"]) <= 400, "(b2) 历史 answer 截断 ≤400")
msgs3 = qa._build_messages(CHUNKS, [(0, 1.0)], "问", "zh", history=None)
check([m["role"] for m in msgs3] == ["system", "user"], "(b2) 无历史保持两条消息")

# ============ (c) CLI 输出解析 ============
ok_result = {"answer": "答", "citations": []}
stdout = "\n".join([
    "      [llm] load from local: models/Qwen...",
    "      [qa] generate (input 1234 tokens) ...",
    qa.RESULT_MARKER + " " + json.dumps(ok_result, ensure_ascii=False),
])
check(qa.parse_qa_output(stdout) == ok_result, "(c) 混合日志中解析出 [QA_RESULT]")
check(qa.parse_qa_output("没有结果行") is None, "(c) 无标记行 → None")
two = stdout + "\n" + qa.RESULT_MARKER + ' {"answer": "第二条", "citations": []}'
check(qa.parse_qa_output(two)["answer"] == "第二条", "(c) 多条取最后一条")
check(qa.parse_qa_output(qa.RESULT_MARKER + " {坏json") is None, "(c) 坏 JSON → None")

# ============ (d) QA 队列状态机（fakeredis） ============
srv = fakeredis.FakeServer()
kv = fakeredis.FakeStrictRedis(server=srv, decode_responses=True)
rq_conn = fakeredis.FakeStrictRedis(server=srv)
JQ.set_connections(kv=kv, rq=rq_conn)

qid = JQ.enqueue_ask("BVtest", "行列式是什么", "zh", "user-1")
st = JQ.qa_state(qid)
check(st is not None and st["status"] == "queued", "(d) enqueue 后状态 queued")
check(st["user_id"] == "user-1" and st["note_id"] == "BVtest", "(d) 元数据写入")

# 同用户第二问 → ActiveQAError；其他用户不受影响
try:
    JQ.enqueue_ask("BVtest", "再问一个", "zh", "user-1")
    check(False, "(d) 进行中重复提问应抛 ActiveQAError")
except JQ.ActiveQAError:
    check(True, "(d) 进行中重复提问抛 ActiveQAError")
qid2 = JQ.enqueue_ask("BVtest", "其他用户的问题", "zh", "user-2")
check(qid2 != qid, "(d) 其他用户可正常入队")

# done 后同用户可再问
JQ.set_qa(qid, status="running")
check(JQ.qa_state(qid)["status"] == "running", "(d) running 状态写入")
JQ.set_qa(qid, status="done", result={"answer": "A", "citations": []})
st = JQ.qa_state(qid)
check(st["status"] == "done" and st["result"]["answer"] == "A", "(d) done + result 解码")
qid3 = JQ.enqueue_ask("BVtest", "第二个问题", "zh", "user-1")
check(qid3 != qid, "(d) 上一问 done 后可再问")

JQ.set_qa(qid3, status="failed", error="x" * 600)
st3 = JQ.qa_state(qid3)
check(len(st3["error"]) <= 500, "(d) error 截断 ≤500")

# ============ (e) run_ask 状态机（进程内执行，monkeypatch 模型调用） ============
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402
import worker_tasks as WT  # noqa: E402

tmp = Path(tempfile.mkdtemp())
(tmp / "summary.json").write_text(json.dumps(CHUNKS, ensure_ascii=False), encoding="utf-8")
WT._resolve_summary_path = lambda nid: (tmp / "summary.json") if nid == "BVok" else None

_orig_answer = qa.answer_question
qa.answer_question = lambda chunks, q, lang="zh", **kw: {
    "answer": f"fake[{len(chunks)}chunks]", "citations": [], "retrieved": []}

JQ.create_qa("qa-ok", "BVok", "问题", "zh", "user-1")
WT.run_ask("qa-ok", "BVok", "问题", "zh")
st = JQ.qa_state("qa-ok")
check(st["status"] == "done" and st["result"]["answer"] == "fake[3chunks]",
      "(e) 正常路径 → done + result")

JQ.create_qa("qa-miss", "BVgone", "问题", "zh", "user-1")
WT.run_ask("qa-miss", "BVgone", "问题", "zh")
check(JQ.qa_state("qa-miss")["status"] == "failed", "(e) 笔记不存在 → failed")

def _boom(*a, **kw):
    raise RuntimeError("CUDA 炸了")
qa.answer_question = _boom
JQ.create_qa("qa-err", "BVok", "问题", "zh", "user-1")
try:
    WT.run_ask("qa-err", "BVok", "问题", "zh")
    check(False, "(e) 模型异常应向上抛（RQ 记 failed registry）")
except RuntimeError:
    check(True, "(e) 模型异常向上抛")
check(JQ.qa_state("qa-err")["status"] == "failed", "(e) 抛出前已写 failed 状态")
qa.answer_question = _orig_answer

# unload_qa_model：未加载时是 no-op 不炸（无 GPU 环境 torch import 失败也被兜住）
WT.unload_qa_model()
check(True, "(e) unload_qa_model 未加载时安全 no-op")

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("ALL PASS")
