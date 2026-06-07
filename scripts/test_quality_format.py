"""Pure-function test：download._quality_to_ytdlp_args 的 yt-dlp 选择参数生成。
重点回归竖屏 bug——画质封顶用 -S "res:N"（res=短边 min(w,h)），横屏按高、
竖屏按宽，朝向无关；-f 恒宽松，绝不让整 job 因画质选择落空而失败。
无网络 / 无 yt-dlp 调用。Run: .venv/Scripts/python.exe scripts/test_quality_format.py"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import download as D  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

# (a) best / 空 / None → 只宽松 -f，不加 -S（取最高画质）
for q in ("best", "", None):
    args = D._quality_to_ytdlp_args(q)
    check(args == ["-f", "bv*+ba/b"], f"(a) {q!r} -> {args}")

# (b) 非法输入 → 兜底为宽松 -f（不抛、不加 -S）
check(D._quality_to_ytdlp_args("garbage") == ["-f", "bv*+ba/b"],
      "(b) 'garbage' -> -f bv*+ba/b")
check(D._quality_to_ytdlp_args("720") == ["-f", "bv*+ba/b"],
      "(b) '720' 缺 p -> -f bv*+ba/b")

# (c) NNNp → -f 宽松 + -S res:N（核心：封顶走短边 res，绝不收窄 -f 致失败）
args = D._quality_to_ytdlp_args("360p")
check(args == ["-f", "bv*+ba/b", "-S", "res:360"], f"(c) '360p' -> {args}")
check(args[:2] == ["-f", "bv*+ba/b"], "(c) -f 仍宽松（永不因画质落空失败）")
check("-S" in args and "res:360" in args, "(c) 用 -S res:360 按短边封顶")

# (d) 任意 NNNp 数字都正确透传到 res:N
for n in (240, 480, 720, 1080):
    args = D._quality_to_ytdlp_args(f"{n}p")
    check(args == ["-f", "bv*+ba/b", "-S", f"res:{n}"], f"(d) '{n}p' -> res:{n}")

# (e) 大小写无关
check(D._quality_to_ytdlp_args("720P") == D._quality_to_ytdlp_args("720p"),
      "(e) '720P' == '720p'")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ===")
    sys.exit(1)
print("=== ALL CHECKS PASSED ===")
