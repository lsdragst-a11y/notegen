"""idempotency_key 现按 user_id 隔离：同用户同 URL 同 key；不同用户不同 key；
无 user_id 行为稳定（向后兼容公开/旧路径）。无 Redis/网络。
Run: .venv/Scripts/python.exe scripts/test_idempotency_user.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import jobqueue as JQ  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

base = {"quality": "360p", "user_id": "u1"}
k_u1 = JQ.idempotency_key("https://a/v", base)
k_u1b = JQ.idempotency_key("HTTPS://A/V  ", dict(base))  # 归一仍同
k_u2 = JQ.idempotency_key("https://a/v", {"quality": "360p", "user_id": "u2"})
k_none = JQ.idempotency_key("https://a/v", {"quality": "360p"})

check(k_u1 == k_u1b, "同用户同 URL（归一后）同 key")
check(k_u1 != k_u2, "不同用户同 URL 不同 key")
check(k_u1 != k_none and k_u2 != k_none, "带/不带 user_id 不同 key")
check(len(k_u1) == 16, "key 仍 16 hex")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ==="); sys.exit(1)
print("=== ALL CHECKS PASSED ===")
