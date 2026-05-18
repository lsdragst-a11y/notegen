"""为 /mm-ablation 页生成 manifest.json：汇总 9 视频 txt vs mm 对比数据。

读 web/public/mm-ablation/*.{txt,mm}.chapters.json + data/raw/*.meta.json，
出一个紧凑 manifest 供前端单次 fetch 渲染。

Run:
  .venv/Scripts/python.exe scripts/build_mm_manifest.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MM_DIR = ROOT / "web" / "public" / "mm-ablation"
META_DIR = ROOT / "data" / "raw"

# 视频显示名（覆盖 meta title 太长 / 命名混乱的 case）
DISPLAY_NAMES = {
    "BV19E411D78Q_p38_p0": "计网 p38 以太网与 IEEE 802.3",
    "BV19E411D78Q_p44_p0": "计网 p44 以太网交换机",
    "BV19E411D78Q_p46_p0": "计网 p46 IPv4 分组",
    "BV19E411D78Q_p49_p0": "计网 p49 CIDR",
    "BV1YE411D7nH_p37_p0": "OS p37 哲学家进餐问题",
    "EH5jx5qPabU_p0": "AI Agents 入门教程 (英文 25min)",
    "BV1p5wuzQEz8_p2_p0": "Tina Huang p02 编程学习",
    "BV1S6kQBNEJq_p0": "Tina Huang AI Agent 精华版",
    "BV1GofdBZEW7_p0": "Vibe Coding Fundamentals",
}


def _slim_chapter(ch: dict) -> dict:
    return {
        "title": ch["title"],
        "start": ch["start"],
        "end": ch["end"],
        "indices": ch["indices"],
    }


def _load(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  failed {path}: {e}", file=sys.stderr)
        return None


def build() -> dict:
    stems = sorted(set(p.name.split(".")[0] for p in MM_DIR.glob("*.chapters.json")))
    videos = []
    for stem in stems:
        txt = _load(MM_DIR / f"{stem}.txt.chapters.json")
        mm = _load(MM_DIR / f"{stem}.mm.chapters.json")
        if not txt or not mm:
            print(f"  skip {stem} (txt={bool(txt)} mm={bool(mm)})", file=sys.stderr)
            continue
        ab = txt.get("ablation") or {}
        ab_mm = mm.get("ablation") or {}
        sm = ab.get("seg_meta") or {}
        sm_mm = ab_mm.get("seg_meta") or {}
        videos.append({
            "stem": stem,
            "title": DISPLAY_NAMES.get(stem, stem),
            "lang": ab.get("lang") or "?",
            "duration": ab.get("duration"),
            "n_chunks": ab.get("n_chunks") or 0,
            "txt": {
                "n_chapters": ab.get("n_chapters"),
                "chapters": [_slim_chapter(c) for c in txt["chapters"]],
                "attempts": sm.get("llm_attempts"),
                "pass_via": sm.get("llm_pass_via"),
                "repair_used": sm.get("llm_repair_used") or [],
                "fallback": sm.get("fallback_used", False),
            },
            "mm": {
                "n_chapters": ab_mm.get("n_chapters"),
                "chapters": [_slim_chapter(c) for c in mm["chapters"]],
                "attempts": sm_mm.get("llm_attempts"),
                "pass_via": sm_mm.get("llm_pass_via"),
                "repair_used": sm_mm.get("llm_repair_used") or [],
                "fallback": sm_mm.get("fallback_used", False),
            },
        })
    # 汇总
    n = len(videos)
    n_boundary_diff = sum(
        1 for v in videos
        if set(c["start"] for c in v["txt"]["chapters"][1:]) !=
           set(c["start"] for c in v["mm"]["chapters"][1:])
    )
    n_chapter_diff = sum(1 for v in videos
                         if v["txt"]["n_chapters"] != v["mm"]["n_chapters"])
    n_attempts_better = sum(
        1 for v in videos
        if (v["mm"]["attempts"] or 0) > 0 and not v["mm"]["fallback"]
        and (v["mm"]["attempts"] or 0) < (v["txt"]["attempts"] or 0)
    )
    n_attempts_worse = sum(
        1 for v in videos
        if (v["mm"]["attempts"] or 0) > (v["txt"]["attempts"] or 0)
    )
    n_mm_fallback = sum(1 for v in videos if v["mm"]["fallback"])
    summary = {
        "n_videos": n,
        "boundary_diff_pct": round(100 * n_boundary_diff / max(n, 1), 1),
        "chapter_diff_pct": round(100 * n_chapter_diff / max(n, 1), 1),
        "n_attempts_better": n_attempts_better,
        "n_attempts_worse": n_attempts_worse,
        "n_mm_fallback": n_mm_fallback,
    }
    return {"videos": videos, "summary": summary}


def main():
    data = build()
    out = MM_DIR / "manifest.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out} ({len(data['videos'])} videos)")
    print(f"summary: {json.dumps(data['summary'], ensure_ascii=False)}")


if __name__ == "__main__":
    main()
