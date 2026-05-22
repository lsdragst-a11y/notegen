"""回归测试：用真实 Qwen 跑代表性视频的 segment_hierarchical，
对照磁盘上旧 chapters.json 看新规则合并 (2026-05-21) 是否引入副作用。

期望：
  - n<3 视频不触发 nav 检查，照旧产 1 顶层
  - n=3 单顶层 case 现在应升级（auto_subs 兜底 OR LLM 切 2 顶层）
  - n>=4 多章 case 照旧 pass via attempt_1，章数差 ≤ 1

跑法:
  cd E:\\claudeproject\\notegen
  .venv\\Scripts\\python.exe scripts\\regress_segment_rules.py
"""
from __future__ import annotations

import gc
import json
import sys
import time
from pathlib import Path

# Force UTF-8 on Windows console (default GBK can't encode CJK/arrows)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import torch  # noqa: E402

import segment_llm as sl  # noqa: E402


CASES = [
    # (stem, summary_suffix, category, note)
    ("BV175RvBAEgi_p1_p0", "large-v3.neural.texttile.mm.vl", "vlog",
     "n=2 烤口炒饭 vlog — n<3 应不触发 nav 检查"),
    ("BV19E411D78Q_p42_p0", "large-v3.neural.texttile", "teaching",
     "n=3 PPP 协议 — 旧版 chapters=1，新规则应升级到 ≥2 顶层 OR 1+children"),
    ("BV19E411D78Q_p51_p0", "large-v3.neural.texttile.mm.vl", "teaching",
     "n=11 NAT — 旧版 chapters=7，应照旧 pass via attempt_1"),
    ("BV1S6kQBNEJq_p0", "large-v3.neural.texttile.mm.vl", "teaching",
     "n=36 Tina Huang AI Agent — 旧版 chapters=9，应照旧"),
]


def load_summary(stem: str, suffix: str) -> list[dict]:
    fp = ROOT / "data" / "outputs" / f"{stem}.{suffix}.summary.json"
    return json.load(open(fp, encoding="utf-8"))


def load_old_chapters(stem: str, suffix: str) -> list[dict]:
    fp = ROOT / "data" / "outputs" / f"{stem}.{suffix}.chapters.json"
    if not fp.exists():
        return []
    d = json.load(open(fp, encoding="utf-8"))
    return d.get("chapters") if isinstance(d, dict) else d


def main():
    print(f"GPU free: {torch.cuda.mem_get_info()[0]/1024**3:.1f} GB")
    print()
    summary_rows = []
    for stem, suffix, category, note in CASES:
        chunks = load_summary(stem, suffix)
        n = len(chunks)
        old_chs = load_old_chapters(stem, suffix)
        # visual captions (when summary has them)
        vlm_caps = [c.get("vlm_caption") for c in chunks]
        has_vlm = any(c for c in vlm_caps)

        print(f"{'='*70}")
        print(f"{stem}  n={n}  category={category}  has_vlm={has_vlm}")
        print(f"  {note}")
        print(f"  旧 chapters.json: {len(old_chs)} 章")
        print(f"{'='*70}")
        t0 = time.time()
        out = sl.segment_hierarchical(
            chunks,
            headlines=[c.get("headline") for c in chunks],
            category=category,
            lang="zh",
            visual_captions=vlm_caps if has_vlm else None,
        )
        dt = time.time() - t0

        meta = out.get("_meta") if isinstance(out, dict) else None
        chapters = out.get("chapters") if isinstance(out, dict) else []
        new_n = len(chapters)
        print(f"  -> new chapters: {new_n} chs ({dt:.1f}s)")
        if meta:
            print(f"     meta: {json.dumps(meta, ensure_ascii=False)}")
        for ci, ch in enumerate(chapters):
            kids = ch.get("children") or []
            print(f"     ch{ci+1}: '{ch.get('title')}' chunks={ch.get('chunks')} children={len(kids)}")
            for sub in kids:
                print(f"         - '{sub.get('title')}' chunks={sub.get('chunks')}")
        print()
        top0_kids = len((chapters[0].get("children") or [])) if chapters else 0
        summary_rows.append({
            "stem": stem, "n_chunks": n, "category": category,
            "old_chapters": len(old_chs), "new_chapters": new_n,
            "top0_children": top0_kids,
            "pass_via": (meta or {}).get("pass_via"),
            "repair_used": (meta or {}).get("repair_used"),
            "fail_reasons": (meta or {}).get("fail_reasons"),
            "dt_sec": round(dt, 1),
        })

    print(f"{'='*70}")
    print("REGRESSION SUMMARY")
    print(f"{'='*70}")
    print(f"{'stem':32s} {'n':3s} {'cat':9s} {'old':4s} {'new':4s} {'pass_via':14s} repair")
    for r in summary_rows:
        repair_short = ",".join(r["repair_used"] or []) or "-"
        print(f"{r['stem']:32s} {r['n_chunks']:3d} {r['category']:9s} "
              f"{r['old_chapters']:4d} {r['new_chapters']:4d} "
              f"{str(r['pass_via']):14s} {repair_short}")

    # 简单回归判定
    print()
    issues = []
    for r in summary_rows:
        if r["new_chapters"] == 0:
            issues.append(f"  ❌ {r['stem']}: all attempts failed, new_chapters=0")
        if r["n_chunks"] >= 3 and r["new_chapters"] == 1 and r["top0_children"] < 2:
            # 单顶层必须带 ≥2 children 才算有效导航
            issues.append(f"  [WARN] {r['stem']}: 单顶层 n>=3 且 top0_children={r['top0_children']} < 2")
    if issues:
        print("ISSUES:")
        for i in issues:
            print(i)
    else:
        print("[OK] 无明显回归（无 0-chapter / 单顶层无 children 失败）")

    # 释放
    sl._MODEL = None
    sl._TOKENIZER = None
    gc.collect()
    torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
