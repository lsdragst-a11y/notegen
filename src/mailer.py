"""邮箱验证发信（ROADMAP 阶段 B #3）。stdlib smtplib，无新依赖。

行为：
  - 配齐 NOTEGEN_SMTP_HOST / NOTEGEN_SMTP_USER / NOTEGEN_SMTP_PASS → SMTP_SSL 真发信
  - 未配置（默认）→ 维持原 dev 行为：验证链接打印到控制台，返回 False
  - 发信异常 → 控制台打印链接兜底（用户仍可完成验证），返回 False

QQ 邮箱：host=smtp.qq.com port=465，PASS 填「授权码」（设置→账户→开启 SMTP 生成），
163 同理：smtp.163.com:465 + 授权码。FROM 缺省用 USER。
"""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def _console_fallback(link: str) -> None:
    print(f"[VERIFY] {link}", flush=True)


def smtp_configured() -> bool:
    return bool(os.environ.get("NOTEGEN_SMTP_HOST")
                and os.environ.get("NOTEGEN_SMTP_USER")
                and os.environ.get("NOTEGEN_SMTP_PASS"))


def build_verification_message(to_email: str, link: str, from_addr: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = "NoteGen 邮箱验证"
    msg["From"] = from_addr
    msg["To"] = to_email
    msg.set_content(
        "你好，\n\n"
        "感谢注册 NoteGen。请点击以下链接完成邮箱验证（30 分钟内有效）：\n\n"
        f"{link}\n\n"
        "如果这不是你的操作，请忽略本邮件。\n"
    )
    return msg


def send_verification_email(to_email: str, link: str,
                            smtp_factory=smtplib.SMTP_SSL) -> bool:
    """发验证邮件。返回 True=已发送；False=走了控制台 fallback。
    smtp_factory 可注入（单测用 dummy 捕获，不真连网）。"""
    if not smtp_configured():
        _console_fallback(link)
        return False
    host = os.environ["NOTEGEN_SMTP_HOST"]
    port = int(os.environ.get("NOTEGEN_SMTP_PORT", "465"))
    user = os.environ["NOTEGEN_SMTP_USER"]
    password = os.environ["NOTEGEN_SMTP_PASS"]
    from_addr = os.environ.get("NOTEGEN_SMTP_FROM", user)
    msg = build_verification_message(to_email, link, from_addr)
    try:
        with smtp_factory(host, port, timeout=15) as smtp:
            smtp.login(user, password)
            smtp.send_message(msg)
        return True
    except Exception as e:
        print(f"[mailer] SMTP 发送失败（{e}），回落控制台链接", flush=True)
        _console_fallback(link)
        return False
