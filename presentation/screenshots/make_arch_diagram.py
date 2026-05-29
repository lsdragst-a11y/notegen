"""答辩用架构图：一页纸把 notegen 整个 pipeline + 三层视觉信号画清楚。"""
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from pathlib import Path

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

fig, ax = plt.subplots(figsize=(16, 10), dpi=150)
ax.set_xlim(0, 16)
ax.set_ylim(0, 10)
ax.axis("off")

C_INPUT = "#E8F4FD"
C_AUDIO = "#FFE9CC"
C_TEXT = "#E6F4EA"
C_VISION = "#FCE4EC"
C_LLM = "#F3E5F5"
C_OUTPUT = "#FFF9C4"
C_BORDER = "#37474F"

def box(x, y, w, h, label, color, fontsize=10, bold=False):
    p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.05",
                       linewidth=1.4, edgecolor=C_BORDER, facecolor=color)
    ax.add_patch(p)
    weight = "bold" if bold else "normal"
    ax.text(x + w/2, y + h/2, label, ha="center", va="center",
            fontsize=fontsize, fontweight=weight, wrap=True)

def arrow(x1, y1, x2, y2, color="#37474F", style="-", lw=1.6):
    a = FancyArrowPatch((x1, y1), (x2, y2),
                        arrowstyle="->", mutation_scale=14,
                        color=color, linewidth=lw, linestyle=style)
    ax.add_patch(a)

ax.text(8, 9.55, "NoteGen · 视频→笔记 整体架构",
        ha="center", fontsize=17, fontweight="bold")
ax.text(8, 9.18,
        "输入一个 B 站 URL → 18 个 stage 串行 → 输出带目录/截图/小结的笔记网页",
        ha="center", fontsize=11, color="#555")

box(0.3, 7.7, 2.4, 0.9, "① B 站 URL\n或本地 mp4", C_INPUT, 11, bold=True)

box(3.3, 7.7, 2.2, 0.9, "② 下载视频\n+ 抽音频", C_AUDIO, 10)
arrow(2.7, 8.15, 3.3, 8.15)

box(6.0, 7.7, 2.3, 0.9, "③ Whisper ASR\n听写 + 修错字", C_AUDIO, 10)
arrow(5.5, 8.15, 6.0, 8.15)

box(8.8, 7.7, 2.3, 0.9, "④ 切 chunk\n(~800 字一段)", C_TEXT, 10)
arrow(8.3, 8.15, 8.8, 8.15)

box(11.6, 7.7, 2.4, 0.9, "⑤ Pegasus\n抽 headline + 关键词", C_TEXT, 10)
arrow(11.1, 8.15, 11.6, 8.15)

box(14.2, 7.7, 1.6, 0.9, "⑥ Qwen\n纠 ASR 错字", C_LLM, 10)
arrow(14.0, 8.15, 14.2, 8.15)

ax.text(8, 6.95, "↓  到这里"
                  "「文本侧」"
                  "完成。下面三层视觉信号叠上来，目标都是「章节切得更准」",
        ha="center", fontsize=11, color="#222", style="italic")

vy = 5.3
vh = 1.3
box(0.3, vy, 5.0, vh,
    "第①层视觉 · 选关键帧\n\n"
    "Chinese-CLIP 在每段抽 8 帧\n"
    "挑「最像 headline」那张存 JPG\n\n"
    "用处：笔记里配图 · 留下向量给下一层",
    C_VISION, 9.5)

box(5.5, vy, 5.0, vh,
    "第②层视觉 · 画面相似度\n\n"
    "拿上一层留的向量\n"
    "算相邻段画面 cosine 相似度\n\n"
    "用处：相似度低=可能换主题\n做章节切分的 tie-breaker（数字 cue）",
    C_VISION, 9.5)

box(10.7, vy, 5.0, vh,
    "第③层视觉 · VL 描述（主力）\n\n"
    "Qwen2.5-VL 对代表帧写一句中文\n"
    "「讲师在白板上写 PV 操作…」\n\n"
    "用处：高密度文本 cue 喂切分 LLM\n三层降级 + VL-rescue 保底",
    C_VISION, 9.5)

arrow(2.8, vy, 2.8, 7.7 - 0.05, style="--", lw=1.2, color="#888")
arrow(8.0, vy, 8.0, 7.7 - 0.05, style="--", lw=1.2, color="#888")
arrow(13.2, vy, 13.2, 7.7 - 0.05, style="--", lw=1.2, color="#888")

box(2.0, 3.3, 5.0, 1.3,
    "⑦ 视频内容分类\n\n"
    "teaching / vlog / talk / shopstreet …\n"
    "决定用哪套章节切分 prompt 和笔记模板",
    C_LLM, 10)

box(9.0, 3.3, 5.0, 1.3,
    "⑧ Qwen2.5-7B 章节切分\n\n"
    "输入：headlines + 视觉 cue + 分类\n"
    "输出：顶层章 + 子章节 + 标题\n"
    "失败有 3 attempts + repair + fallback",
    C_LLM, 10, bold=True)

arrow(7.0, 3.95, 9.0, 3.95)
arrow(8.0, 5.3, 11.5, 4.6)
arrow(13.2, 5.3, 12.0, 4.6)
arrow(2.8, 5.3, 4.5, 4.6)

box(0.3, 1.4, 5.0, 1.3,
    "⑨ 章节级生成 (Qwen)\n\n"
    "每章 abstract / 重难点 / recap / quiz\n"
    "末章自动标 wrap-up",
    C_LLM, 10)
arrow(8.0, 3.3, 4.0, 2.75)

box(5.7, 1.4, 4.5, 1.3,
    "⑩ 中英双语翻译 (Qwen)\n\n"
    "标题 / abstract / keywords 出 _zh + _en\n"
    "前端 NavBar 一键切换",
    C_LLM, 10)
arrow(11.5, 3.3, 8.5, 2.75)

box(10.6, 1.4, 5.0, 1.3,
    "最终 · 排版输出\n\n"
    ".md (TOC + 章节 + 截图 + 术语表)\n"
    ".chapters.json / .summary.json",
    C_OUTPUT, 10, bold=True)
arrow(11.5, 3.3, 13.0, 2.75)

box(4.5, 0.05, 7.0, 1.0,
    "前端：Next.js 16 · 读 md+json 渲染 · 视频内嵌 Plyr 跳转 · 章节侧栏 · 双语 toggle · 36 个静态 demo",
    "#CFE2FF", 10, bold=True)
arrow(8.0, 1.4, 8.0, 1.05)

legend_y = -0.5
legend = [
    ("音频/听写", C_AUDIO),
    ("文本处理", C_TEXT),
    ("视觉识别", C_VISION),
    ("大模型生成", C_LLM),
    ("最终输出", C_OUTPUT),
]
ax.text(0.3, legend_y - 0.05, "图例:", fontsize=9, fontweight="bold")

plt.tight_layout()

out_dir = Path(__file__).parent
out_path = out_dir / "architecture.png"
plt.savefig(out_path, dpi=180, bbox_inches="tight", facecolor="white")
print(f"saved -> {out_path}")
