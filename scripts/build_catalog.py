"""扫 web/public/notes/ 重建 catalog.json。

catalog.json 现在只是前端的 SSR / 离线兜底——运行时 `/api/notes` 直接 fs.readdir。
但旧的 catalog.json 只列了 5 个早期 demo（python/os/...）漏掉 28 个 BV-prefix 笔记，
当前是 stale fallback。本脚本扫整个目录重生成，让兜底数据跟现实一致。

跑法：
  .venv/Scripts/python.exe scripts/build_catalog.py
  .venv/Scripts/python.exe scripts/build_catalog.py --dry      # 只打印不写盘

跟 web/app/api/notes/route.ts 的 GET 实现保持字段一致：
  id, title, domain, duration_sec, chunks, chapters, uploader, webpage_url, video_size_mb
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTES = ROOT / "web" / "public" / "notes"
VIDEOS = ROOT / "web" / "public" / "videos"
CATALOG = NOTES / "catalog.json"

CATEGORY_LABEL = {
    "teaching": "学习",
    "popsci": "科普",
    "vlog": "Vlog",
    "talk": "时评",
}


def guess_domain(title: str, category: str | None) -> str:
    """跟 route.ts 的 guessDomain 等价（teaching 再细分到编程/考研/工具）。"""
    t = (title or "").lower()
    if category and category in CATEGORY_LABEL:
        if category == "teaching":
            if any(k in t for k in ("python", "代码", "编程", "agent", "vibe")):
                return "编程教学"
            if any(k in t for k in ("考研", "操作系统", "计算机网络", "线代", "线性代数")):
                return "考研专业课"
            if "claude" in t:
                return "工具教程"
        return CATEGORY_LABEL[category]
    # 无 category 字段的 legacy 笔记
    if any(k in t for k in ("python", "代码", "编程")):
        return "编程教学"
    if any(k in t for k in ("考研", "操作系统", "计算机网络", "线代", "线性代数")):
        return "考研专业课"
    if any(k in t for k in ("vlog", "日常", "外卖")):
        return "Vlog"
    if any(k in t for k in ("评测", "iphone", "ios")):
        return "数码评测"
    if "claude" in t:
        return "工具教程"
    return "学习"


def build_entry(note_id: str) -> dict | None:
    d = NOTES / note_id
    s_p = d / "summary.json"
    c_p = d / "chapters.json"
    if not (s_p.exists() and c_p.exists()):
        return None  # 半成品跳过

    summary = json.loads(s_p.read_text(encoding="utf-8"))
    chapters_doc = json.loads(c_p.read_text(encoding="utf-8"))
    chapters = chapters_doc.get("chapters", []) if isinstance(chapters_doc, dict) else []

    meta: dict = {}
    m_p = d / "meta.json"
    if m_p.exists():
        try:
            meta = json.loads(m_p.read_text(encoding="utf-8"))
        except Exception:
            meta = {}

    last = summary[-1] if summary else {}
    duration_sec = int(last.get("end", 0))

    video_size_mb = None
    v_p = VIDEOS / f"{note_id}.mp4"
    if v_p.exists():
        video_size_mb = round(v_p.stat().st_size / 1024 / 1024, 1)

    return {
        "id": note_id,
        "title": meta.get("title") or note_id,
        "domain": guess_domain(meta.get("title", ""), meta.get("category")),
        "duration_sec": duration_sec,
        "chunks": len(summary),
        "chapters": len(chapters),
        "uploader": meta.get("uploader", ""),
        "webpage_url": meta.get("webpage_url", ""),
        "video_size_mb": video_size_mb,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry", action="store_true", help="只打印不写盘")
    args = p.parse_args()

    ids = sorted([d.name for d in NOTES.iterdir() if d.is_dir()])
    entries: list[dict] = []
    skipped: list[str] = []
    for nid in ids:
        e = build_entry(nid)
        if e is None:
            skipped.append(nid)
        else:
            entries.append(e)

    # 按 mtime 倒序（跟 route.ts 一致），最新生成的排前
    entries.sort(key=lambda e: (NOTES / e["id"]).stat().st_mtime, reverse=True)

    print(f"扫到 {len(ids)} 个目录，可发布 {len(entries)} 条，跳过 {len(skipped)} 个")
    for nid in skipped:
        print(f"  [skip] {nid}（缺 summary/chapters.json）")
    print()
    print(f"catalog entries (top 5):")
    for e in entries[:5]:
        print(f"  {e['id']}  {e['title'][:50]}  ({e['chunks']}c/{e['chapters']}ch)")

    if args.dry:
        print(f"\n[dry] 不写盘，目标: {CATALOG}")
        return

    CATALOG.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[ok] 写入 {CATALOG}（{len(entries)} 条）")


if __name__ == "__main__":
    main()
