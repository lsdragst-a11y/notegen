"""service_common 纯函数断言（normalize_quality / adaptive_chunk_chars /
estimate_pipeline_seconds）。无 GPU / 无 Redis。
Run: .venv/Scripts/python.exe scripts/test_service_common.py"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import service_common as SC  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

# normalize_quality 白名单
check(SC.normalize_quality("720p") == "720p", "720p 合法")
check(SC.normalize_quality("BEST") == "best", "大小写归一")
check(SC.normalize_quality(None) == "best", "None -> best")
check(SC.normalize_quality("; rm -rf") == "best", "非法 -> best")
check(SC.normalize_quality("") == "best", "空 -> best")

# adaptive_chunk_chars 分档
check(SC.adaptive_chunk_chars(0) == 800, "未知时长 -> 800")
check(SC.adaptive_chunk_chars(300) == 400, "<10min -> 400")
check(SC.adaptive_chunk_chars(1000) == 600, "<25min -> 600")
check(SC.adaptive_chunk_chars(3000) == 800, ">=25min -> 800")

# estimate_pipeline_seconds 单调递增 + 正
check(SC.estimate_pipeline_seconds(0) > 0, "0 时长仍有固定开销")
check(SC.estimate_pipeline_seconds(1200) > SC.estimate_pipeline_seconds(600),
      "时长越长估时越大")

# 路径常量存在
check(SC.ROOT.name == "notegen", f"ROOT 指向项目根 -> {SC.ROOT}")
check(str(SC.PY).endswith("python.exe"), "PY 指向 venv python")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ===")
    sys.exit(1)
print("=== ALL CHECKS PASSED ===")
