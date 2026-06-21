"""P1 质量过滤断言（需真 jieba，CI/本机跑）：
- summarize._is_garbled_or_ordinal：近形错字残留 + 序数碎片识别
- keywords_for / build_glossary：脏 token 不出现在关键词与术语表
- segment_llm._drop_lowvalue_quizzes：位置题/循环解析题被丢、概念题保留
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_quality_filters_unit.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from summarize import (_is_garbled_or_ordinal, keywords_for,  # noqa: E402
                       build_glossary)
from segment_llm import _drop_lowvalue_quizzes  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)


# ============ (a) _is_garbled_or_ordinal ============
for bad in ("数捷", "数损", "结枯", "计创机", "第二个", "一号", "三种", "第5步"):
    check(_is_garbled_or_ordinal(bad), f"脏 token 命中：{bad}")
for good in ("数据", "结构", "行列式", "操作系统", "链表", "指针", "BM25", "api"):
    check(not _is_garbled_or_ordinal(good), f"正常词放行：{good}")

# ============ (b) keywords_for 端到端 ============
dirty_text = "数捷 元素的插入和删除，" * 8 + "线性表的顺序存储结构，链表用指针连接节点。" * 6
kws = keywords_for(dirty_text, k=6)
check("数捷" not in kws, f"keywords_for 滤掉近形错字（{kws}）")
check(any(k in ("链表", "指针", "线性表", "存储", "节点", "顺序存储") for k in kws),
      f"正常术语保留（{kws}）")

# ============ (c) build_glossary ============
sums = [{"start": i * 60, "end": i * 60 + 60,
         "text": "线性表 链表 数捷 第二个",
         "keywords": ["链表", "数捷", "第二个", "线性表"]} for i in range(8)]
terms = {g["term"] for g in build_glossary(sums, top_k=10)}
check("数捷" not in terms and "第二个" not in terms,
      f"术语表无脏 token（{terms}）")
check("链表" in terms, "术语表保留真术语")

# ============ (d) quiz 低值题过滤 ============
quizzes = [{"questions": [
    {   # 位置答案 mc（用户实测反例）→ 丢
        "type": "mc", "q": "我们需要找到哪个数据元素？",
        "options": ["第一个", "第二个", "第三个", "第四个"], "answer_idx": 1,
        "explanation": "我们需要找到第二个数据元素"},
    {   # 位置断言 tf（用户实测反例）→ 丢
        "type": "tf", "q": "插入操作在第二个位置进行", "answer": True,
        "explanation": "插入确实在第二个位置进行"},
    {   # 循环解析（解析零新增信息）→ 丢
        "type": "tf", "q": "中断服务程序需要保存寄存器", "answer": True,
        "explanation": "中断服务程序需要保存寄存器"},
    {   # 概念题 → 留
        "type": "mc", "q": "单链表插入为什么要先找到前驱节点？",
        "options": ["要修改前驱的指针域", "内存不足", "需要排序", "头节点为空"],
        "answer_idx": 0,
        "explanation": "插入须把前驱 next 指针改指向新节点，否则链断裂"},
    {   # 正常判断题（解析有新信息）→ 留
        "type": "tf", "q": "顺序表支持随机访问", "answer": True,
        "explanation": "底层是连续内存数组，可按下标 O(1) 寻址"},
]}]
_drop_lowvalue_quizzes(quizzes)
left = quizzes[0]["questions"]
check(len(left) == 2, f"5 道题滤剩 2 道（{len(left)}）")
qs = {q["q"] for q in left}
check("单链表插入为什么要先找到前驱节点？" in qs, "概念 mc 保留")
check("顺序表支持随机访问" in qs, "正常 tf 保留")
check("插入操作在第二个位置进行" not in qs, "位置断言 tf 被丢")

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("ALL PASS")
