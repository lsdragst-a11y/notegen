"""platform_meta.py 断言：vtt 解析（小时位/逗号毫秒/标签/rolling 去重）、
轨道挑选（手传优先/ai- 视为自动/语言匹配）、sanity、章节锚定 outline。
纯 stdlib + 临时目录。
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_platform_meta_unit.py"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import platform_meta as PM  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)


# ============ (a) parse_vtt ============
VTT = """WEBVTT
Kind: captions

NOTE this is a comment

1
00:01.000 --> 00:04,500
大家好，<c.colorE5E5E5>今天讲</c>行列式

00:04.500 --> 01:00:02.000
按行展开是核心&nbsp;方法
第二行也算进来

01:00:02.000 --> 01:00:05.000
按行展开是核心 方法 第二行也算进来
"""
segs = PM.parse_vtt(VTT)
check(len(segs) == 2, f"3 cue 经 rolling 去重后 2 段（{len(segs)}）")
check(abs(segs[0]["start"] - 1.0) < 1e-6 and abs(segs[0]["end"] - 4.5) < 1e-6,
      "mm:ss 与逗号毫秒都解析")
check("行列式" in segs[0]["text"] and "<c" not in segs[0]["text"], "标签剥离")
check(abs(segs[1]["end"] - 3605.0) < 1e-6, f"小时位时间戳（end={segs[1]['end']}）")
check("第二行也算进来" in segs[1]["text"], "多行 cue 合并")
check(segs[0]["confidence"] is None and segs[0]["words"] == [], "无置信度字段（None-safe 形状）")

# ============ (b) pick_subtitle_file ============
d = Path(tempfile.mkdtemp())
video = d / "BV1xx_p0.mp4"
video.write_bytes(b"")
(d / "BV1xx_p0.zh-Hans.vtt").write_text("WEBVTT\n", encoding="utf-8")
(d / "BV1xx_p0.en.vtt").write_text("WEBVTT\n", encoding="utf-8")
(d / "BV1xx_p0.ai-zh.vtt").write_text("WEBVTT\n", encoding="utf-8")

r = PM.pick_subtitle_file(video, "zh", manual_langs=["zh-Hans", "en"],
                          auto_langs=["ai-zh"])
check(r is not None and r[1] == "zh-Hans" and r[2] == "manual",
      f"手传 zh-Hans 优先（{r and r[1]}）")
r = PM.pick_subtitle_file(video, "en", manual_langs=["zh-Hans", "en"])
check(r is not None and r[1] == "en", "en 轨按语言匹配")

(d / "BV1xx_p0.zh-Hans.vtt").unlink()
r = PM.pick_subtitle_file(video, "zh", manual_langs=["en"], auto_langs=["ai-zh"])
check(r is None, "只剩 AI 轨且未开 use_auto → None")
r = PM.pick_subtitle_file(video, "zh", manual_langs=["en"], auto_langs=["ai-zh"],
                          use_auto=True)
check(r is not None and r[1] == "ai-zh" and r[2] == "auto", "use_auto 时采 AI 轨且标 auto")
# ai- 前缀即使被平台塞进 subtitles dict 也算自动
r = PM.pick_subtitle_file(video, "zh", manual_langs=["ai-zh"], auto_langs=[])
check(r is None, "ai-* 在 manual dict 里也按自动处理")

# ============ (c) sanity + load_platform_subtitle ============
check(not PM.subtitle_sanity_ok([{"start": 0, "end": 1, "text": "x"}] * 4, 100),
      "段数 <5 拒")
segs10 = [{"start": i * 10.0, "end": i * 10.0 + 8, "text": "x"} for i in range(10)]
check(PM.subtitle_sanity_ok(segs10, 100), "覆盖 80% 过")
check(not PM.subtitle_sanity_ok(segs10, 1000), "覆盖 8% 拒")

good_vtt = "WEBVTT\n\n" + "\n\n".join(
    f"00:{i:02d}.000 --> 00:{i:02d}.900\n第{i}句内容" for i in range(10))
(d / "BV1xx_p0.zh-Hans.vtt").write_text(good_vtt, encoding="utf-8")
meta = {"duration": 10, "subtitle_langs": ["zh-Hans"], "auto_caption_langs": []}
r = PM.load_platform_subtitle(video, meta, "zh")
check(r is not None and r["source"] == "platform_subtitle"
      and len(r["segments"]) == 10 and r["subtitle_kind"] == "manual",
      "load_platform_subtitle 端到端")
check(r["duration"] == 10, "duration 取 meta")
r2 = PM.load_platform_subtitle(video, {"duration": 1000,
                                       "subtitle_langs": ["zh-Hans"]}, "zh")
check(r2 is None, "sanity 不过整体返回 None（回落 whisper）")

# ============ (d) platform_chapter_outline ============
SUMS = [{"start": i * 60.0, "end": i * 60.0 + 60} for i in range(10)]  # 10 chunk x 60s
CHS = [{"start_time": 0, "end_time": 180, "title": "开场"},
       {"start_time": 180, "end_time": 420, "title": "正题"},
       {"start_time": 420, "end_time": 600, "title": "总结"}]
o = PM.platform_chapter_outline(CHS, SUMS)
check(o is not None and len(o["chapters"]) == 3, "3 章映射成功")
check(o["chapters"][0]["indices"] == [0, 1, 2], f"chunk 按中点归章（{o['chapters'][0]['indices']}）")
check(o["chapters"][1]["indices"] == [3, 4, 5, 6], "中段归属正确")
check(o["chapters"][2]["title"] == "总结" and o["chapters"][2]["start"] == 420.0,
      "标题保留创作者原文 + start 取首 chunk")
check(o["_meta"]["pass_via"] == "platform_chapters", "_meta 标 platform_chapters")

check(PM.platform_chapter_outline([CHS[0]], SUMS) is None, "<2 章 → None")
check(PM.platform_chapter_outline(None, SUMS) is None, "无章节 → None")
bad = [dict(CHS[0]), {"start_time": 180, "title": ""}]
check(PM.platform_chapter_outline(bad, SUMS) is None, "空标题 → None（不接受残数据）")
# 全部 chunk 都落进一章（其余章空）→ 有效章 <2 → None，让 LLM 切
tight = [{"start_time": 0, "title": "A"}, {"start_time": 9999, "title": "B"}]
check(PM.platform_chapter_outline(tight, SUMS) is None, "空章丢弃后 <2 → None")
# 乱序输入排序后正确
o2 = PM.platform_chapter_outline(list(reversed(CHS)), SUMS)
check(o2 is not None and o2["chapters"][0]["title"] == "开场", "乱序章节先排序")

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("ALL PASS")
