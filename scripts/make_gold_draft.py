"""半自动 gold 草稿生成：扫 data/outputs/*.chapters.json，对每个视频出
data/gold/<id>.gold.json 草稿（silver）+ 带时间戳转写 snippet（供人工校正）+
manifest 候选与缺口报告。

人工流程：跑本脚本 -> 编辑各 *.gold.json（据 snippet 与原视频校正 boundaries_sec、
把 annotated_by 改 "human"）-> 据候选填 data/gold/manifest.json（冻结 30 视频）。

Run: .venv/Scripts/python.exe scripts/make_gold_draft.py [--limit N]
"""
from __future__ import annotations

import argparse
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import seg_eval as E  # noqa: E402
from service_common import _guess_domain  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "data" / "outputs"
GOLD_DIR = ROOT / "data" / "gold"

_DOMAIN_MAP = {"编程教学": "learning", "考研专业课": "learning", "学习": "learning",
               "Vlog": "vlog", "数码评测": "vlog"}


def build_gold_draft(video_id: str, local_source: str, duration: float,
                     domain: str, label: str, boundaries: list[float],
                     draft_source: str) -> dict:
    """组装 gold 草稿 dict，保证 n_segments == len(boundaries)+1，boundaries 升序。"""
    b = sorted(float(x) for x in boundaries)
    return {
        "schema_version": 1,
        "video_id": video_id,
        "local_source": local_source,
        "duration": float(duration),
        "domain": domain,
        "label": label,
        "boundaries_sec": b,
        "n_segments": len(b) + 1,
        "annotated_by": "draft",
        "draft_source": draft_source,
        "notes": "",
    }


def _transcript_snippets(chap_path: Path, boundaries: list[float], window: float = 8.0) -> list[dict]:
    """从同一次产出的 summary.json 取每个边界 ±window 秒附近的转写 snippet，辅助人工校正。
    直接由 chapters 文件名换出 summary（`<base>.chapters.json` -> `<base>.summary.json`），
    保证 snippet 与抽边界用的 chapters 同一次运行、chunk 起点对齐。"""
    sp = chap_path.with_name(chap_path.name.replace(".chapters.json", ".summary.json"))
    if not sp.exists():
        return [{"boundary_sec": b, "near_text": "(no summary.json)"} for b in boundaries]
    try:
        rows = json.loads(sp.read_text(encoding="utf-8"))
    except Exception:
        return [{"boundary_sec": b, "near_text": "(summary parse failed)"} for b in boundaries]
    out = []
    for b in boundaries:
        near = [r.get("summary", r.get("text", ""))[:60]
                for r in rows if abs(float(r.get("start", -1e9)) - b) <= window]
        out.append({"boundary_sec": b, "near_text": " / ".join(near) or "(no nearby chunk)"})
    return out


def _meta_for(stem0: str) -> dict:
    mp = ROOT / "data" / "raw" / f"{stem0}.meta.json"
    if mp.exists():
        try:
            return json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 个候选（0=全部）")
    args = ap.parse_args()

    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    # 每视频取最新（mtime）的一份 chapters.json 作草稿源
    by_video: dict[str, Path] = {}
    for p in sorted(OUTPUTS.glob("*.chapters.json"), key=lambda q: -q.stat().st_mtime):
        stem0 = p.name.split(".")[0]
        by_video.setdefault(stem0, p)

    candidates = []
    items = list(by_video.items())
    if args.limit:
        items = items[: args.limit]
    for stem0, chap_path in items:
        try:
            obj = json.loads(chap_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        boundaries = E.extract_pred_boundaries(obj)
        chs = obj.get("chapters") or []
        duration = float(chs[-1].get("end", 0.0)) if chs else 0.0
        meta = _meta_for(stem0)
        title = meta.get("title", stem0)
        domain = _DOMAIN_MAP.get(_guess_domain(title), "learning")
        # local_source：优先 data/raw 下的 mp4
        src = ""
        for cand in [ROOT / "data" / "raw" / f"{stem0}.mp4",
                     ROOT / "data" / "raw" / f"{stem0}_p0.mp4"]:
            if cand.exists():
                src = str(cand.relative_to(ROOT)).replace("\\", "/")
                break
        draft = build_gold_draft(stem0, src, duration, domain, title,
                                 boundaries, f"llm:{chap_path.name}")
        draft["_draft_snippets"] = _transcript_snippets(chap_path, boundaries)
        out = GOLD_DIR / f"{stem0}.gold.json"
        out.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
        candidates.append({"video_id": stem0, "domain": domain,
                           "gold": f"data/gold/{stem0}.gold.json",
                           "n_segments_draft": draft["n_segments"], "has_source": bool(src)})
        print(f"[draft] {stem0}  domain={domain}  segs={draft['n_segments']}  src={'Y' if src else 'N'}")

    n = len(candidates)
    by_dom: dict[str, int] = {}
    for c in candidates:
        by_dom[c["domain"]] = by_dom.get(c["domain"], 0) + 1
    print(f"\n候选 {n} 个；分档 {by_dom}；目标 30。缺口 {max(0, 30 - n)}。")
    # manifest 候选（人工据此筛选/冻结成 30）
    (GOLD_DIR / "manifest_candidates.json").write_text(
        json.dumps({"schema_version": 1, "candidates": candidates}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"manifest 候选写入 {GOLD_DIR / 'manifest_candidates.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
