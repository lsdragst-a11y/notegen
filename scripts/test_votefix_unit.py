"""asr_votefix 断言：近形错字投票归一、词典词免疫、高频真新词 ratio 保护、
平局放弃、应用与统计。注入假 jieba（空格分词）+ dict_fn → 纯 stdlib 可跑。
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_votefix_unit.py"""
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# 假 jieba：lcut 按空格切（测试文本用空格分词），不依赖真词典
fake = types.ModuleType("jieba")
fake.dt = types.SimpleNamespace(initialized=True, FREQ={})
fake.lcut = lambda text: (text or "").split()
fake.initialize = lambda: None
fake.setLogLevel = lambda *_: None
sys.modules["jieba"] = fake

import asr_votefix as VF  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)


DICT = {"数据", "数组", "结构", "存储", "今天", "我们", "线性", "操作", "右边",
        "操故"}  # 操故 仅为制造平局的人工词
dict_fn = lambda t: t in DICT

# 语料：数据×9 / 数捷×2 / 数损×1 / 数搯×1 / 数组×4 / 结构×6 / 结枯×1 /
#       右值×8（真新词，不在词典）/ 右边×20 / 操做×1（平局候选）/ 操作×4 / 操故×4
def seg(t): return {"start": 0, "end": 1, "text": t}
TEXTS = (
    ["数据 结构 今天 我们"] * 3 + ["数据 线性 结构"] * 3 +
    ["数据 数组 右边 右边"] * 3 + ["数捷 结枯 右值 右边"] +
    ["数捷 数损 右值 右边"] + ["数搯 数组 右值 右边"] +
    ["右值 右值 右值 右值 右值 右边"] +
    ["右边 右边 右边 右边 右边 右边 右边 右边 右边 右边"] +
    ["操做 操作 操作 操作 操作 操故 操故 操故 操故"] +
    ["数组"]
)

mapping = VF.build_vote_corrections(TEXTS, dict_fn=dict_fn)
check(mapping.get("数捷") == "数据", f"数捷→数据（{mapping.get('数捷')}）")
check(mapping.get("数损") == "数据", "数损→数据")
check(mapping.get("数搯") == "数据", "数搯→数据")
check(mapping.get("结枯") == "结构", "结枯→结构")
check("数组" not in mapping, "词典词 数组 免疫（不会被当错字）")
check("右值" not in mapping,
      "高频真新词 右值(8次) 受 ratio 保护（右边20 < 8×3）不被改写")
check("操做" not in mapping, "两个同频目标（操作/操故）平局 → 放弃")

# ============ 应用 + 统计 ============
asr = {"segments": [seg(t) for t in TEXTS]}
asr, stats = VF.vote_fix(asr, dict_fn=dict_fn)
joined = "\n".join(s["text"] for s in asr["segments"])
check("数捷" not in joined and "数损" not in joined and "结枯" not in joined,
      "全部错字变体被替换")
check("右值" in joined and "数组" in joined, "受保护词原样保留")
check(stats.get("数捷") == ("数据", 2), f"统计 数捷×2（{stats.get('数捷')}）")
check(stats.get("结枯") == ("结构", 1), "统计 结枯×1")

# ============ 干净视频零改动 ============
clean = {"segments": [seg("数据 结构 线性 操作")] * 5}
_, stats2 = VF.vote_fix(clean, dict_fn=dict_fn)
check(stats2 == {}, "干净语料 → 空统计零改动")

# ============ 工具函数 ============
check(VF._one_char_diff("数捷", "数据") and not VF._one_char_diff("数据", "数据")
      and not VF._one_char_diff("数捷", "结构") and not VF._one_char_diff("数据", "数据库"),
      "_one_char_diff 边界")
check(VF._is_zh_token("计创机") and not VF._is_zh_token("a数据")
      and not VF._is_zh_token("数"), "_is_zh_token 边界")

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("ALL PASS")
