"""qa.retrieve_hybrid 断言：无向量回落 BM25、长度不匹配回落、dense 救场
（BM25 零命中 + 高 cos）、低 cos 拒绝（保住「没讲」）、RRF 融合排序。
monkeypatch 掉 jieba 分词 → 纯 stdlib 可跑（沙箱/CI 无 jieba 也行）。
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_retrieval_hybrid_unit.py"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import qa  # noqa: E402

# jieba-free 分词（仅本测试）：按非字母数字切 + 小写
qa._tokenize = lambda t: [w for w in re.split(r"[^\w]+", (t or "").lower()) if w]

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)


CHUNKS = [
    {"start": 0,   "end": 60,  "text": "determinant expansion rows method",
     "headline": "determinant"},
    {"start": 60,  "end": 120, "text": "matrix inverse adjoint formula",
     "headline": "inverse"},
    {"start": 120, "end": 180, "text": "eigenvalue eigenvector diagonalization",
     "headline": "eigen"},
]
# 3 维玩具向量（已归一化）：chunk0 ~ x 轴, chunk1 ~ y 轴, chunk2 ~ z 轴
DOCS = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]

# ============ (a) 回落路径 ============
hits = qa.retrieve_hybrid(CHUNKS, "determinant expansion", doc_vecs=None, q_vec=None)
check(hits and hits[0][0] == 0, "无向量 → 纯 BM25（top=chunk0）")
hits = qa.retrieve_hybrid(CHUNKS, "determinant expansion",
                          doc_vecs=DOCS[:2], q_vec=[1, 0, 0])
check(hits and hits[0][0] == 0, "doc_vecs 长度不匹配 → 回落 BM25")

# ============ (b) dense 救场（同义改写：BM25 零命中） ============
q_vec = [0.0, 0.98, 0.2]   # 靠近 chunk1
hits = qa.retrieve_hybrid(CHUNKS, "如何用伴随求逆", doc_vecs=DOCS, q_vec=q_vec)
check(hits and hits[0][0] == 1, f"BM25 零命中时 dense 召回 chunk1（{hits}）")

# ============ (c) 低 cos 拒绝：两路都没证据 → 空（诚实说没讲） ============
q_far = [0.33, 0.33, 0.33]   # 模长 <1，与所有 doc cos≈0.33 < 0.40
hits = qa.retrieve_hybrid(CHUNKS, "怎么做红烧肉", doc_vecs=DOCS, q_vec=q_far)
check(hits == [], f"BM25 空 + dense top<0.40 → []（{hits}）")

# ============ (d) RRF 融合：两路都第一的赢 ============
hits = qa.retrieve_hybrid(CHUNKS, "eigenvalue diagonalization",
                          doc_vecs=DOCS, q_vec=[0.1, 0.1, 0.99])
check(hits and hits[0][0] == 2, "BM25 与 dense 同推 chunk2 → 融合第一")
# BM25 推 0、dense 推 2 且 cos 高 → 两者都该进结果池
hits = qa.retrieve_hybrid(CHUNKS, "determinant expansion",
                          doc_vecs=DOCS, q_vec=[0.0, 0.0, 1.0], top_k=3)
got = {i for i, _ in hits}
check({0, 2} <= got, f"双路各自的 top 都进池（{got}）")
# 低 cos 的 dense 候选不该被凑数塞进来（chunk1 两路都无证据）
hits = qa.retrieve_hybrid(CHUNKS, "determinant", doc_vecs=DOCS,
                          q_vec=[1.0, 0.0, 0.0], top_k=3)
got = {i for i, _ in hits}
check(1 not in got, f"无证据 chunk 不进池（{got}）")

# ============ (e) _cos 基本性质 ============
check(abs(qa._cos([1, 0], [1, 0]) - 1.0) < 1e-9 and abs(qa._cos([1, 0], [0, 1])) < 1e-9,
      "_cos 点积正确")

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("ALL PASS")
