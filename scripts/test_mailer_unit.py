"""mailer.py 断言：未配置 → 控制台 fallback；配置后 → SMTP 发送（dummy 工厂
捕获，不真连网）；发送异常 → fallback 兜底。纯 stdlib。
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_mailer_unit.py"""
import io
import os
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import mailer  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

_SMTP_KEYS = ("NOTEGEN_SMTP_HOST", "NOTEGEN_SMTP_PORT", "NOTEGEN_SMTP_USER",
              "NOTEGEN_SMTP_PASS", "NOTEGEN_SMTP_FROM")
for k in _SMTP_KEYS:
    os.environ.pop(k, None)

LINK = "http://localhost:3000/verify?token=abc123"

# ============ (a) 未配置 → 控制台 fallback ============
check(not mailer.smtp_configured(), "无环境变量 → smtp_configured False")
buf = io.StringIO()
with redirect_stdout(buf):
    sent = mailer.send_verification_email("a@b.com", LINK)
check(sent is False, "未配置返回 False")
check(f"[VERIFY] {LINK}" in buf.getvalue(), "链接打印到控制台（dev 行为不变）")

# ============ (b) 配置后 → dummy SMTP 捕获 ============
os.environ.update({
    "NOTEGEN_SMTP_HOST": "smtp.qq.com",
    "NOTEGEN_SMTP_USER": "me@qq.com",
    "NOTEGEN_SMTP_PASS": "authcode",
})
check(mailer.smtp_configured(), "配齐三件套 → smtp_configured True")

calls = {}
class DummySMTP:
    def __init__(self, host, port, timeout=None):
        calls["conn"] = (host, port)
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def login(self, user, pw): calls["login"] = (user, pw)
    def send_message(self, msg): calls["msg"] = msg

sent = mailer.send_verification_email("stu@example.com", LINK,
                                      smtp_factory=DummySMTP)
check(sent is True, "配置后返回 True")
check(calls["conn"] == ("smtp.qq.com", 465), f"默认 465 SSL（{calls['conn']}）")
check(calls["login"] == ("me@qq.com", "authcode"), "用授权码登录")
msg = calls["msg"]
check(msg["To"] == "stu@example.com" and msg["From"] == "me@qq.com",
      "收发件人正确（FROM 缺省用 USER）")
check(LINK in msg.get_content(), "正文含验证链接")
check("NoteGen" in msg["Subject"], "主题含产品名")

os.environ["NOTEGEN_SMTP_FROM"] = "noreply@qq.com"
os.environ["NOTEGEN_SMTP_PORT"] = "587"
mailer.send_verification_email("x@y.com", LINK, smtp_factory=DummySMTP)
check(calls["conn"] == ("smtp.qq.com", 587), "NOTEGEN_SMTP_PORT 生效")
check(calls["msg"]["From"] == "noreply@qq.com", "NOTEGEN_SMTP_FROM 生效")

# ============ (c) 发送异常 → fallback 兜底 ============
class BoomSMTP:
    def __init__(self, *a, **k): raise OSError("connection refused")

buf = io.StringIO()
with redirect_stdout(buf):
    sent = mailer.send_verification_email("a@b.com", LINK, smtp_factory=BoomSMTP)
check(sent is False, "异常返回 False")
check(f"[VERIFY] {LINK}" in buf.getvalue(), "异常时控制台链接兜底")

for k in _SMTP_KEYS:
    os.environ.pop(k, None)

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("ALL PASS")
